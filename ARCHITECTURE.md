# Arquitectura del Sistema: Integración MDM-GLPI

## Visión General

El sistema de integración MDM-GLPI es una aplicación Python que sincroniza dispositivos móviles desde ManageEngine MDM hacia GLPI, centralizando el inventario de dispositivos.

## Principios de Diseño

### 1. Separación de Responsabilidades
- Cada componente tiene una responsabilidad específica y bien definida
- Bajo acoplamiento entre módulos
- Alta cohesión dentro de cada módulo

### 2. Configurabilidad
- Toda la configuración externa en archivos JSON/YAML
- Diferentes perfiles de configuración (desarrollo, producción)
- Validación de configuración al inicio

### 3. Observabilidad
- Logging estructurado con diferentes niveles
- Métricas de rendimiento y errores
- Trazabilidad de operaciones

### 4. Resiliencia
- Manejo robusto de errores
- Reintentos con backoff exponencial
- Circuit breaker para APIs externas

## Arquitectura de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                    MDM-GLPI Integration                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    │
│  │   Scheduler │    │ Sync Service │    │ Config Mgr  │    │
│  │             │───▶│              │◄───│             │    │
│  └─────────────┘    └──────┬───────┘    └─────────────┘    │
│                             │                               │
│  ┌─────────────┐    ┌──────▼───────┐    ┌─────────────┐    │
│  │ MDM Connector│    │ Data Mapper  │    │GLPI Connector│   │
│  │             │───▶│              │───▶│             │    │
│  └─────────────┘    └──────────────┘    └─────────────┘    │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    │
│  │   Logger    │    │ Cache/Store  │    │Error Handler│    │
│  │             │    │              │    │             │    │
│  └─────────────┘    └──────────────┘    └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Descripción de Componentes

### 1. Scheduler
**Responsabilidad**: Programación y ejecución de tareas de sincronización

**Funcionalidades**:
- Sincronización completa (diaria)
- Sincronización incremental (cada 15 minutos)
- Sincronización manual bajo demanda
- Gestión de trabajos concurrentes

**Tecnología**: APScheduler

### 2. Sync Service
**Responsabilidad**: Orquestación del proceso de sincronización

**Funcionalidades**:
- Coordinación entre conectores
- Gestión del flujo de datos
- Manejo de transacciones
- Control de concurrencia

**Patrones**:
- Command Pattern para operaciones
- Observer Pattern para eventos

### 3. MDM Connector
**Responsabilidad**: Comunicación con ManageEngine MDM API

**Funcionalidades**:
- Autenticación con MDM
- Obtención de dispositivos
- Obtención de usuarios y grupos
- Manejo de paginación
- Rate limiting

**Endpoints utilizados**:
```python
GET /api/v1/mdm/devices
GET /api/v1/mdm/devices/{device_id}
GET /api/v1/mdm/users
GET /api/v1/mdm/groups
GET /api/v1/mdm/apps/{device_id}
```

### 4. GLPI Connector
**Responsabilidad**: Comunicación con GLPI API

**Funcionalidades**:
- Autenticación con GLPI
- CRUD de dispositivos (Computer/Phone)
- CRUD de usuarios
- Gestión de relaciones
- Búsqueda por criterios

**Endpoints utilizados**:
```python
POST /apirest.php/initSession
GET /apirest.php/Computer
POST /apirest.php/Computer
PUT /apirest.php/Computer/{id}
GET /apirest.php/Phone
POST /apirest.php/Phone
```

### 5. Data Mapper
**Responsabilidad**: Transformación de datos entre sistemas

**Funcionalidades**:
- Mapeo de campos MDM → GLPI
- Validación de datos
- Normalización de valores
- Resolución de conflictos

**Mapeos principales**:
```python
mdm_device = {
    "device_id": "12345",
    "device_name": "iPhone 13",
    "model": "iPhone13,2",
    "os_version": "15.6",
    "user_email": "user@company.com"
}

glpi_computer = {
    "name": "iPhone 13",
    "computermodels_id": 15,
    "operatingsystems_id": 8,
    "operatingsystemversions_id": 45,
    "users_id": 123
}
```

### 6. Config Manager
**Responsabilidad**: Gestión de configuración del sistema

**Funcionalidades**:
- Carga de configuración desde archivos
- Validación de parámetros
- Gestión de credenciales
- Configuración por entorno

**Estructura de configuración**:
```yaml
mdm:
  base_url: "https://mdm.company.com"
  api_key: "${MDM_API_KEY}"
  timeout: 30
  rate_limit: 100

glpi:
  base_url: "https://glpi.company.com"
  app_token: "${GLPI_APP_TOKEN}"
  user_token: "${GLPI_USER_TOKEN}"
  timeout: 30

sync:
  full_sync_cron: "0 2 * * *"
  incremental_sync_cron: "*/15 * * * *"
  batch_size: 100
  max_retries: 3
```

### 7. Logger
**Responsabilidad**: Sistema de logging estructurado

**Funcionalidades**:
- Logs estructurados en JSON
- Diferentes niveles (DEBUG, INFO, WARN, ERROR)
- Rotación de archivos
- Correlación de requests

### 8. Cache/Store
**Responsabilidad**: Almacenamiento local y cache

**Funcionalidades**:
- Cache de respuestas de API
- Almacenamiento de mapeos ID
- Historial de sincronizaciones
- Estado de dispositivos

**Esquema de base de datos**:
```sql
CREATE TABLE devices (
    id INTEGER PRIMARY KEY,
    mdm_id VARCHAR(255) UNIQUE,
    glpi_id INTEGER,
    device_data JSON,
    last_sync TIMESTAMP,
    sync_status VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE sync_logs (
    id INTEGER PRIMARY KEY,
    sync_type VARCHAR(50),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    devices_processed INTEGER,
    devices_success INTEGER,
    devices_error INTEGER,
    status VARCHAR(50),
    error_details TEXT
);
```

## Patrones de Diseño Utilizados

### 1. Repository Pattern
```python
class DeviceRepository:
    def find_by_mdm_id(self, mdm_id: str) -> Optional[Device]:
        pass
    
    def save(self, device: Device) -> Device:
        pass
    
    def find_all_pending_sync(self) -> List[Device]:
        pass
```

### 2. Factory Pattern
```python
class ConnectorFactory:
    @staticmethod
    def create_mdm_connector(config: Config) -> MDMConnector:
        return ManageEngineMDMConnector(config.mdm)
    
    @staticmethod
    def create_glpi_connector(config: Config) -> GLPIConnector:
        return GLPIRestConnector(config.glpi)
```

### 3. Strategy Pattern
```python
class SyncStrategy(ABC):
    @abstractmethod
    def sync(self, devices: List[Device]) -> SyncResult:
        pass

class FullSyncStrategy(SyncStrategy):
    def sync(self, devices: List[Device]) -> SyncResult:
        # Implementación de sincronización completa
        pass

class IncrementalSyncStrategy(SyncStrategy):
    def sync(self, devices: List[Device]) -> SyncResult:
        # Implementación de sincronización incremental
        pass
```

### 4. Observer Pattern
```python
class SyncEventObserver(ABC):
    @abstractmethod
    def on_sync_started(self, event: SyncStartedEvent):
        pass
    
    @abstractmethod
    def on_sync_completed(self, event: SyncCompletedEvent):
        pass

class LoggingObserver(SyncEventObserver):
    def on_sync_started(self, event: SyncStartedEvent):
        logger.info(f"Sync started: {event.sync_type}")
```

## Flujo de Datos

### Sincronización Completa
```
1. Scheduler → Trigger Full Sync
2. Sync Service → Get all devices from MDM
3. MDM Connector → Fetch devices (paginated)
4. Data Mapper → Transform MDM data to GLPI format
5. GLPI Connector → Create/Update devices in GLPI
6. Cache/Store → Update local mappings
7. Logger → Record sync results
```

### Sincronización Incremental
```
1. Scheduler → Trigger Incremental Sync
2. Sync Service → Get devices modified since last sync
3. MDM Connector → Fetch modified devices
4. Data Mapper → Transform and detect changes
5. GLPI Connector → Update only changed devices
6. Cache/Store → Update timestamps and mappings
7. Logger → Record incremental results
```

## Manejo de Errores

### Estrategias de Retry
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(requests.RequestException)
)
def api_call(self, endpoint: str) -> dict:
    # Implementación de llamada API
    pass
```

### Circuit Breaker
```python
class APICircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
```

## Seguridad

### Gestión de Credenciales
- Variables de entorno para credenciales sensibles
- Encriptación de tokens en configuración
- Rotación automática de tokens cuando sea posible

### Validación de Datos
```python
from pydantic import BaseModel, validator

class DeviceModel(BaseModel):
    mdm_id: str
    name: str
    model: Optional[str]
    os_version: Optional[str]
    
    @validator('mdm_id')
    def validate_mdm_id(cls, v):
        if not v or len(v) < 3:
            raise ValueError('MDM ID must be at least 3 characters')
        return v
```

## Monitoreo y Métricas

### Métricas Clave
- Dispositivos sincronizados por minuto
- Tasa de errores de API
- Tiempo de respuesta de APIs
- Uso de memoria y CPU
- Tamaño de cola de sincronización

### Health Checks
```python
class HealthChecker:
    def check_mdm_connectivity(self) -> bool:
        # Verificar conectividad con MDM
        pass
    
    def check_glpi_connectivity(self) -> bool:
        # Verificar conectividad con GLPI
        pass
    
    def check_database_health(self) -> bool:
        # Verificar estado de base de datos local
        pass
```

## Escalabilidad

### Procesamiento en Lotes
- Procesamiento de dispositivos en lotes de 100
- Paralelización de llamadas API cuando sea posible
- Queue-based processing para grandes volúmenes

### Optimizaciones
- Cache de metadatos (modelos, usuarios, grupos)
- Compresión de respuestas API
- Conexiones persistentes HTTP
- Índices en base de datos local

## Deployment

### Containerización
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "mdm_glpi_integration"]
```

### Configuración de Entorno
```yaml
# docker-compose.yml
version: '3.8'
services:
  mdm-glpi-sync:
    build: .
    environment:
      - MDM_API_KEY=${MDM_API_KEY}
      - GLPI_APP_TOKEN=${GLPI_APP_TOKEN}
      - GLPI_USER_TOKEN=${GLPI_USER_TOKEN}
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./data:/app/data
```