#!/usr/bin/env python3
"""
Multi-Splunk Query Tool
Ejecuta queries en múltiples instancias de Splunk Cloud de forma paralela.
"""

import argparse
import json
import csv
import logging
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import splunklib.client as client
    import splunklib.results as results
except ImportError:
    print("Error: splunk-sdk no está instalado. Ejecuta: pip install splunk-sdk")
    sys.exit(1)

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class SplunkInstance:
    """Configuración de una instancia de Splunk"""
    name: str
    host: str
    port: int
    scheme: str
    auth_type: str
    token: str
    verify: bool
    app: str
    owner: str


class TableRenderer:
    """Renderiza tablas en consola sin dependencias externas"""
    
    @staticmethod
    def render(data: List[Dict[str, Any]], max_rows: int = 20, title: str = "") -> str:
        """Renderiza datos como tabla ASCII"""
        if not data:
            return "No hay resultados para mostrar.\n"
        
        # Limitar filas
        display_data = data[:max_rows]
        total_rows = len(data)
        
        # Obtener columnas
        columns = list(display_data[0].keys()) if display_data else []
        if not columns:
            return "No hay columnas para mostrar.\n"
        
        # Calcular anchos de columna
        col_widths = {col: len(col) for col in columns}
        for row in display_data:
            for col in columns:
                val = str(row.get(col, ''))
                col_widths[col] = max(col_widths[col], len(val))
        
        # Limitar ancho máximo por columna
        max_width = 50
        for col in col_widths:
            col_widths[col] = min(col_widths[col], max_width)
        
        # Construir tabla
        output = []
        
        # Título
        if title:
            output.append(f"\n{'=' * 80}")
            output.append(f"{title}")
            output.append(f"{'=' * 80}")
        
        # Separador superior
        separator = "+" + "+".join("-" * (col_widths[col] + 2) for col in columns) + "+"
        output.append(separator)
        
        # Encabezados
        header = "|"
        for col in columns:
            header += f" {col:<{col_widths[col]}} |"
        output.append(header)
        output.append(separator)
        
        # Filas de datos
        for row in display_data:
            row_str = "|"
            for col in columns:
                val = str(row.get(col, ''))
                if len(val) > col_widths[col]:
                    val = val[:col_widths[col]-3] + "..."
                row_str += f" {val:<{col_widths[col]}} |"
            output.append(row_str)
        
        # Separador inferior
        output.append(separator)
        
        # Información adicional
        if total_rows > max_rows:
            output.append(f"Mostrando {max_rows} de {total_rows} resultados totales")
        else:
            output.append(f"Total: {total_rows} resultados")
        
        return "\n".join(output)


class SplunkQueryExecutor:
    """Ejecuta queries en instancias de Splunk"""
    
    def __init__(self, timeout: int = 300):
        self.timeout = timeout
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Crea sesión HTTP con reintentos"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    
    def normalize_query(self, query: str) -> str:
        """Normaliza la query para Splunk"""
        query = query.strip()
        if not query.startswith('search') and not query.startswith('|'):
            query = f"search {query}"
        return query
    
    def execute_splunk_sdk(self, instance: SplunkInstance, query: str) -> Tuple[List[Dict], Optional[str]]:
        """Ejecuta query usando Splunk SDK"""
        try:
            # Preparar token
            token_value = instance.token
            if instance.auth_type == 'splunk' and not token_value.startswith('Splunk '):
                token_value = f"Splunk {token_value}"
            
            # Crear servicio
            service = client.connect(
                host=instance.host,
                port=instance.port,
                scheme=instance.scheme,
                token=token_value,
                app=instance.app,
                owner=instance.owner,
                verify=instance.verify
            )
            
            logger.info(f"[{instance.name}] Ejecutando query con SDK...")
            
            # Ejecutar búsqueda
            job = service.jobs.create(
                query,
                exec_mode="blocking",
                earliest_time="-24h",
                latest_time="now"
            )
            
            # Obtener resultados
            result_stream = job.results(output_mode='json', count=0)
            reader = results.JSONResultsReader(result_stream)
            
            data = []
            for result in reader:
                if isinstance(result, dict):
                    data.append(result)
            
            logger.info(f"[{instance.name}] ✓ Completado: {len(data)} resultados")
            return data, None
            
        except Exception as e:
            error_msg = f"Error SDK: {str(e)}"
            logger.error(f"[{instance.name}] {error_msg}")
            return [], error_msg
    
    def execute_bearer_rest(self, instance: SplunkInstance, query: str) -> Tuple[List[Dict], Optional[str]]:
        """Ejecuta query usando REST API con Bearer token"""
        try:
            base_url = f"{instance.scheme}://{instance.host}:{instance.port}"
            headers = {
                'Authorization': f"Bearer {instance.token}",
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            logger.info(f"[{instance.name}] Ejecutando query con REST API...")
            
            # Crear job de búsqueda
            create_job_url = f"{base_url}/services/search/jobs"
            data = {
                'search': query,
                'exec_mode': 'blocking',
                'earliest_time': '-24h',
                'latest_time': 'now',
                'output_mode': 'json'
            }
            
            response = self.session.post(
                create_job_url,
                headers=headers,
                data=data,
                verify=instance.verify,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Obtener SID del job
            job_info = response.json()
            sid = job_info.get('sid')
            
            if not sid:
                raise ValueError("No se pudo obtener SID del job")
            
            # Obtener resultados
            results_url = f"{base_url}/services/search/jobs/{sid}/results"
            params = {'output_mode': 'json', 'count': 0}
            
            response = self.session.get(
                results_url,
                headers=headers,
                params=params,
                verify=instance.verify,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            results_data = response.json()
            data = results_data.get('results', [])
            
            logger.info(f"[{instance.name}] ✓ Completado: {len(data)} resultados")
            return data, None
            
        except Exception as e:
            error_msg = f"Error REST: {str(e)}"
            logger.error(f"[{instance.name}] {error_msg}")
            return [], error_msg
    
    def execute(self, instance: SplunkInstance, query: str) -> Tuple[List[Dict], Optional[str]]:
        """Ejecuta query en una instancia"""
        normalized_query = self.normalize_query(query)
        
        if instance.auth_type == 'splunk':
            return self.execute_splunk_sdk(instance, normalized_query)
        elif instance.auth_type == 'bearer':
            return self.execute_bearer_rest(instance, normalized_query)
        else:
            error_msg = f"Tipo de autenticación no soportado: {instance.auth_type}"
            logger.error(f"[{instance.name}] {error_msg}")
            return [], error_msg


class ConfigLoader:
    """Carga configuración desde archivo YAML"""
    
    @staticmethod
    def load(config_path: str) -> List[SplunkInstance]:
        """Carga instancias desde YAML"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            instances = []
            for inst_config in config.get('instances', []):
                instance = SplunkInstance(
                    name=inst_config['name'],
                    host=inst_config['host'],
                    port=inst_config.get('port', 8089),
                    scheme=inst_config.get('scheme', 'https'),
                    auth_type=inst_config.get('auth_type', 'splunk'),
                    token=inst_config['token'],
                    verify=inst_config.get('verify', True),
                    app=inst_config.get('app', 'search'),
                    owner=inst_config.get('owner', 'admin')
                )
                instances.append(instance)
            
            return instances
        
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            sys.exit(1)


class ResultsHandler:
    """Maneja guardado de resultados"""
    
    @staticmethod
    def save_json(data: List[Dict], filepath: Path):
        """Guarda resultados en JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def save_csv(data: List[Dict], filepath: Path):
        """Guarda resultados en CSV"""
        if not data:
            # Crear archivo vacío
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('')
            return
        
        keys = list(data[0].keys())
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)


def select_clients_interactive(instances: List[SplunkInstance]) -> List[str]:
    """Modo interactivo para seleccionar clientes"""
    print("\n=== Clientes disponibles ===")
    for idx, inst in enumerate(instances, 1):
        print(f"{idx}. {inst.name}")
    
    print("\nIngresa los números de los clientes separados por comas (ej: 1,3,5)")
    print("O presiona Enter para seleccionar todos:")
    
    selection = input("> ").strip()
    
    if not selection:
        return [inst.name for inst in instances]
    
    try:
        indices = [int(x.strip()) for x in selection.split(',')]
        selected = [instances[i-1].name for i in indices if 0 < i <= len(instances)]
        return selected
    except (ValueError, IndexError):
        logger.error("Selección inválida")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Ejecuta queries en múltiples instancias de Splunk Cloud',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--config', required=True, help='Ruta del archivo YAML de configuración')
    parser.add_argument('--query', help='Query de Splunk a ejecutar')
    parser.add_argument('--query-file', help='Archivo con la query a ejecutar')
    parser.add_argument('--clients', help='Lista de clientes separados por comas (ej: ficosa,cliente2)')
    parser.add_argument('--ask-clients', action='store_true', help='Modo interactivo para seleccionar clientes')
    parser.add_argument('--parallel', type=int, default=8, help='Número de ejecuciones paralelas (default: 8)')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout en segundos por instancia (default: 300)')
    parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Formato de salida (default: json)')
    parser.add_argument('--outdir', default='output', help='Directorio de salida (default: output)')
    parser.add_argument('--preview', type=int, default=20, help='Filas a mostrar en consola (default: 20)')
    
    args = parser.parse_args()
    
    # Validar query
    if not args.query and not args.query_file:
        logger.error("Debes especificar --query o --query-file")
        sys.exit(1)
    
    # Leer query
    if args.query_file:
        try:
            with open(args.query_file, 'r', encoding='utf-8') as f:
                query = f.read()
        except Exception as e:
            logger.error(f"Error leyendo archivo de query: {e}")
            sys.exit(1)
    else:
        query = args.query
    
    # Cargar configuración
    logger.info(f"Cargando configuración desde {args.config}")
    instances = ConfigLoader.load(args.config)
    logger.info(f"Cargadas {len(instances)} instancias")
    
    # Filtrar clientes
    if args.ask_clients:
        selected_clients = select_clients_interactive(instances)
    elif args.clients:
        selected_clients = [c.strip() for c in args.clients.split(',')]
    else:
        selected_clients = [inst.name for inst in instances]
    
    filtered_instances = [inst for inst in instances if inst.name in selected_clients]
    
    if not filtered_instances:
        logger.error("No se encontraron instancias con los clientes seleccionados")
        sys.exit(1)
    
    logger.info(f"Ejecutando query en {len(filtered_instances)} instancias: {', '.join(selected_clients)}")
    
    # Crear directorio de salida
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    # Ejecutar queries en paralelo
    executor = SplunkQueryExecutor(timeout=args.timeout)
    renderer = TableRenderer()
    handler = ResultsHandler()
    
    results = {}
    errors = {}
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {
            pool.submit(executor.execute, inst, query): inst 
            for inst in filtered_instances
        }
        
        for future in as_completed(futures):
            instance = futures[future]
            try:
                data, error = future.result()
                
                if error:
                    errors[instance.name] = error
                else:
                    results[instance.name] = data
                    
                    # Guardar resultados
                    ext = 'json' if args.format == 'json' else 'csv'
                    filepath = outdir / f"{instance.name}.{ext}"
                    
                    if args.format == 'json':
                        handler.save_json(data, filepath)
                    else:
                        handler.save_csv(data, filepath)
                    
                    logger.info(f"[{instance.name}] Guardado en {filepath}")
                    
                    # Mostrar preview en consola
                    table = renderer.render(data, max_rows=args.preview, title=f"Cliente: {instance.name}")
                    print(f"\n{table}")
                
            except Exception as e:
                error_msg = f"Error inesperado: {str(e)}"
                errors[instance.name] = error_msg
                logger.error(f"[{instance.name}] {error_msg}")
    
    elapsed_time = time.time() - start_time
    
    # Resumen final
    print("\n" + "=" * 80)
    print("RESUMEN DE EJECUCIÓN")
    print("=" * 80)
    print(f"Tiempo total: {elapsed_time:.2f} segundos")
    print(f"Exitosos: {len(results)}")
    print(f"Errores: {len(errors)}")
    
    if results:
        print("\n✓ Instancias exitosas:")
        for name, data in results.items():
            print(f"  - {name}: {len(data)} resultados")
    
    if errors:
        print("\n✗ Instancias con errores:")
        for name, error in errors.items():
            print(f"  - {name}: {error}")
    
    print(f"\nResultados guardados en: {outdir.absolute()}")
    print("=" * 80)
    
    sys.exit(0 if not errors else 1)


if __name__ == '__main__':
    main()
