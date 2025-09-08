"""Aplicación FastAPI principal."""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

import structlog
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry
import uvicorn

from ..config.settings import Settings
from ..services.sync_service import SyncService
from ..services.health_checker import HealthChecker
from ..services.metrics_service import MetricsService
from .endpoints import router
from .middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    RateLimitMiddleware,
    SecurityMiddleware
)

logger = structlog.get_logger()

# Instancias globales de servicios (singleton pattern)
_services: Dict[str, Any] = {}


def get_service(service_name: str, settings: Settings):
    """Obtener instancia singleton de servicio.
    
    Args:
        service_name: Nombre del servicio
        settings: Configuración
        
    Returns:
        Instancia del servicio
    """
    if service_name not in _services:
        if service_name == "sync_service":
            _services[service_name] = SyncService(settings)
        elif service_name == "health_checker":
            _services[service_name] = HealthChecker(settings)
        elif service_name == "metrics_service":
            registry = CollectorRegistry()
            _services[service_name] = MetricsService(settings, registry)
        else:
            raise ValueError(f"Servicio desconocido: {service_name}")
    
    return _services[service_name]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación.
    
    Args:
        app: Instancia de FastAPI
    """
    # Startup
    logger.info("Iniciando aplicación MDM-GLPI Integration")
    
    try:
        # Cargar configuración
        settings = Settings()
        app.state.settings = settings
        
        # Inicializar servicios
        sync_service = get_service("sync_service", settings)
        health_checker = get_service("health_checker", settings)
        metrics_service = get_service("metrics_service", settings)
        
        # Almacenar servicios en el estado de la app
        app.state.sync_service = sync_service
        app.state.health_checker = health_checker
        app.state.metrics_service = metrics_service
        
        # Verificar conectividad inicial
        logger.info("Verificando conectividad inicial")
        initial_health = await health_checker.check_health()
        
        if initial_health.overall_status.value == "unhealthy":
            logger.warning(
                "Sistema iniciado con problemas de conectividad",
                status=initial_health.overall_status.value
            )
        else:
            logger.info(
                "Sistema iniciado correctamente",
                status=initial_health.overall_status.value
            )
        
        # Inicializar métricas
        metrics_service.update_health_metrics(health_checker.get_health_summary())
        
        logger.info("Aplicación iniciada correctamente")
        
        yield
        
    except Exception as e:
        logger.error("Error durante el inicio de la aplicación", error=str(e))
        raise
    
    # Shutdown
    logger.info("Cerrando aplicación")
    
    try:
        # Limpiar recursos si es necesario
        # Los servicios se limpiarán automáticamente
        logger.info("Aplicación cerrada correctamente")
        
    except Exception as e:
        logger.error("Error durante el cierre de la aplicación", error=str(e))


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Crear instancia de la aplicación FastAPI.
    
    Args:
        settings: Configuración opcional
        
    Returns:
        Instancia de FastAPI configurada
    """
    if settings is None:
        settings = Settings()
    
    # Crear aplicación
    app = FastAPI(
        title="MDM-GLPI Integration API",
        description="API para integración entre ManageEngine MDM y GLPI",
        version="1.0.0",
        docs_url="/docs" if settings.logging.level == "DEBUG" else None,
        redoc_url="/redoc" if settings.logging.level == "DEBUG" else None,
        lifespan=lifespan
    )
    
    # Configurar CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configurar orígenes permitidos
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Middleware de seguridad
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # TODO: Configurar hosts permitidos
    )
    
    # Middleware personalizado
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
    app.add_middleware(LoggingMiddleware)
    
    # Incluir rutas
    app.include_router(router, prefix="/api/v1")
    
    # Ruta raíz
    @app.get("/")
    async def root():
        """Endpoint raíz."""
        return {
            "name": "MDM-GLPI Integration API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs" if settings.logging.level == "DEBUG" else "disabled",
            "health": "/api/v1/health",
            "metrics": "/api/v1/metrics"
        }
    
    # Manejadores de errores globales
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        """Manejador para errores 404."""
        return JSONResponse(
            status_code=404,
            content={
                "error": "Endpoint no encontrado",
                "path": str(request.url.path),
                "method": request.method
            }
        )
    
    @app.exception_handler(500)
    async def internal_error_handler(request: Request, exc):
        """Manejador para errores 500."""
        logger.error(
            "Error interno del servidor",
            error=str(exc),
            path=str(request.url.path),
            method=request.method
        )
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Error interno del servidor",
                "detail": str(exc) if settings.logging.level == "DEBUG" else None
            }
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Manejador de excepciones HTTP."""
        from datetime import datetime
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, reload: bool = False):
    """Ejecutar servidor de desarrollo.
    
    Args:
        host: Host para bind
        port: Puerto para bind
        reload: Habilitar recarga automática
    """
    logger.info(
        "Iniciando servidor de desarrollo",
        host=host,
        port=port,
        reload=reload
    )
    
    uvicorn.run(
        "src.mdm_glpi_integration.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_config=None,  # Usar nuestro logging
        access_log=False  # Usar nuestro middleware de logging
    )


if __name__ == "__main__":
    # Ejecutar servidor si se llama directamente
    import sys
    
    # Configurar logging básico
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Argumentos de línea de comandos básicos
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    reload = "--reload" in sys.argv
    
    run_server(host, port, reload)