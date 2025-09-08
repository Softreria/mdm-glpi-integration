# MDM-GLPI Integration

🔄 **Integración automática entre ManageEngine MDM y GLPI** para sincronización de dispositivos móviles en tiempo real.

## 🌟 Características

- **Sincronización Automática**: Sincronización programada y manual de dispositivos desde ManageEngine MDM a GLPI
- **API REST Completa**: Endpoints para operaciones manuales, monitoreo y administración
- **Monitoreo Avanzado**: Métricas Prometheus, health checks y alertas
- **Configuración Flexible**: Archivos YAML con validación y recarga en caliente
- **Logging Estructurado**: Logs JSON con múltiples niveles y rotación automática
- **Manejo Robusto de Errores**: Reintentos automáticos, circuit breakers y recuperación
- **Base de Datos**: Historial de sincronizaciones y mapeo de dispositivos
- **CLI Intuitivo**: Herramienta de línea de comandos para todas las operaciones

## 🚀 Instalación Rápida

### Prerrequisitos

- Python 3.9 o superior
- Acceso a ManageEngine MDM API
- Acceso a GLPI con API REST habilitada
- Tokens de autenticación para ambos sistemas

### Instalación

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/softreria/mdm-glpi-integration.git
   cd mdm-glpi-integration
   ```

2. **Crear entorno virtual**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

3. **Instalar dependencias**:
   ```bash
   pip install -e .
   ```

4. **Configurar variables de entorno**:
   ```bash
   cp .env.example .env
   # Editar .env con tu token de Zoho y credenciales de GLPI
   ```

5. **Generar configuración**:
   ```bash
   mdm-glpi-sync init-config -o config/config.yaml
   # Editar config/config.yaml según tus necesidades
   ```

6. **Probar conexión con Zoho MDM**:
   ```bash
   python test_zoho_connection.py
   ```

7. **Verificar conectividad**:
   ```bash
   mdm-glpi-sync health
   ```

## 📖 Uso

### Línea de Comandos

```bash
# Ejecutar sincronización manual completa
mdm-glpi-sync sync --type full

# Ejecutar sincronización incremental
mdm-glpi-sync sync --type incremental

# Ejecutar en modo daemon (programado)
mdm-glpi-sync run

# Verificar estado del sistema
mdm-glpi-sync health

# Ver estado actual
mdm-glpi-sync status

# Ver logs recientes
mdm-glpi-sync logs --days 7 --level INFO
```

### ⚙️ Configuración

La aplicación se configura mediante:

1. **Archivo principal**: `config/config.yaml`
2. **Variables de entorno**: Prefijo `MDM_GLPI_`
3. **Archivo .env**: Para desarrollo local

### 🔑 Configuración de Zoho MDM

Esta aplicación está configurada para trabajar con **Zoho MDM (ManageEngine)**. Para configurar tu token de autenticación:

1. **Obtén tu token OAuth de Zoho** desde tu consola de Zoho
2. **Configura el token** en tu archivo `.env`:
   ```bash
   MDM_API_KEY=1000.tu_token_oauth_de_zoho.aqui
   ```
3. **Verifica la conexión**:
   ```bash
   python test_zoho_connection.py
   ```

El formato del token debe ser: `1000.xxxxxxxx.xxxxxxxx`

La configuración se realiza mediante el archivo `config/config.yaml`:

```yaml
# Configuración de ManageEngine MDM
mdm:
  base_url: "https://your-mdm-server.com"
  api_key: "${MDM_API_KEY}"
  timeout: 30
  rate_limit: 100

# Configuración de GLPI
glpi:
  base_url: "https://your-glpi-server.com"
  app_token: "${GLPI_APP_TOKEN}"
  user_token: "${GLPI_USER_TOKEN}"
  timeout: 30

# Configuración de sincronización
sync:
  full_sync_cron: "0 2 * * *"      # Diaria a las 2:00 AM
  incremental_sync_cron: "*/15 * * * *"  # Cada 15 minutos
  batch_size: 100
  max_retries: 3
```

Ver [documentación de configuración](docs/configuration.md) para detalles completos.

### Variables de Entorno

Configura las siguientes variables en tu archivo `.env`:

```bash
# Credenciales MDM
MDM_API_KEY=your_mdm_api_key_here

# Credenciales GLPI
GLPI_APP_TOKEN=your_glpi_app_token_here
GLPI_USER_TOKEN=your_glpi_user_token_here
```

## 🏗️ Arquitectura

El sistema está diseñado con una arquitectura modular y escalable:

```
┌─────────────────────────────────────────────────────────────┐
│                    MDM-GLPI Integration                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    │
│  │   Scheduler │    │ Sync Service │    │ Config Mgr  │    │
│  │             │───▶│              │◄───│             │    │
│  └─────────────┘    └──────┬───────┘    └─────────────┘    │
│                             │                               │
│  ┌─────────────┐    ┌──────▼───────┐    ┌─────────────┐    │
│  │ MDM Connector│    │ Data Mapper  │    │GLPI Connector│   │
│  │             │───▶│              │───▶│             │    │
│  └─────────────┘    └──────────────┘    └─────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Componentes Principales

- **Scheduler**: Programación automática de sincronizaciones
- **Sync Service**: Orquestación del proceso de sincronización
- **MDM Connector**: Comunicación con ManageEngine MDM API
- **GLPI Connector**: Comunicación con GLPI API
- **Data Mapper**: Transformación de datos entre sistemas
- **Config Manager**: Gestión de configuración y credenciales

## 📊 Mapeo de Datos

### Tipos de Dispositivos

| MDM Device Type | GLPI Item Type |
|-----------------|----------------|
| iPhone          | Phone          |
| iPad            | Computer       |
| Android         | Phone          |
| Windows         | Computer       |

### Campos Principales

| Campo MDM           | Campo GLPI        | Descripción                    |
|---------------------|-------------------|--------------------------------|
| device_id           | otherserial       | ID único del dispositivo       |
| device_name         | name              | Nombre del dispositivo         |
| model               | computermodels_id | Modelo del dispositivo         |
| os_version          | operatingsystems_id| Versión del sistema operativo |
| user_email          | users_id          | Usuario asignado               |
| enrollment_date     | date_creation     | Fecha de registro              |
| last_seen           | date_mod          | Última vez visto               |

## 🔧 Desarrollo

### Configuración del Entorno de Desarrollo

```bash
# Instalar dependencias de desarrollo
pip install -e ".[dev]"

# Configurar pre-commit hooks
pre-commit install

# Ejecutar tests
pytest

# Ejecutar tests con cobertura
pytest --cov=src/mdm_glpi_integration

# Formatear código
black src/ tests/
isort src/ tests/

# Verificar tipos
mypy src/

# Linting
flake8 src/ tests/
```

### Estructura del Proyecto

```
mdm-glpi-integration/
├── src/mdm_glpi_integration/
│   ├── __init__.py
│   ├── main.py                 # Aplicación principal
│   ├── cli.py                  # Interfaz CLI
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py         # Configuración
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── mdm_connector.py    # Conector MDM
│   │   └── glpi_connector.py   # Conector GLPI
│   ├── services/
│   │   ├── __init__.py
│   │   └── sync_service.py     # Servicio de sincronización
│   ├── models/
│   │   ├── __init__.py
│   │   └── device.py           # Modelos de datos
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py           # Configuración de logging
│   │   └── health_checker.py   # Health checks
│   └── api/
│       ├── __init__.py
│       └── routes.py           # API REST (opcional)
├── tests/
│   ├── unit/                   # Tests unitarios
│   └── integration/            # Tests de integración
├── config/
│   └── config.yaml             # Configuración por defecto
├── docs/                       # Documentación
├── scripts/                    # Scripts de utilidad
├── requirements.txt            # Dependencias
├── pyproject.toml             # Configuración del proyecto
└── README.md
```

## 📈 Monitoreo

### Métricas Disponibles

El sistema expone métricas en formato Prometheus en el puerto 8080:

- `mdm_glpi_devices_synced_total`: Total de dispositivos sincronizados
- `mdm_glpi_sync_duration_seconds`: Duración de las sincronizaciones
- `mdm_glpi_api_requests_total`: Total de requests a APIs
- `mdm_glpi_errors_total`: Total de errores por tipo

### Logs

Los logs se almacenan en formato JSON estructurado:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Sincronización completada",
  "devices_processed": 150,
  "devices_success": 148,
  "devices_error": 2,
  "duration": 45.2
}
```

## 🐳 Deployment

### Docker

```bash
# Construir imagen
docker build -t mdm-glpi-integration .

# Ejecutar contenedor
docker run -d \
  --name mdm-glpi-sync \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  -e MDM_API_KEY=your_key \
  -e GLPI_APP_TOKEN=your_token \
  -e GLPI_USER_TOKEN=your_token \
  mdm-glpi-integration
```

### Docker Compose

```yaml
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
    restart: unless-stopped
```

### Systemd Service

```ini
[Unit]
Description=MDM-GLPI Integration Service
After=network.target

[Service]
Type=simple
User=mdm-glpi
WorkingDirectory=/opt/mdm-glpi-integration
ExecStart=/opt/mdm-glpi-integration/venv/bin/mdm-glpi-sync run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 🔒 Seguridad

- **Credenciales**: Nunca hardcodees credenciales en el código
- **Variables de Entorno**: Usa variables de entorno para información sensible
- **SSL/TLS**: Siempre usa conexiones seguras en producción
- **Tokens**: Rota los tokens de API regularmente
- **Logs**: No registres información sensible en los logs

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

### Guías de Contribución

- Sigue el estilo de código existente
- Añade tests para nuevas funcionalidades
- Actualiza la documentación según sea necesario
- Asegúrate de que todos los tests pasen

## 📝 Changelog

### [1.0.0] - 2024-01-15

#### Added
- Sincronización inicial entre MDM y GLPI
- CLI para gestión manual
- Configuración mediante YAML
- Logging estructurado
- Health checks automáticos
- Métricas de Prometheus
- Documentación completa

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## 🆘 Soporte

- **Documentación**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/softreria/mdm-glpi-integration/issues)
- **Email**: info@softreria.com

## 🙏 Agradecimientos

- [ManageEngine MDM](https://www.manageengine.com/mobile-device-management/) por su API
- [GLPI](https://glpi-project.org/) por su sistema de inventario
- [FastAPI](https://fastapi.tiangolo.com/) por el framework web
- [Pydantic](https://pydantic-docs.helpmanual.io/) por la validación de datos