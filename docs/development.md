# Guía de Desarrollo

Esta guía cubre todo lo necesario para contribuir al desarrollo de la integración MDM-GLPI.

## 🚀 Configuración del Entorno de Desarrollo

### Requisitos Previos

```bash
# Python 3.9+
python3.9 --version

# Git
git --version

# PostgreSQL (para desarrollo local)
psql --version

# Docker (opcional, para contenedores)
docker --version
docker-compose --version
```

### Configuración Inicial

```bash
# 1. Clonar repositorio
git clone https://github.com/company/mdm-glpi-integration.git
cd mdm-glpi-integration

# 2. Crear entorno virtual
python3.9 -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate     # Windows

# 3. Instalar dependencias de desarrollo
pip install -r requirements-dev.txt

# 4. Instalar pre-commit hooks
pre-commit install

# 5. Configurar variables de entorno
cp .env.example .env
# Editar .env con valores de desarrollo

# 6. Configurar base de datos de desarrollo
createdb mdmglpi_dev
psql mdmglpi_dev < scripts/init_dev_db.sql

# 7. Ejecutar migraciones
python -m alembic upgrade head

# 8. Verificar instalación
python cli.py test-connections
python -m pytest tests/ -v
```

### Estructura del Proyecto

```
mdm-glpi-integration/
├── src/
│   └── mdm_glpi_integration/
│       ├── __init__.py
│       ├── main.py                 # Punto de entrada principal
│       ├── cli.py                  # Interfaz de línea de comandos
│       ├── api/                    # API REST
│       │   ├── __init__.py
│       │   ├── app.py             # Aplicación FastAPI
│       │   ├── middleware.py      # Middlewares personalizados
│       │   └── routes/            # Endpoints de la API
│       ├── connectors/            # Conectores a sistemas externos
│       │   ├── __init__.py
│       │   ├── mdm.py            # Conector ManageEngine MDM
│       │   └── glpi.py           # Conector GLPI
│       ├── core/                  # Funcionalidad central
│       │   ├── __init__.py
│       │   ├── config.py         # Configuración
│       │   ├── exceptions.py     # Excepciones personalizadas
│       │   └── security.py       # Utilidades de seguridad
│       ├── models/               # Modelos de datos
│       │   ├── __init__.py
│       │   ├── device.py         # Modelos de dispositivos
│       │   └── database.py       # Modelos de base de datos
│       ├── services/             # Servicios de negocio
│       │   ├── __init__.py
│       │   ├── sync.py           # Servicio de sincronización
│       │   ├── health.py         # Verificaciones de salud
│       │   └── metrics.py        # Métricas y monitoreo
│       └── utils/                # Utilidades
│           ├── __init__.py
│           ├── logging.py        # Configuración de logging
│           ├── retry.py          # Lógica de reintentos
│           └── validation.py     # Validaciones
├── tests/                        # Tests
│   ├── unit/                    # Tests unitarios
│   ├── integration/             # Tests de integración
│   └── fixtures/                # Datos de prueba
├── docs/                        # Documentación
├── scripts/                     # Scripts de utilidad
├── config.example.yaml          # Configuración de ejemplo
├── requirements.txt             # Dependencias de producción
├── requirements-dev.txt         # Dependencias de desarrollo
├── pyproject.toml              # Configuración del proyecto
├── .pre-commit-config.yaml     # Configuración de pre-commit
└── README.md
```

## 🧪 Testing

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Tests con cobertura
pytest --cov=src/mdm_glpi_integration --cov-report=html

# Tests específicos
pytest tests/unit/test_sync_service.py
pytest tests/integration/

# Tests con marcadores
pytest -m "not slow"  # Excluir tests lentos
pytest -m "integration"  # Solo tests de integración

# Tests en paralelo
pytest -n auto

# Tests con output detallado
pytest -v -s
```

### Escribir Tests

#### Test Unitario

```python
# tests/unit/test_mdm_connector.py
import pytest
from unittest.mock import Mock, patch
from src.mdm_glpi_integration.connectors.mdm import MDMConnector
from src.mdm_glpi_integration.core.exceptions import MDMConnectionError

class TestMDMConnector:
    @pytest.fixture
    def mdm_connector(self):
        return MDMConnector(
            base_url="https://test-mdm.com",
            api_key="test-key",
            timeout=30
        )
    
    @patch('requests.get')
    def test_get_devices_success(self, mock_get, mdm_connector):
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "devices": [
                {"id": "1", "name": "Device 1", "serial": "ABC123"},
                {"id": "2", "name": "Device 2", "serial": "DEF456"}
            ]
        }
        mock_get.return_value = mock_response
        
        # Act
        devices = mdm_connector.get_devices()
        
        # Assert
        assert len(devices) == 2
        assert devices[0].id == "1"
        assert devices[0].name == "Device 1"
        mock_get.assert_called_once()
    
    @patch('requests.get')
    def test_get_devices_connection_error(self, mock_get, mdm_connector):
        # Arrange
        mock_get.side_effect = requests.ConnectionError("Connection failed")
        
        # Act & Assert
        with pytest.raises(MDMConnectionError):
            mdm_connector.get_devices()
    
    def test_build_headers(self, mdm_connector):
        # Act
        headers = mdm_connector._build_headers()
        
        # Assert
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"
```

#### Test de Integración

```python
# tests/integration/test_sync_flow.py
import pytest
from src.mdm_glpi_integration.services.sync import SyncService
from src.mdm_glpi_integration.models.device import SyncType

@pytest.mark.integration
class TestSyncFlow:
    @pytest.fixture
    def sync_service(self, test_settings, test_db):
        return SyncService(test_settings)
    
    @pytest.fixture
    def mock_mdm_devices(self):
        return [
            {
                "id": "mdm-001",
                "name": "Test Device 1",
                "serial_number": "SN001",
                "model": "iPhone 12",
                "os_version": "15.0",
                "status": "active"
            },
            {
                "id": "mdm-002",
                "name": "Test Device 2",
                "serial_number": "SN002",
                "model": "Samsung Galaxy",
                "os_version": "11.0",
                "status": "inactive"
            }
        ]
    
    @pytest.mark.asyncio
    async def test_full_sync_flow(self, sync_service, mock_mdm_devices):
        # Arrange
        with patch.object(sync_service.mdm_connector, 'get_devices') as mock_get_devices:
            mock_get_devices.return_value = mock_mdm_devices
            
            with patch.object(sync_service.glpi_connector, 'create_computer') as mock_create:
                mock_create.return_value = {"id": 123}
                
                # Act
                result = await sync_service.sync_all(SyncType.FULL)
                
                # Assert
                assert result.devices_synced == 2
                assert result.errors == 0
                assert result.sync_type == SyncType.FULL
                mock_get_devices.assert_called_once()
                assert mock_create.call_count == 2
```

#### Fixtures y Mocks

```python
# tests/conftest.py
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.mdm_glpi_integration.core.config import Settings
from src.mdm_glpi_integration.models.database import Base

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_settings():
    """Configuración para tests."""
    return Settings(
        mdm={
            "base_url": "https://test-mdm.com",
            "api_key": "test-key",
            "timeout": 30
        },
        glpi={
            "base_url": "https://test-glpi.com",
            "app_token": "test-app-token",
            "user_token": "test-user-token"
        },
        database={
            "url": "sqlite:///:memory:"
        },
        logging={
            "level": "DEBUG"
        }
    )

@pytest.fixture
def test_db(test_settings):
    """Base de datos en memoria para tests."""
    engine = create_engine(test_settings.database.url)
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(engine)

@pytest.fixture
def sample_mdm_device():
    """Dispositivo MDM de ejemplo."""
    return {
        "id": "test-device-001",
        "name": "Test iPhone",
        "serial_number": "ABC123456",
        "model": "iPhone 12 Pro",
        "os_version": "15.0.1",
        "status": "active",
        "last_seen": "2024-01-15T10:30:00Z",
        "user": {
            "name": "John Doe",
            "email": "john.doe@company.com"
        }
    }
```

### Marcadores de Tests

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow tests",
    "external: Tests that require external services",
    "database: Tests that require database"
]
```

## 🔧 Herramientas de Desarrollo

### Linting y Formateo

```bash
# Black (formateo de código)
black src/ tests/

# isort (ordenar imports)
isort src/ tests/

# flake8 (linting)
flake8 src/ tests/

# mypy (type checking)
mypy src/

# Ejecutar todo junto
pre-commit run --all-files
```

### Configuración de Pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict
  
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black
        language_version: python3.9
  
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: ["--profile", "black"]
  
  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        additional_dependencies: [flake8-docstrings]
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.0.1
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-PyYAML]
```

### Configuración de Herramientas

```toml
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py39']
include = '\.pyi?$'
extend-exclude = '''
(
  /(
      \.eggs
    | \.git
    | \.hg
    | \.mypy_cache
    | \.tox
    | \.venv
    | _build
    | buck-out
    | build
    | dist
  )/
)
'''

[tool.isort]
profile = "black"
multi_line_output = 3
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true
ensure_newline_before_comments = true
line_length = 88

[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/venv/*",
    "*/__pycache__/*"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:"
]
```

## 🏗️ Arquitectura y Patrones

### Principios de Diseño

1. **Separación de Responsabilidades**: Cada módulo tiene una responsabilidad específica
2. **Inversión de Dependencias**: Usar interfaces y dependency injection
3. **Configuración Externa**: Toda configuración debe ser externa al código
4. **Logging Estructurado**: Usar JSON para logs en producción
5. **Manejo de Errores**: Excepciones específicas y manejo centralizado
6. **Testing**: Cobertura mínima del 80%

### Patrones Utilizados

#### Repository Pattern

```python
# src/mdm_glpi_integration/repositories/device.py
from abc import ABC, abstractmethod
from typing import List, Optional
from src.mdm_glpi_integration.models.device import MDMDevice

class DeviceRepository(ABC):
    @abstractmethod
    async def get_all(self) -> List[MDMDevice]:
        pass
    
    @abstractmethod
    async def get_by_id(self, device_id: str) -> Optional[MDMDevice]:
        pass
    
    @abstractmethod
    async def save(self, device: MDMDevice) -> MDMDevice:
        pass

class SQLDeviceRepository(DeviceRepository):
    def __init__(self, session):
        self.session = session
    
    async def get_all(self) -> List[MDMDevice]:
        # Implementación específica para SQL
        pass
```

#### Factory Pattern

```python
# src/mdm_glpi_integration/factories/connector.py
from src.mdm_glpi_integration.connectors.mdm import MDMConnector
from src.mdm_glpi_integration.connectors.glpi import GLPIConnector
from src.mdm_glpi_integration.core.config import Settings

class ConnectorFactory:
    @staticmethod
    def create_mdm_connector(settings: Settings) -> MDMConnector:
        return MDMConnector(
            base_url=settings.mdm.base_url,
            api_key=settings.mdm.api_key,
            timeout=settings.mdm.timeout
        )
    
    @staticmethod
    def create_glpi_connector(settings: Settings) -> GLPIConnector:
        return GLPIConnector(
            base_url=settings.glpi.base_url,
            app_token=settings.glpi.app_token,
            user_token=settings.glpi.user_token
        )
```

#### Observer Pattern (para métricas)

```python
# src/mdm_glpi_integration/observers/metrics.py
from abc import ABC, abstractmethod
from typing import List

class SyncObserver(ABC):
    @abstractmethod
    def on_sync_started(self, sync_id: str):
        pass
    
    @abstractmethod
    def on_device_synced(self, device_id: str, success: bool):
        pass
    
    @abstractmethod
    def on_sync_completed(self, sync_id: str, result):
        pass

class MetricsObserver(SyncObserver):
    def __init__(self, metrics_service):
        self.metrics_service = metrics_service
    
    def on_sync_started(self, sync_id: str):
        self.metrics_service.increment_counter("sync_started_total")
    
    def on_device_synced(self, device_id: str, success: bool):
        if success:
            self.metrics_service.increment_counter("devices_synced_total")
        else:
            self.metrics_service.increment_counter("devices_failed_total")
```

### Manejo de Errores

```python
# src/mdm_glpi_integration/core/exceptions.py
class MDMGLPIException(Exception):
    """Excepción base para la aplicación."""
    pass

class ConfigurationError(MDMGLPIException):
    """Error de configuración."""
    pass

class ConnectionError(MDMGLPIException):
    """Error de conexión a servicios externos."""
    pass

class SyncError(MDMGLPIException):
    """Error durante la sincronización."""
    def __init__(self, message: str, device_id: str = None, errors: List[str] = None):
        super().__init__(message)
        self.device_id = device_id
        self.errors = errors or []

# Uso en servicios
class SyncService:
    async def sync_device(self, device_id: str):
        try:
            # Lógica de sincronización
            pass
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to connect to external service: {e}")
        except Exception as e:
            raise SyncError(f"Sync failed for device {device_id}", device_id=device_id)
```

## 📊 Logging y Monitoreo

### Configuración de Logging

```python
# src/mdm_glpi_integration/utils/logging.py
import logging
import json
from datetime import datetime
from typing import Dict, Any

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Agregar contexto adicional
        if hasattr(record, 'sync_id'):
            log_entry['sync_id'] = record.sync_id
        if hasattr(record, 'device_id'):
            log_entry['device_id'] = record.device_id
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        
        # Agregar información de excepción
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)

def setup_logging(settings):
    """Configurar logging basado en settings."""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.logging.level.upper()))
    
    # Limpiar handlers existentes
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Handler para archivo
    if settings.logging.file:
        file_handler = logging.FileHandler(settings.logging.file)
        if settings.logging.format == "json":
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            )
        logger.addHandler(file_handler)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    if settings.logging.format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )
    logger.addHandler(console_handler)

# Uso en servicios
class SyncService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def sync_device(self, device_id: str, sync_id: str):
        # Crear logger con contexto
        logger = logging.LoggerAdapter(
            self.logger, 
            {'sync_id': sync_id, 'device_id': device_id}
        )
        
        logger.info("Starting device sync")
        try:
            # Lógica de sincronización
            logger.info("Device sync completed successfully")
        except Exception as e:
            logger.error("Device sync failed", exc_info=True)
            raise
```

### Métricas Personalizadas

```python
# src/mdm_glpi_integration/services/metrics.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from typing import Dict, Any
import time

class MetricsService:
    def __init__(self):
        self.registry = CollectorRegistry()
        
        # Contadores
        self.sync_total = Counter(
            'mdm_glpi_sync_total',
            'Total number of sync operations',
            ['sync_type', 'status'],
            registry=self.registry
        )
        
        self.devices_processed = Counter(
            'mdm_glpi_devices_processed_total',
            'Total number of devices processed',
            ['status'],
            registry=self.registry
        )
        
        # Histogramas
        self.sync_duration = Histogram(
            'mdm_glpi_sync_duration_seconds',
            'Time spent on sync operations',
            ['sync_type'],
            registry=self.registry
        )
        
        self.api_request_duration = Histogram(
            'mdm_glpi_api_request_duration_seconds',
            'Time spent on API requests',
            ['service', 'endpoint'],
            registry=self.registry
        )
        
        # Gauges
        self.active_syncs = Gauge(
            'mdm_glpi_active_syncs',
            'Number of currently active sync operations',
            registry=self.registry
        )
        
        self.last_sync_timestamp = Gauge(
            'mdm_glpi_last_sync_timestamp',
            'Timestamp of last successful sync',
            ['sync_type'],
            registry=self.registry
        )
    
    def record_sync_start(self, sync_type: str):
        self.active_syncs.inc()
        return time.time()
    
    def record_sync_end(self, sync_type: str, start_time: float, success: bool):
        duration = time.time() - start_time
        self.sync_duration.labels(sync_type=sync_type).observe(duration)
        
        status = 'success' if success else 'failure'
        self.sync_total.labels(sync_type=sync_type, status=status).inc()
        
        if success:
            self.last_sync_timestamp.labels(sync_type=sync_type).set(time.time())
        
        self.active_syncs.dec()
    
    def record_device_processed(self, success: bool):
        status = 'success' if success else 'failure'
        self.devices_processed.labels(status=status).inc()
    
    def record_api_request(self, service: str, endpoint: str, duration: float):
        self.api_request_duration.labels(
            service=service, 
            endpoint=endpoint
        ).observe(duration)
```

## 🚀 Deployment y CI/CD

### GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: test_mdmglpi
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Cache pip dependencies
      uses: actions/cache@v3
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
        restore-keys: |
          ${{ runner.os }}-pip-
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-dev.txt
    
    - name: Lint with flake8
      run: |
        flake8 src/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 src/ tests/ --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics
    
    - name: Type check with mypy
      run: mypy src/
    
    - name: Test with pytest
      env:
        DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test_mdmglpi
      run: |
        pytest --cov=src/mdm_glpi_integration --cov-report=xml --cov-report=html
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella

  security:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Run Bandit Security Scan
      run: |
        pip install bandit
        bandit -r src/ -f json -o bandit-report.json
    
    - name: Run Safety Check
      run: |
        pip install safety
        safety check --json --output safety-report.json

  build:
    needs: [test, security]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v2
    
    - name: Login to Container Registry
      uses: docker/login-action@v2
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    
    - name: Build and push Docker image
      uses: docker/build-push-action@v4
      with:
        context: .
        push: true
        tags: |
          ghcr.io/${{ github.repository }}:latest
          ghcr.io/${{ github.repository }}:${{ github.sha }}
        cache-from: type=gha
        cache-to: type=gha,mode=max

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production
    
    steps:
    - name: Deploy to production
      run: |
        echo "Deploying to production..."
        # Aquí iría la lógica de deployment
```

### Dockerfile Optimizado

```dockerfile
# Dockerfile
# Multi-stage build para optimizar tamaño
FROM python:3.9-slim as builder

# Instalar dependencias de compilación
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements y instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Etapa de producción
FROM python:3.9-slim

# Instalar dependencias de runtime
RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r mdmglpi \
    && useradd -r -g mdmglpi mdmglpi

# Copiar dependencias instaladas
COPY --from=builder /root/.local /home/mdmglpi/.local

# Establecer directorio de trabajo
WORKDIR /app

# Copiar código fuente
COPY src/ ./src/
COPY cli.py .
COPY config.example.yaml ./config.yaml

# Crear directorios y establecer permisos
RUN mkdir -p /app/data /app/logs \
    && chown -R mdmglpi:mdmglpi /app

# Cambiar a usuario no-root
USER mdmglpi

# Agregar .local/bin al PATH
ENV PATH=/home/mdmglpi/.local/bin:$PATH

# Exponer puerto
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python cli.py health || exit 1

# Comando por defecto
CMD ["python", "cli.py", "run"]
```

## 📝 Contribución

### Proceso de Contribución

1. **Fork del repositorio**
2. **Crear rama de feature**: `git checkout -b feature/nueva-funcionalidad`
3. **Hacer cambios y commits**: Seguir [Conventional Commits](https://www.conventionalcommits.org/)
4. **Escribir tests**: Mantener cobertura > 80%
5. **Ejecutar tests y linting**: `pre-commit run --all-files`
6. **Push y crear PR**: Incluir descripción detallada
7. **Code review**: Responder a comentarios
8. **Merge**: Después de aprobación

### Conventional Commits

```bash
# Tipos de commit
feat: nueva funcionalidad
fix: corrección de bug
docs: cambios en documentación
style: formateo, punto y coma faltante, etc.
refactor: refactoring de código
test: agregar tests faltantes
chore: tareas de mantenimiento

# Ejemplos
git commit -m "feat(sync): add incremental sync support"
git commit -m "fix(mdm): handle connection timeout properly"
git commit -m "docs(api): update endpoint documentation"
git commit -m "test(glpi): add integration tests for connector"
```

### Code Review Checklist

- [ ] Código sigue estándares de estilo (Black, isort, flake8)
- [ ] Tests incluidos y pasando
- [ ] Documentación actualizada
- [ ] No hay secretos hardcodeados
- [ ] Manejo de errores apropiado
- [ ] Logging estructurado implementado
- [ ] Performance considerado
- [ ] Backward compatibility mantenida
- [ ] Security implications evaluadas

### Release Process

1. **Actualizar CHANGELOG.md**
2. **Bump version**: `bump2version patch|minor|major`
3. **Create release tag**: `git tag v1.2.3`
4. **Push tag**: `git push origin v1.2.3`
5. **GitHub Actions** automáticamente:
   - Ejecuta tests
   - Construye imagen Docker
   - Crea GitHub Release
   - Despliega a staging

---

¿Necesitas ayuda con algún aspecto específico del desarrollo? ¡Consulta la documentación o contacta al equipo!