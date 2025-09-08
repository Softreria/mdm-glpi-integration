# Guía de Solución de Problemas

Esta guía cubre los problemas más comunes y sus soluciones para la integración MDM-GLPI.

## 🔍 Diagnóstico General

### Verificación Rápida del Sistema

```bash
# Verificar estado general
python cli.py health

# Verificar conectividad
python cli.py test-connections

# Ver información del sistema
python cli.py version
python cli.py info

# Verificar configuración
python cli.py config --validate
```

### Logs y Monitoreo

```bash
# Ver logs en tiempo real
tail -f logs/mdm-glpi.log

# Buscar errores específicos
grep -i "error" logs/mdm-glpi.log | tail -20
grep -i "failed" logs/mdm-glpi.log | tail -20

# Ver logs estructurados (JSON)
jq '.' logs/mdm-glpi.log | grep -A5 -B5 "ERROR"

# Verificar métricas
curl http://localhost:8080/metrics
curl http://localhost:8080/status
```

## 🔌 Problemas de Conectividad

### Error: "Connection refused" o "Timeout"

**Síntomas:**
```
ConnectionError: HTTPSConnectionPool(host='mdm.company.com', port=443): Max retries exceeded
requests.exceptions.ConnectTimeout: HTTPSConnectionPool(host='glpi.company.com', port=443)
```

**Soluciones:**

1. **Verificar conectividad de red:**
```bash
# Ping al servidor
ping mdm.company.com
ping glpi.company.com

# Verificar puertos
telnet mdm.company.com 443
telnet glpi.company.com 443

# Usar curl para probar
curl -I https://mdm.company.com
curl -I https://glpi.company.com/apirest.php
```

2. **Verificar configuración de proxy:**
```yaml
# config.yaml
mdm:
  base_url: "https://mdm.company.com"
  proxy:
    http: "http://proxy.company.com:8080"
    https: "http://proxy.company.com:8080"

glpi:
  base_url: "https://glpi.company.com/apirest.php"
  proxy:
    http: "http://proxy.company.com:8080"
    https: "http://proxy.company.com:8080"
```

3. **Verificar certificados SSL:**
```bash
# Verificar certificado
openssl s_client -connect mdm.company.com:443 -servername mdm.company.com

# Si hay problemas con certificados, deshabilitar verificación temporalmente
# config.yaml
mdm:
  ssl_verify: false  # Solo para debugging
glpi:
  ssl_verify: false  # Solo para debugging
```

### Error: "SSL Certificate verification failed"

**Síntomas:**
```
SSLError: HTTPSConnectionPool(host='mdm.company.com', port=443): 
Max retries exceeded with url: /api/v1/devices 
(Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED]')))
```

**Soluciones:**

1. **Agregar certificados personalizados:**
```bash
# Descargar certificado
echo | openssl s_client -connect mdm.company.com:443 2>/dev/null | \
    openssl x509 -out mdm.crt

# Agregar al almacén de certificados
sudo cp mdm.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

2. **Configurar bundle de certificados:**
```yaml
# config.yaml
mdm:
  ssl_cert_path: "/path/to/custom-ca-bundle.crt"
glpi:
  ssl_cert_path: "/path/to/custom-ca-bundle.crt"
```

## 🔑 Problemas de Autenticación

### Error: "Invalid API Key" o "Unauthorized"

**Síntomas:**
```
HTTPError: 401 Client Error: Unauthorized for url: https://mdm.company.com/api/v1/devices
HTTPError: 401 Client Error: Unauthorized for url: https://glpi.company.com/apirest.php/initSession
```

**Soluciones:**

1. **Verificar credenciales MDM:**
```bash
# Probar API key manualmente
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://mdm.company.com/api/v1/devices

# Verificar formato de API key
echo $MDM_GLPI_MDM__API_KEY | wc -c  # Debe tener longitud esperada
```

2. **Verificar tokens GLPI:**
```bash
# Probar inicialización de sesión
curl -X GET \
  'https://glpi.company.com/apirest.php/initSession' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: user_token YOUR_USER_TOKEN' \
  -H 'App-Token: YOUR_APP_TOKEN'
```

3. **Regenerar credenciales:**
```bash
# Para MDM - generar nueva API key en la consola de administración
# Para GLPI - regenerar tokens en Configuración > General > API

# Actualizar variables de entorno
export MDM_GLPI_MDM__API_KEY="new_api_key"
export MDM_GLPI_GLPI__APP_TOKEN="new_app_token"
export MDM_GLPI_GLPI__USER_TOKEN="new_user_token"
```

### Error: "Session expired" (GLPI)

**Síntomas:**
```
HTTPError: 401 Client Error: Unauthorized
Response: {"ERROR": "session_token seems invalid"}
```

**Soluciones:**

1. **Verificar configuración de sesión:**
```yaml
# config.yaml
glpi:
  session_timeout: 1800  # 30 minutos
  max_session_retries: 3
```

2. **Forzar renovación de sesión:**
```bash
# Reiniciar aplicación para forzar nueva sesión
python cli.py restart

# O limpiar cache de sesión
rm -f data/glpi_session.cache
```

## 🗄️ Problemas de Base de Datos

### Error: "Connection to database failed"

**Síntomas:**
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) 
connection to server at "localhost" (127.0.0.1), port 5432 failed: 
Connection refused
```

**Soluciones:**

1. **Verificar estado de PostgreSQL:**
```bash
# Verificar si PostgreSQL está ejecutándose
sudo systemctl status postgresql

# Iniciar PostgreSQL si está parado
sudo systemctl start postgresql

# Verificar conectividad
psql -h localhost -U mdmglpi -d mdmglpi -c "SELECT 1;"
```

2. **Verificar configuración de conexión:**
```yaml
# config.yaml
database:
  url: "postgresql://mdmglpi:password@localhost:5432/mdmglpi"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30
```

3. **Verificar permisos de usuario:**
```sql
-- Conectar como superusuario
sudo -u postgres psql

-- Verificar usuario y permisos
\du mdmglpi

-- Otorgar permisos si es necesario
GRANT ALL PRIVILEGES ON DATABASE mdmglpi TO mdmglpi;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO mdmglpi;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO mdmglpi;
```

### Error: "Table doesn't exist"

**Síntomas:**
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedTable) 
relation "sync_records" does not exist
```

**Soluciones:**

1. **Crear tablas manualmente:**
```python
# Ejecutar en Python
from src.mdm_glpi_integration.models.database import create_tables
from src.mdm_glpi_integration.core.config import get_settings

settings = get_settings()
create_tables(settings.database.url)
```

2. **Verificar migración de esquema:**
```bash
# Si usas Alembic
alembic upgrade head

# O recrear todas las tablas
python -c "from src.mdm_glpi_integration.models.database import create_tables; create_tables()"
```

## 🔄 Problemas de Sincronización

### Error: "Sync failed with multiple errors"

**Síntomas:**
```
ERROR: Sync completed with errors: 15 devices failed
ERROR: Device sync failed: Device ID 12345 - HTTP 500 Internal Server Error
```

**Soluciones:**

1. **Verificar dispositivos fallidos:**
```bash
# Ver dispositivos con errores
curl http://localhost:8080/status/failed-devices

# Ver logs de sincronización específica
grep "sync_id: abc123" logs/mdm-glpi.log
```

2. **Reintentar dispositivos fallidos:**
```bash
# Reintentar todos los dispositivos fallidos
python cli.py sync --retry-failed

# Reintentar dispositivo específico
python cli.py sync --device-id 12345
```

3. **Ajustar configuración de reintentos:**
```yaml
# config.yaml
sync:
  max_retries: 5
  retry_delay: 30
  batch_size: 25  # Reducir si hay muchos errores
  
circuit_breaker:
  failure_threshold: 10
  recovery_timeout: 300
  expected_exception: "requests.exceptions.RequestException"
```

### Error: "Rate limit exceeded"

**Síntomas:**
```
HTTPError: 429 Client Error: Too Many Requests
ERROR: Rate limit exceeded, waiting 60 seconds
```

**Soluciones:**

1. **Ajustar límites de velocidad:**
```yaml
# config.yaml
connectors:
  mdm:
    rate_limit: 50      # Reducir requests por minuto
    rate_window: 60
  glpi:
    rate_limit: 30
    rate_window: 60

sync:
  batch_size: 10        # Procesar menos dispositivos por lote
  delay_between_batches: 5  # Pausa entre lotes
```

2. **Implementar backoff exponencial:**
```yaml
# config.yaml
retry:
  max_attempts: 5
  backoff_factor: 2
  max_delay: 300
```

### Error: "Device mapping conflict"

**Síntomas:**
```
ERROR: Device mapping conflict: MDM device 12345 already mapped to GLPI computer 67890
ERROR: Multiple GLPI computers found for device serial ABC123
```

**Soluciones:**

1. **Limpiar mapeos duplicados:**
```sql
-- Encontrar mapeos duplicados
SELECT mdm_device_id, COUNT(*) 
FROM device_mapping 
GROUP BY mdm_device_id 
HAVING COUNT(*) > 1;

-- Eliminar mapeos duplicados (mantener el más reciente)
DELETE FROM device_mapping 
WHERE id NOT IN (
    SELECT MAX(id) 
    FROM device_mapping 
    GROUP BY mdm_device_id
);
```

2. **Configurar estrategia de mapeo:**
```yaml
# config.yaml
mapping:
  strategy: "serial_number"  # o "name", "uuid"
  conflict_resolution: "update_existing"  # o "create_new", "skip"
  case_sensitive: false
```

## 📊 Problemas de Rendimiento

### Sincronización Lenta

**Síntomas:**
- Sincronización toma más de 1 hora
- Alto uso de CPU/memoria
- Timeouts frecuentes

**Soluciones:**

1. **Optimizar configuración:**
```yaml
# config.yaml
sync:
  batch_size: 100       # Aumentar tamaño de lote
  max_workers: 4        # Paralelización
  
database:
  pool_size: 20         # Más conexiones
  pool_timeout: 10
  
connectors:
  mdm:
    timeout: 15         # Reducir timeout
    connection_pool_size: 10
  glpi:
    timeout: 15
    session_pool_size: 5
```

2. **Optimizar base de datos:**
```sql
-- Crear índices faltantes
CREATE INDEX CONCURRENTLY idx_sync_records_device_timestamp 
ON sync_records(device_id, timestamp);

CREATE INDEX CONCURRENTLY idx_device_mapping_lookup 
ON device_mapping(mdm_device_id, glpi_computer_id);

-- Analizar estadísticas
ANALYZE;

-- Vacuum si es necesario
VACUUM ANALYZE;
```

3. **Monitorear recursos:**
```bash
# Monitorear uso de recursos
top -p $(pgrep -f "cli.py")
iotop -p $(pgrep -f "cli.py")

# Verificar conexiones de base de datos
psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='mdmglpi';"
```

### Alto Uso de Memoria

**Síntomas:**
```
MemoryError: Unable to allocate array
OOM Killer: Process killed due to memory usage
```

**Soluciones:**

1. **Reducir tamaño de lote:**
```yaml
# config.yaml
sync:
  batch_size: 25        # Reducir de 100 a 25
  stream_processing: true  # Procesar en streaming
```

2. **Configurar límites de memoria:**
```bash
# Systemd service
[Service]
MemoryLimit=512M
MemoryAccounting=true
```

3. **Optimizar consultas:**
```python
# Usar paginación en consultas grandes
devices = mdm_connector.get_devices(limit=100, offset=0)
while devices:
    process_devices(devices)
    offset += 100
    devices = mdm_connector.get_devices(limit=100, offset=offset)
```

## 🔧 Problemas de Configuración

### Error: "Configuration validation failed"

**Síntomas:**
```
ValidationError: 1 validation error for Settings
mdm -> api_key
  field required (type=value_error.missing)
```

**Soluciones:**

1. **Validar configuración:**
```bash
# Verificar sintaxis YAML
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Validar configuración completa
python cli.py config --validate

# Ver configuración actual
python cli.py config --show
```

2. **Verificar variables de entorno:**
```bash
# Listar variables relevantes
env | grep MDM_GLPI

# Verificar que no falten variables requeridas
echo "MDM API Key: ${MDM_GLPI_MDM__API_KEY:-NOT_SET}"
echo "GLPI App Token: ${MDM_GLPI_GLPI__APP_TOKEN:-NOT_SET}"
echo "GLPI User Token: ${MDM_GLPI_GLPI__USER_TOKEN:-NOT_SET}"
```

3. **Usar configuración de ejemplo:**
```bash
# Copiar configuración de ejemplo
cp config.example.yaml config.yaml

# Editar con valores correctos
vim config.yaml
```

### Error: "Invalid log level" o "Log file permission denied"

**Síntomas:**
```
ValueError: Invalid log level: DEBGU
PermissionError: [Errno 13] Permission denied: '/var/log/mdm-glpi.log'
```

**Soluciones:**

1. **Corregir nivel de log:**
```yaml
# config.yaml
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"  # json, console
```

2. **Corregir permisos de archivos:**
```bash
# Crear directorio de logs con permisos correctos
sudo mkdir -p /var/log/mdm-glpi
sudo chown mdmglpi:mdmglpi /var/log/mdm-glpi
sudo chmod 755 /var/log/mdm-glpi

# O usar directorio local
mkdir -p logs
chmod 755 logs
```

## 🚨 Problemas de Monitoreo

### Métricas no Disponibles

**Síntomas:**
- Endpoint `/metrics` devuelve 404
- Prometheus no puede scrape métricas
- Grafana muestra "No data"

**Soluciones:**

1. **Verificar configuración de monitoreo:**
```yaml
# config.yaml
monitoring:
  enable_metrics: true
  port: 8080
  host: "0.0.0.0"
  metrics_path: "/metrics"
```

2. **Verificar endpoint:**
```bash
# Probar endpoint localmente
curl http://localhost:8080/metrics
curl http://localhost:8080/health

# Verificar que el puerto esté abierto
netstat -tlnp | grep 8080
```

3. **Verificar configuración de Prometheus:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'mdm-glpi'
    static_configs:
      - targets: ['localhost:8080']  # Verificar host:puerto correcto
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Health Checks Fallan

**Síntomas:**
```
HTTPError: 503 Service Unavailable
{"status": "unhealthy", "checks": {"database": false, "mdm": false}}
```

**Soluciones:**

1. **Verificar componentes individualmente:**
```bash
# Verificar base de datos
psql -h localhost -U mdmglpi -d mdmglpi -c "SELECT 1;"

# Verificar MDM
curl -H "Authorization: Bearer $MDM_API_KEY" https://mdm.company.com/api/v1/health

# Verificar GLPI
curl https://glpi.company.com/apirest.php
```

2. **Ajustar timeouts de health check:**
```yaml
# config.yaml
health_check:
  timeout: 10
  interval: 30
  retries: 3
```

## 🔄 Procedimientos de Recuperación

### Recuperación de Sincronización Fallida

```bash
#!/bin/bash
# recovery.sh

echo "Iniciando recuperación de sincronización..."

# 1. Verificar estado del sistema
python cli.py health
if [ $? -ne 0 ]; then
    echo "Sistema no saludable, verificando componentes..."
    python cli.py test-connections
fi

# 2. Limpiar locks de sincronización
psql -d mdmglpi -c "DELETE FROM sync_locks WHERE created_at < NOW() - INTERVAL '1 hour';"

# 3. Reintentar dispositivos fallidos
python cli.py sync --retry-failed

# 4. Si falla, ejecutar sincronización incremental
if [ $? -ne 0 ]; then
    echo "Reintento fallido, ejecutando sync incremental..."
    python cli.py sync --incremental
fi

# 5. Verificar resultados
python cli.py status

echo "Recuperación completada"
```

### Recuperación de Base de Datos

```bash
#!/bin/bash
# db_recovery.sh

echo "Iniciando recuperación de base de datos..."

# 1. Backup actual
pg_dump mdmglpi > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Verificar integridad
psql -d mdmglpi -c "SELECT count(*) FROM sync_records;"
psql -d mdmglpi -c "SELECT count(*) FROM device_mapping;"

# 3. Limpiar registros corruptos
psql -d mdmglpi -c "DELETE FROM sync_records WHERE device_id IS NULL;"
psql -d mdmglpi -c "DELETE FROM device_mapping WHERE mdm_device_id IS NULL;"

# 4. Reindexar
psql -d mdmglpi -c "REINDEX DATABASE mdmglpi;"

# 5. Actualizar estadísticas
psql -d mdmglpi -c "ANALYZE;"

echo "Recuperación de BD completada"
```

### Rollback de Configuración

```bash
#!/bin/bash
# config_rollback.sh

echo "Realizando rollback de configuración..."

# 1. Backup configuración actual
cp config.yaml config.yaml.backup.$(date +%Y%m%d_%H%M%S)

# 2. Restaurar configuración anterior
if [ -f config.yaml.backup ]; then
    cp config.yaml.backup config.yaml
    echo "Configuración restaurada desde backup"
else
    cp config.example.yaml config.yaml
    echo "Configuración restaurada desde ejemplo"
fi

# 3. Validar configuración
python cli.py config --validate

# 4. Reiniciar servicio
sudo systemctl restart mdm-glpi-integration

# 5. Verificar estado
sleep 10
python cli.py health

echo "Rollback completado"
```

## 📞 Contacto y Soporte

### Información para Reportar Problemas

Cuando reportes un problema, incluye:

1. **Información del sistema:**
```bash
python cli.py version
python cli.py info
uname -a
python --version
```

2. **Logs relevantes:**
```bash
# Últimos 100 líneas de logs
tail -100 logs/mdm-glpi.log

# Logs de error específicos
grep -A5 -B5 "ERROR" logs/mdm-glpi.log | tail -50
```

3. **Configuración (sin credenciales):**
```bash
# Configuración sanitizada
python cli.py config --show --sanitize
```

4. **Estado del sistema:**
```bash
python cli.py health
python cli.py status
curl http://localhost:8080/metrics | grep -E "(error|failed)"
```

### Canales de Soporte

- **Documentación:** [docs/](./)
- **Issues:** GitHub Issues
- **Email:** soporte@company.com
- **Slack:** #mdm-glpi-integration

### Escalación

1. **Nivel 1:** Problemas de configuración y uso básico
2. **Nivel 2:** Problemas de integración y rendimiento
3. **Nivel 3:** Problemas de arquitectura y desarrollo

---

**Nota:** Esta guía se actualiza regularmente. Para la versión más reciente, consulta la documentación en línea.