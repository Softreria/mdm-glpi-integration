# API Reference

Documentación completa de la API REST de la integración MDM-GLPI.

## 📋 Información General

- **Base URL**: `http://localhost:8080` (configurable)
- **Formato**: JSON
- **Autenticación**: No requerida (configurar según necesidades)
- **Rate Limiting**: Configurable por IP

## 🔍 Health & Status

### GET /health

Verificación rápida del estado de salud del sistema.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-20T10:30:00Z",
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

**Status Codes:**
- `200`: Sistema saludable
- `503`: Sistema con problemas

### GET /ready

Verifica si el sistema está listo para recibir requests.

**Response:**
```json
{
  "ready": true,
  "components": {
    "database": "ready",
    "mdm_connector": "ready",
    "glpi_connector": "ready"
  }
}
```

### GET /live

Liveness probe para Kubernetes.

**Response:**
```json
{
  "alive": true
}
```

## 📊 Status Detallado

### GET /status

Estado detallado del sistema y todos sus componentes.

**Response:**
```json
{
  "overall_status": "healthy",
  "timestamp": "2024-01-20T10:30:00Z",
  "components": {
    "mdm": {
      "status": "healthy",
      "response_time": 150.5,
      "last_check": "2024-01-20T10:29:45Z",
      "message": "Connection successful"
    },
    "glpi": {
      "status": "healthy",
      "response_time": 89.2,
      "last_check": "2024-01-20T10:29:45Z",
      "message": "API accessible"
    },
    "database": {
      "status": "healthy",
      "response_time": 5.1,
      "last_check": "2024-01-20T10:29:45Z",
      "message": "Database responsive"
    },
    "system": {
      "status": "healthy",
      "memory_usage_percent": 45.2,
      "cpu_usage_percent": 12.8,
      "disk_usage_percent": 67.3
    }
  },
  "last_sync": {
    "type": "incremental",
    "timestamp": "2024-01-20T10:15:00Z",
    "status": "completed",
    "devices_processed": 25,
    "duration_seconds": 45.2
  }
}
```

### GET /status/failed-devices

Lista de dispositivos que fallaron en la última sincronización.

**Query Parameters:**
- `limit` (int): Número máximo de resultados (default: 50)
- `offset` (int): Offset para paginación (default: 0)

**Response:**
```json
{
  "failed_devices": [
    {
      "device_id": "MDM123456",
      "device_name": "iPhone de Juan",
      "error_message": "GLPI API timeout",
      "last_attempt": "2024-01-20T10:15:30Z",
      "retry_count": 2,
      "next_retry": "2024-01-20T10:45:30Z"
    }
  ],
  "total_count": 1,
  "pagination": {
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

## 🔄 Sincronización

### POST /sync/full

Ejecuta una sincronización completa de todos los dispositivos.

**Request Body:**
```json
{
  "force": false,
  "batch_size": 50,
  "filters": {
    "status": ["active"],
    "os_types": ["ios", "android"]
  }
}
```

**Response:**
```json
{
  "sync_id": "sync_20240120_103000",
  "status": "started",
  "message": "Full synchronization started",
  "estimated_duration_seconds": 300,
  "estimated_devices": 150
}
```

**Status Codes:**
- `202`: Sincronización iniciada
- `409`: Ya hay una sincronización en progreso
- `503`: Sistema no disponible

### POST /sync/incremental

Ejecuta una sincronización incremental (solo cambios recientes).

**Request Body:**
```json
{
  "since": "2024-01-20T09:00:00Z",
  "batch_size": 25
}
```

**Response:**
```json
{
  "sync_id": "sync_20240120_103000_inc",
  "status": "started",
  "message": "Incremental synchronization started",
  "estimated_duration_seconds": 60,
  "estimated_devices": 25
}
```

### POST /sync/manual

Sincronización manual con filtros específicos.

**Request Body:**
```json
{
  "device_ids": ["MDM123456", "MDM789012"],
  "force_update": true,
  "dry_run": false
}
```

**Response:**
```json
{
  "sync_id": "sync_manual_20240120_103000",
  "status": "started",
  "devices_to_process": 2,
  "message": "Manual synchronization started"
}
```

### POST /sync/retry-failed

Reintenta la sincronización de dispositivos que fallaron.

**Request Body:**
```json
{
  "max_retry_count": 3,
  "reset_retry_count": false
}
```

**Response:**
```json
{
  "sync_id": "retry_20240120_103000",
  "status": "started",
  "failed_devices_count": 5,
  "message": "Retrying failed devices"
}
```

### GET /sync/status/{sync_id}

Obtiene el estado de una sincronización específica.

**Response:**
```json
{
  "sync_id": "sync_20240120_103000",
  "type": "full",
  "status": "in_progress",
  "started_at": "2024-01-20T10:30:00Z",
  "progress": {
    "devices_processed": 75,
    "devices_total": 150,
    "percentage": 50.0,
    "current_batch": 3,
    "total_batches": 6
  },
  "results": {
    "devices_synced": 70,
    "devices_created": 15,
    "devices_updated": 55,
    "devices_failed": 5,
    "errors": [
      {
        "device_id": "MDM999999",
        "error": "GLPI API timeout",
        "timestamp": "2024-01-20T10:32:15Z"
      }
    ]
  },
  "estimated_completion": "2024-01-20T10:35:00Z"
}
```

## 📈 Métricas

### GET /metrics

Métricas en formato Prometheus.

**Response:**
```
# HELP mdm_glpi_sync_total Total number of synchronizations
# TYPE mdm_glpi_sync_total counter
mdm_glpi_sync_total{type="full"} 5
mdm_glpi_sync_total{type="incremental"} 48

# HELP mdm_glpi_devices_processed_total Total devices processed
# TYPE mdm_glpi_devices_processed_total counter
mdm_glpi_devices_processed_total 1250

# HELP mdm_glpi_sync_duration_seconds Time spent on synchronization
# TYPE mdm_glpi_sync_duration_seconds histogram
mdm_glpi_sync_duration_seconds_bucket{le="10"} 15
mdm_glpi_sync_duration_seconds_bucket{le="30"} 35
mdm_glpi_sync_duration_seconds_bucket{le="60"} 45
mdm_glpi_sync_duration_seconds_bucket{le="+Inf"} 48
mdm_glpi_sync_duration_seconds_sum 1456.7
mdm_glpi_sync_duration_seconds_count 48

# HELP mdm_glpi_api_requests_total Total API requests
# TYPE mdm_glpi_api_requests_total counter
mdm_glpi_api_requests_total{service="mdm",status="success"} 1205
mdm_glpi_api_requests_total{service="mdm",status="error"} 15
mdm_glpi_api_requests_total{service="glpi",status="success"} 1180
mdm_glpi_api_requests_total{service="glpi",status="error"} 8
```

### GET /metrics/summary

Resumen de métricas en formato JSON.

**Response:**
```json
{
  "synchronization": {
    "total_syncs": 53,
    "full_syncs": 5,
    "incremental_syncs": 48,
    "average_duration_seconds": 30.3,
    "last_sync": "2024-01-20T10:15:00Z"
  },
  "devices": {
    "total_processed": 1250,
    "total_created": 150,
    "total_updated": 1050,
    "total_failed": 50,
    "success_rate_percent": 96.0
  },
  "api_performance": {
    "mdm_avg_response_time_ms": 145.2,
    "glpi_avg_response_time_ms": 89.7,
    "mdm_success_rate_percent": 98.8,
    "glpi_success_rate_percent": 99.3
  },
  "system": {
    "uptime_seconds": 86400,
    "memory_usage_percent": 45.2,
    "cpu_usage_percent": 12.8
  }
}
```

## ℹ️ Información del Sistema

### GET /version

Información de versión de la aplicación.

**Response:**
```json
{
  "version": "1.0.0",
  "build_date": "2024-01-15T12:00:00Z",
  "git_commit": "abc123def456",
  "python_version": "3.9.7",
  "dependencies": {
    "fastapi": "0.104.1",
    "sqlalchemy": "2.0.23",
    "aiohttp": "3.9.1"
  }
}
```

### GET /info

Información general del sistema.

**Response:**
```json
{
  "application": "MDM-GLPI Integration",
  "version": "1.0.0",
  "environment": "production",
  "started_at": "2024-01-20T09:00:00Z",
  "configuration": {
    "mdm_url": "https://mdm.company.com",
    "glpi_url": "https://glpi.company.com/apirest.php",
    "database_type": "postgresql",
    "monitoring_enabled": true,
    "sync_schedules": {
      "full": "0 2 * * *",
      "incremental": "*/15 * * * *"
    }
  },
  "features": {
    "metrics": true,
    "health_checks": true,
    "api_rate_limiting": true,
    "automatic_retry": true
  }
}
```

## 🔧 Administración

### POST /admin/cleanup-logs

Limpia logs antiguos del sistema.

**Request Body:**
```json
{
  "retention_days": 30,
  "dry_run": false
}
```

**Response:**
```json
{
  "message": "Log cleanup completed",
  "logs_deleted": 1250,
  "space_freed_mb": 45.7,
  "retention_days": 30
}
```

### POST /admin/reload-config

Recarga la configuración sin reiniciar la aplicación.

**Response:**
```json
{
  "message": "Configuration reloaded successfully",
  "timestamp": "2024-01-20T10:30:00Z",
  "changes": [
    "sync.batch_size: 50 -> 75",
    "logging.level: INFO -> DEBUG"
  ]
}
```

### GET /admin/stats

Estadísticas detalladas del sistema.

**Response:**
```json
{
  "database": {
    "total_devices": 150,
    "sync_records": 1250,
    "failed_syncs": 25,
    "database_size_mb": 125.7
  },
  "performance": {
    "avg_sync_time_seconds": 30.5,
    "avg_devices_per_minute": 45.2,
    "peak_memory_usage_mb": 256.8,
    "avg_cpu_usage_percent": 15.3
  },
  "errors": {
    "last_24h": 5,
    "last_7d": 23,
    "most_common": [
      {
        "error": "GLPI API timeout",
        "count": 12,
        "percentage": 52.2
      },
      {
        "error": "MDM device not found",
        "count": 8,
        "percentage": 34.8
      }
    ]
  }
}
```

## 🚨 Códigos de Error

### Códigos HTTP Estándar

| Código | Descripción |
|--------|-------------|
| 200 | OK - Operación exitosa |
| 202 | Accepted - Operación iniciada (asíncrona) |
| 400 | Bad Request - Request inválido |
| 404 | Not Found - Recurso no encontrado |
| 409 | Conflict - Conflicto (ej: sync ya en progreso) |
| 422 | Unprocessable Entity - Datos inválidos |
| 429 | Too Many Requests - Rate limit excedido |
| 500 | Internal Server Error - Error interno |
| 503 | Service Unavailable - Servicio no disponible |

### Formato de Errores

```json
{
  "error": {
    "code": "SYNC_IN_PROGRESS",
    "message": "A synchronization is already in progress",
    "details": {
      "current_sync_id": "sync_20240120_103000",
      "started_at": "2024-01-20T10:30:00Z",
      "progress_percent": 45.0
    },
    "timestamp": "2024-01-20T10:35:00Z"
  }
}
```

### Códigos de Error Específicos

| Código | Descripción |
|--------|-------------|
| `SYNC_IN_PROGRESS` | Ya hay una sincronización en progreso |
| `MDM_CONNECTION_FAILED` | Error de conexión con MDM |
| `GLPI_CONNECTION_FAILED` | Error de conexión con GLPI |
| `DATABASE_ERROR` | Error de base de datos |
| `INVALID_DEVICE_ID` | ID de dispositivo inválido |
| `SYNC_NOT_FOUND` | Sincronización no encontrada |
| `RATE_LIMIT_EXCEEDED` | Límite de requests excedido |
| `CONFIGURATION_ERROR` | Error de configuración |

## 📡 WebSocket (Futuro)

### /ws/sync-status

WebSocket para recibir actualizaciones en tiempo real del estado de sincronización.

**Mensaje de Ejemplo:**
```json
{
  "type": "sync_progress",
  "sync_id": "sync_20240120_103000",
  "progress": {
    "devices_processed": 75,
    "devices_total": 150,
    "percentage": 50.0
  },
  "timestamp": "2024-01-20T10:32:30Z"
}
```

## 🔐 Autenticación (Futuro)

### API Key Authentication

```http
GET /sync/status
Authorization: Bearer your-api-key
```

### JWT Authentication

```http
POST /auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

## 📚 Ejemplos de Uso

### Bash/cURL

```bash
#!/bin/bash

# Verificar estado
curl -s http://localhost:8080/health | jq .

# Ejecutar sincronización completa
curl -X POST http://localhost:8080/sync/full \
  -H "Content-Type: application/json" \
  -d '{"force": false, "batch_size": 25}' | jq .

# Monitorear progreso
SYNC_ID=$(curl -s -X POST http://localhost:8080/sync/full | jq -r '.sync_id')
while true; do
  STATUS=$(curl -s http://localhost:8080/sync/status/$SYNC_ID | jq -r '.status')
  if [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]]; then
    break
  fi
  echo "Status: $STATUS"
  sleep 5
done
```

### Python

```python
import requests
import time

class MDMGLPIClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
    
    def health_check(self):
        response = requests.get(f"{self.base_url}/health")
        return response.json()
    
    def start_full_sync(self, batch_size=50):
        data = {"batch_size": batch_size}
        response = requests.post(f"{self.base_url}/sync/full", json=data)
        return response.json()
    
    def get_sync_status(self, sync_id):
        response = requests.get(f"{self.base_url}/sync/status/{sync_id}")
        return response.json()
    
    def wait_for_sync(self, sync_id, timeout=300):
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_sync_status(sync_id)
            if status['status'] in ['completed', 'failed']:
                return status
            time.sleep(5)
        raise TimeoutError("Sync did not complete within timeout")

# Uso
client = MDMGLPIClient()
health = client.health_check()
print(f"System status: {health['status']}")

sync_result = client.start_full_sync(batch_size=25)
sync_id = sync_result['sync_id']
print(f"Started sync: {sync_id}")

final_status = client.wait_for_sync(sync_id)
print(f"Sync completed: {final_status['results']}")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

class MDMGLPIClient {
  constructor(baseURL = 'http://localhost:8080') {
    this.client = axios.create({ baseURL });
  }

  async healthCheck() {
    const response = await this.client.get('/health');
    return response.data;
  }

  async startFullSync(batchSize = 50) {
    const response = await this.client.post('/sync/full', {
      batch_size: batchSize
    });
    return response.data;
  }

  async getSyncStatus(syncId) {
    const response = await this.client.get(`/sync/status/${syncId}`);
    return response.data;
  }

  async waitForSync(syncId, timeout = 300000) {
    const startTime = Date.now();
    
    while (Date.now() - startTime < timeout) {
      const status = await this.getSyncStatus(syncId);
      
      if (['completed', 'failed'].includes(status.status)) {
        return status;
      }
      
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
    
    throw new Error('Sync did not complete within timeout');
  }
}

// Uso
(async () => {
  const client = new MDMGLPIClient();
  
  const health = await client.healthCheck();
  console.log(`System status: ${health.status}`);
  
  const syncResult = await client.startFullSync(25);
  console.log(`Started sync: ${syncResult.sync_id}`);
  
  const finalStatus = await client.waitForSync(syncResult.sync_id);
  console.log(`Sync completed:`, finalStatus.results);
})();
```

## 🔄 Rate Limiting

La API implementa rate limiting por IP:

- **Límite por defecto**: 100 requests por minuto
- **Headers de respuesta**:
  - `X-RateLimit-Limit`: Límite total
  - `X-RateLimit-Remaining`: Requests restantes
  - `X-RateLimit-Reset`: Timestamp de reset

**Respuesta cuando se excede el límite:**
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again later.",
    "details": {
      "limit": 100,
      "window_seconds": 60,
      "retry_after_seconds": 45
    }
  }
}
```