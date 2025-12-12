# Multi-Splunk Query Tool

Herramienta para ejecutar queries en múltiples instancias de Splunk Cloud de forma paralela con soporte para diferentes métodos de autenticación.

## 📋 Requisitos

- Python 3.9 o superior
- Dependencias:
  ```bash
  pip install splunk-sdk pyyaml requests
  ```

## 🚀 Instalación

1. **Clonar o descargar los archivos:**
   - `multi_splunk_query.py`
   - `hosts_config.yml` (ejemplo de configuración)

2. **Instalar dependencias:**
   ```bash
   pip install splunk-sdk pyyaml requests
   ```

3. **Configurar instancias de Splunk:**
   - Editar `hosts_config.yml` con tus instancias
   - Agregar tokens de autenticación en texto plano

## ⚙️ Configuración

### Archivo `hosts_config.yml`

```yaml
instances:
  - name: ficosa                    # Nombre único del cliente
    host: ficosa.splunkcloud.com    # Hostname de Splunk
    port: 8089                       # Puerto (default: 8089)
    scheme: https                    # Protocolo (https/http)
    auth_type: splunk                # Tipo: splunk o bearer
    token: eyJraWQi...               # Token en texto plano
    verify: true                     # Verificar SSL (true/false)
    app: search                      # App de Splunk
    owner: admin                     # Owner del contexto
```

### Tipos de Autenticación

**1. Splunk Token (`auth_type: splunk`)**
- Token estándar de Splunk
- El script automáticamente agrega el prefijo `Splunk ` si no está presente
- Ejemplo: `token: eyJraWQiOiJzcGx1bmsuc2VjcmV0Ii...`

**2. Bearer Token (`auth_type: bearer`)**
- Token de API con autenticación Bearer
- Usa REST API directamente
- Ejemplo: `token: Bearer_abc123def456...`

## 📖 Uso

### Sintaxis Básica

```bash
python multi_splunk_query.py --config hosts_config.yml --query "index=main | stats count by host"
```

### Opciones Disponibles

| Opción | Descripción | Requerido | Default |
|--------|-------------|-----------|---------|
| `--config` | Ruta del archivo YAML de configuración | ✅ | - |
| `--query` | Query de Splunk a ejecutar | ✅* | - |
| `--query-file` | Archivo con la query a ejecutar | ✅* | - |
| `--clients` | Lista de clientes separados por comas | ❌ | Todos |
| `--ask-clients` | Modo interactivo para seleccionar clientes | ❌ | false |
| `--parallel` | Número de ejecuciones paralelas | ❌ | 8 |
| `--timeout` | Timeout en segundos por instancia | ❌ | 300 |
| `--format` | Formato de salida: json o csv | ❌ | json |
| `--outdir` | Directorio para guardar resultados | ❌ | output |
| `--preview` | Filas a mostrar en consola por cliente | ❌ | 20 |

*Nota: Debes especificar `--query` O `--query-file`*

## 💡 Ejemplos de Uso

### 1. Ejecutar query en todas las instancias

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=main error | head 100"
```

### 2. Ejecutar en clientes específicos

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=_internal | stats count by sourcetype" \
  --clients ficosa,cliente2
```

### 3. Modo interactivo para seleccionar clientes

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=main | timechart span=1h count" \
  --ask-clients
```

### 4. Query desde archivo

```bash
# Crear archivo con la query
echo 'index=main sourcetype=access_* | stats count by status' > query.spl

# Ejecutar
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query-file query.spl
```

### 5. Guardar resultados en CSV

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=main | stats count by host, sourcetype" \
  --format csv \
  --outdir resultados_csv
```

### 6. Ajustar concurrencia y timeout

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=_audit | stats count" \
  --parallel 4 \
  --timeout 600
```

### 7. Mostrar más filas en preview

```bash
python multi_splunk_query.py \
  --config hosts_config.yml \
  --query "index=main | head 1000" \
  --preview 50
```

## 📊 Formato de Salida

### En Consola

El script muestra una tabla ASCII por cada cliente:

```
================================================================================
Cliente: ficosa
================================================================================
+----------------+------------------+----------+
| _time          | host             | count    |
+----------------+------------------+----------+
| 2024-12-11...  | server01         | 1234     |
| 2024-12-11...  | server02         | 5678     |
+----------------+------------------+----------+
Mostrando 20 de 150 resultados totales
```

### Archivos Guardados

**JSON (`--format json`):**
```json
[
  {
    "_time": "2024-12-11T10:30:00.000+00:00",
    "host": "server01",
    "count": "1234"
  },
  ...
]
```

**CSV (`--format csv`):**
```csv
_time,host,count
2024-12-11T10:30:00.000+00:00,server01,1234
```

### Estructura de Directorios

```
output/
├── ficosa.json
├── cliente2.json
├── dev_instance.json
└── production.json
```

## 🔍 Normalización de Queries

El script normaliza automáticamente las queries:

| Query Original | Query Normalizada |
|---------------|-------------------|
| `error` | `search error` |
| `index=main` | `search index=main` |
| `\| stats count` | `\| stats count` |
| `search index=main` | `search index=main` |

## 📝 Logging y Diagnóstico

### Niveles de Log

El script proporciona logs detallados:

```
2024-12-11 10:30:00 - INFO - Cargando configuración desde hosts_config.yml
2024-12-11 10:30:00 - INFO - Cargadas 5 instancias
2024-12-11 10:30:00 - INFO - Ejecutando query en 3 instancias: ficosa, cliente2, production
2024-12-11 10:30:01 - INFO - [ficosa] Ejecutando query con SDK...
2024-12-11 10:30:05 - INFO - [ficosa] ✓ Completado: 150 resultados
2024-12-11 10:30:05 - INFO - [ficosa] Guardado en output/ficosa.json
```

### Resumen Final

```
================================================================================
RESUMEN DE EJECUCIÓN
================================================================================
Tiempo total: 45.32 segundos
Exitosos: 4
Errores: 1

✓ Instancias exitosas:
  - ficosa: 150 resultados
  - cliente2: 89 resultados
  - dev_instance: 234 resultados
  - production: 445 resultados

✗ Instancias con errores:
  - analytics_team: Error SDK: Connection timeout

Resultados guardados en: /path/to/output
================================================================================
```

## 🔒 Seguridad

### Mejores Prácticas

1. **No versionar tokens:**
   ```bash
   # Agregar al .gitignore
   echo "hosts_config.yml" >> .gitignore
   echo "*.token" >> .gitignore
   ```

2. **Usar variables de entorno (alternativa):**
   ```bash
   export SPLUNK_TOKEN_FICOSA="eyJraWQi..."
   # Luego modificar el script para leer de variables
   ```

3. **Permisos del archivo de configuración:**
   ```bash
   chmod 600 hosts_config.yml
   ```

4. **Rotación de tokens:**
   - Rotar tokens regularmente
   - Revocar tokens antiguos en Splunk

## 🐛 Troubleshooting

### Error: "splunk-sdk no está instalado"

```bash
pip install splunk-sdk
```

### Error de conexión SSL

Si tienes problemas con certificados SSL:
```yaml
verify: false  # Solo para desarrollo/testing
```

### Timeout en queries largas

Aumentar el timeout:
```bash
--timeout 900  # 15 minutos
```

### Error de autenticación

Verificar:
1. Token válido y no expirado
2. `auth_type` correcto (splunk vs bearer)
3. Permisos del usuario/token en Splunk

### Query devuelve 0 resultados

Verificar:
1. Rango de tiempo (por defecto: últimas 24 horas)
2. Permisos del usuario en los índices
3. Sintaxis de la query

## 📚 Ejemplos de Queries Comunes

### Análisis de errores
```bash
--query "index=main error OR failed | stats count by sourcetype, host"
```

### Top usuarios por actividad
```bash
--query "index=_audit action=* | stats count by user | sort -count | head 20"
```

### Rendimiento por tiempo
```bash
--query "index=main | timechart span=1h avg(response_time) by host"
```

### Búsqueda de IPs sospechosas
```bash
--query "index=firewall src_ip=* | stats count by src_ip, dest_port | where count > 1000"
```

## 🤝 Contribuciones

Para reportar bugs o solicitar features, por favor contacta al equipo de desarrollo.

## 📄 Licencia

Este script es de uso interno. Consulta con tu organización sobre políticas de uso.

---

**Versión:** 1.0.0  
**Última actualización:** Diciembre 2024
