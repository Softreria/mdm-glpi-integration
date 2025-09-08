# Guía de Configuración

Esta guía detalla todas las opciones de configuración disponibles para la integración MDM-GLPI.

## 📁 Archivos de Configuración

### Archivo Principal: `config.yaml`

El archivo principal de configuración debe estar en la raíz del proyecto. Puedes usar `config.example.yaml` como plantilla.

### Variables de Entorno

Todas las configuraciones pueden ser sobrescritas usando variables de entorno con el prefijo `MDM_GLPI_`:

```bash
export MDM_GLPI_MDM__API_KEY="your-api-key"
export MDM_GLPI_GLPI__BASE_URL="https://your-glpi.com/apirest.php"
export MDM_GLPI_DATABASE__URL="postgresql://user:pass@localhost/db"
```

## 🔧 Secciones de Configuración

### 1. Configuración MDM

```yaml
mdm:
  base_url: "https://your-mdm.manageengine.com"  # URL base del MDM
  api_key: "your-api-key"                        # API Key del MDM
  timeout: 30                                     # Timeout en segundos
  rate_limit: 100                                 # Límite de requests por minuto
  ssl_verify: true                                # Verificar certificados SSL
  retry_attempts: 3                               # Intentos de reintento
  retry_delay: 1.0                                # Delay entre reintentos (segundos)
```

#### Parámetros MDM

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `base_url` | string | ✅ | - | URL base de la API de ManageEngine MDM |
| `api_key` | string | ✅ | - | Clave de API para autenticación |
| `timeout` | int | ❌ | 30 | Timeout para requests HTTP (segundos) |
| `rate_limit` | int | ❌ | 100 | Límite de requests por minuto |
| `ssl_verify` | bool | ❌ | true | Verificar certificados SSL |
| `retry_attempts` | int | ❌ | 3 | Número de reintentos en caso de error |
| `retry_delay` | float | ❌ | 1.0 | Delay entre reintentos (segundos) |

### 2. Configuración GLPI

```yaml
glpi:
  base_url: "https://your-glpi.com/apirest.php"   # URL de la API REST de GLPI
  app_token: "your-app-token"                     # Token de aplicación
  user_token: "your-user-token"                   # Token de usuario
  timeout: 30                                     # Timeout en segundos
  ssl_verify: true                                # Verificar certificados SSL
  retry_attempts: 3                               # Intentos de reintento
  retry_delay: 1.0                                # Delay entre reintentos
  session_timeout: 3600                           # Timeout de sesión (segundos)
```

#### Parámetros GLPI

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `base_url` | string | ✅ | - | URL de la API REST de GLPI |
| `app_token` | string | ✅ | - | Token de aplicación GLPI |
| `user_token` | string | ✅ | - | Token de usuario GLPI |
| `timeout` | int | ❌ | 30 | Timeout para requests HTTP |
| `ssl_verify` | bool | ❌ | true | Verificar certificados SSL |
| `retry_attempts` | int | ❌ | 3 | Número de reintentos |
| `retry_delay` | float | ❌ | 1.0 | Delay entre reintentos |
| `session_timeout` | int | ❌ | 3600 | Timeout de sesión GLPI |

### 3. Configuración de Sincronización

```yaml
sync:
  # Programación
  schedule_full: "0 2 * * *"          # Cron para sync completa (diario 2 AM)
  schedule_incremental: "*/15 * * * *" # Cron para sync incremental (cada 15 min)
  schedule_cleanup: "0 3 * * 0"        # Cron para limpieza (domingos 3 AM)
  
  # Comportamiento
  batch_size: 50                       # Dispositivos por lote
  max_retries: 3                       # Reintentos por dispositivo
  initial_sync: true                   # Ejecutar sync inicial al arrancar
  
  # Filtros
  device_filters:
    status: ["active", "inactive"]     # Estados a sincronizar
    os_types: ["ios", "android"]       # Tipos de OS a incluir
    min_last_seen_days: 30             # Días mínimos desde última conexión
  
  # Mapeo de campos
  field_mapping:
    device_name: "name"                # Campo nombre en GLPI
    serial_number: "serial"            # Campo serie en GLPI
    model: "computermodels_id"         # Campo modelo en GLPI
```

#### Parámetros de Sincronización

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `schedule_full` | string | "0 2 * * *" | Expresión cron para sincronización completa |
| `schedule_incremental` | string | "*/15 * * * *" | Expresión cron para sincronización incremental |
| `schedule_cleanup` | string | "0 3 * * 0" | Expresión cron para limpieza de logs |
| `batch_size` | int | 50 | Número de dispositivos a procesar por lote |
| `max_retries` | int | 3 | Reintentos máximos por dispositivo fallido |
| `initial_sync` | bool | true | Ejecutar sincronización inicial al arrancar |

### 4. Configuración de Base de Datos

```yaml
database:
  url: "sqlite:///data/mdm_glpi.db"    # URL de conexión
  echo: false                          # Log de queries SQL
  pool_size: 5                         # Tamaño del pool de conexiones
  max_overflow: 10                     # Conexiones adicionales permitidas
  pool_timeout: 30                     # Timeout para obtener conexión
  pool_recycle: 3600                   # Reciclar conexiones (segundos)
```

#### URLs de Base de Datos Soportadas

```yaml
# SQLite (desarrollo)
database:
  url: "sqlite:///data/mdm_glpi.db"

# PostgreSQL (recomendado para producción)
database:
  url: "postgresql://user:password@localhost:5432/mdm_glpi"

# MySQL/MariaDB
database:
  url: "mysql+pymysql://user:password@localhost:3306/mdm_glpi"

# SQL Server
database:
  url: "mssql+pyodbc://user:password@localhost/mdm_glpi?driver=ODBC+Driver+17+for+SQL+Server"
```

### 5. Configuración de Logging

```yaml
logging:
  level: "INFO"                        # Nivel de logging
  format: "json"                       # Formato: json o console
  file: "logs/mdm-glpi.log"            # Archivo de log
  max_size: "10MB"                     # Tamaño máximo por archivo
  backup_count: 5                      # Archivos de backup a mantener
  
  # Configuración por módulo
  loggers:
    "mdm_glpi_integration.connectors": "DEBUG"
    "mdm_glpi_integration.services": "INFO"
    "sqlalchemy.engine": "WARNING"
```

#### Niveles de Logging

- `DEBUG`: Información muy detallada para debugging
- `INFO`: Información general de operaciones
- `WARNING`: Advertencias que no impiden el funcionamiento
- `ERROR`: Errores que impiden operaciones específicas
- `CRITICAL`: Errores críticos que pueden detener la aplicación

### 6. Configuración de Monitoreo

```yaml
monitoring:
  enable_metrics: true                 # Habilitar métricas Prometheus
  port: 8080                          # Puerto para API y métricas
  host: "0.0.0.0"                     # Host para bind del servidor
  
  # Health checks
  health_check_interval: 60           # Intervalo de health checks (segundos)
  
  # Métricas
  metrics_retention_days: 30          # Días de retención de métricas
  
  # Alertas (futuro)
  alerts:
    sync_failure_threshold: 5         # Fallos consecutivos para alerta
    response_time_threshold: 5000     # Tiempo de respuesta límite (ms)
```

## 🔒 Configuración de Seguridad

### Gestión de Secretos

#### 1. Variables de Entorno (Recomendado)

```bash
# .env file
MDM_GLPI_MDM__API_KEY=your-secret-api-key
MDM_GLPI_GLPI__APP_TOKEN=your-secret-app-token
MDM_GLPI_GLPI__USER_TOKEN=your-secret-user-token
MDM_GLPI_DATABASE__URL=postgresql://user:pass@localhost/db
```

#### 2. Archivos de Secretos

```yaml
# config.yaml
mdm:
  api_key_file: "/run/secrets/mdm_api_key"
  
glpi:
  app_token_file: "/run/secrets/glpi_app_token"
  user_token_file: "/run/secrets/glpi_user_token"
```

#### 3. Integración con Gestores de Secretos

```yaml
# Para AWS Secrets Manager
secrets:
  provider: "aws"
  region: "us-east-1"
  mdm_secret_name: "mdm-glpi/mdm-credentials"
  glpi_secret_name: "mdm-glpi/glpi-credentials"

# Para HashiCorp Vault
secrets:
  provider: "vault"
  url: "https://vault.company.com"
  token_file: "/var/run/secrets/vault-token"
  secret_path: "secret/mdm-glpi"
```

## 🌍 Configuración por Entorno

### Desarrollo

```yaml
# config.dev.yaml
logging:
  level: "DEBUG"
  format: "console"
  
database:
  url: "sqlite:///dev.db"
  echo: true
  
monitoring:
  enable_metrics: false
```

### Testing

```yaml
# config.test.yaml
logging:
  level: "WARNING"
  
database:
  url: "sqlite:///:memory:"
  
sync:
  batch_size: 5
  max_retries: 1
```

### Producción

```yaml
# config.prod.yaml
logging:
  level: "INFO"
  format: "json"
  file: "/var/log/mdm-glpi/app.log"
  
database:
  url: "postgresql://mdm_glpi:${DB_PASSWORD}@db:5432/mdm_glpi"
  pool_size: 10
  max_overflow: 20
  
monitoring:
  enable_metrics: true
  host: "0.0.0.0"
  port: 8080
```

## 🔧 Configuración Avanzada

### Personalización de Mapeo de Campos

```yaml
sync:
  field_mapping:
    # Mapeo básico
    device_name: "name"
    serial_number: "serial"
    
    # Mapeo con transformación
    model:
      target_field: "computermodels_id"
      transform: "lookup_model_id"
      default: 1
    
    # Campos calculados
    location:
      target_field: "locations_id"
      source: "user.department"
      transform: "lookup_location_by_department"
    
    # Campos personalizados
    custom_fields:
      mdm_device_id: "device_id"
      last_mdm_sync: "last_seen"
      mdm_enrollment_date: "enrollment_date"
```

### Configuración de Filtros Avanzados

```yaml
sync:
  device_filters:
    # Filtros básicos
    status: ["active", "inactive"]
    os_types: ["ios", "android"]
    
    # Filtros por fecha
    min_last_seen_days: 30
    max_enrollment_age_days: 365
    
    # Filtros por usuario
    user_filters:
      departments: ["IT", "Sales", "Marketing"]
      exclude_test_users: true
    
    # Filtros personalizados
    custom_filters:
      - field: "storage_total"
        operator: ">"
        value: 16000  # Más de 16GB
      - field: "is_supervised"
        operator: "=="
        value: true
```

### Configuración de Reintentos y Circuit Breaker

```yaml
connectors:
  circuit_breaker:
    failure_threshold: 5              # Fallos antes de abrir circuito
    recovery_timeout: 60              # Tiempo antes de intentar recuperación
    expected_exception: ["ConnectionError", "TimeoutError"]
  
  retry_policy:
    max_attempts: 3
    backoff_strategy: "exponential"   # linear, exponential, fixed
    base_delay: 1.0
    max_delay: 60.0
    jitter: true                      # Añadir variación aleatoria
```

## 📊 Configuración de Métricas

```yaml
monitoring:
  metrics:
    # Métricas de aplicación
    app_metrics:
      - sync_duration_seconds
      - devices_processed_total
      - sync_errors_total
      - api_requests_total
    
    # Métricas de sistema
    system_metrics:
      - memory_usage_bytes
      - cpu_usage_percent
      - disk_usage_bytes
    
    # Métricas personalizadas
    custom_metrics:
      - name: "device_types_distribution"
        type: "gauge"
        labels: ["os_type", "manufacturer"]
      - name: "sync_lag_seconds"
        type: "histogram"
        buckets: [1, 5, 10, 30, 60, 300]
```

## ✅ Validación de Configuración

### Comando de Validación

```bash
# Validar configuración
python cli.py validate-config

# Validar configuración específica
python cli.py validate-config --config config.prod.yaml

# Mostrar configuración efectiva
python cli.py show-config
```

### Esquema de Validación

La aplicación valida automáticamente la configuración al arrancar usando esquemas Pydantic. Los errores de validación se muestran claramente:

```
❌ Error de configuración:
  - mdm.api_key: Campo requerido
  - database.url: URL de base de datos inválida
  - sync.batch_size: Debe ser mayor que 0
```

## 🔄 Recarga de Configuración

La aplicación soporta recarga de configuración en caliente:

```bash
# Enviar señal para recargar configuración
kill -HUP <pid>

# O usando la API
curl -X POST http://localhost:8080/admin/reload-config
```

**Nota**: Algunos cambios requieren reinicio completo (como cambios de base de datos).

## 📝 Ejemplos de Configuración Completa

Ver el directorio [`examples/`](../examples/) para configuraciones completas de ejemplo para diferentes escenarios de uso.