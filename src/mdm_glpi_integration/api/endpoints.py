"""Endpoints de la API REST."""

import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..config.settings import Settings
from ..services.sync_service import SyncService, SyncType, SyncResult
from ..services.health_checker import HealthChecker, SystemHealth
from ..services.metrics_service import MetricsService

logger = structlog.get_logger()

# Modelos de respuesta
class SyncRequest(BaseModel):
    """Modelo para solicitud de sincronización."""
    device_ids: Optional[List[str]] = Field(None, description="IDs específicos de dispositivos")
    force: bool = Field(False, description="Forzar sincronización aunque esté en progreso")


class SyncResponse(BaseModel):
    """Modelo para respuesta de sincronización."""
    success: bool
    message: str
    sync_id: Optional[str] = None
    devices_processed: Optional[int] = None
    devices_created: Optional[int] = None
    devices_updated: Optional[int] = None
    devices_failed: Optional[int] = None
    duration: Optional[float] = None
    errors: Optional[List[str]] = None


class HealthResponse(BaseModel):
    """Modelo para respuesta de salud."""
    status: str
    message: str
    timestamp: str
    uptime: float
    version: str
    components: Dict[str, Dict[str, Any]]


class StatusResponse(BaseModel):
    """Modelo para respuesta de estado."""
    sync_in_progress: bool
    last_full_sync: Optional[str]
    last_incremental_sync: Optional[str]
    statistics: Dict[str, Any]
    last_sync_log: Dict[str, Any]


class ErrorResponse(BaseModel):
    """Modelo para respuesta de error."""
    error: str
    detail: Optional[str] = None
    timestamp: str


# Dependencias
def get_settings() -> Settings:
    """Obtener configuración."""
    # TODO: Implementar singleton o inyección de dependencias
    return Settings()


def get_sync_service(settings: Settings = Depends(get_settings)) -> SyncService:
    """Obtener servicio de sincronización."""
    # TODO: Implementar singleton
    return SyncService(settings)


def get_health_checker(settings: Settings = Depends(get_settings)) -> HealthChecker:
    """Obtener verificador de salud."""
    # TODO: Implementar singleton
    return HealthChecker(settings)


def get_metrics_service(settings: Settings = Depends(get_settings)) -> MetricsService:
    """Obtener servicio de métricas."""
    # TODO: Implementar singleton
    return MetricsService(settings)


# Router principal
router = APIRouter()


# Endpoints de salud
@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(
    health_checker: HealthChecker = Depends(get_health_checker)
):
    """Verificar salud del sistema.
    
    Returns:
        Estado de salud de todos los componentes
    """
    try:
        health = await health_checker.check_health()
        
        return HealthResponse(
            status=health.overall_status.value,
            message=health_checker._get_health_message(health),
            timestamp=health.timestamp.isoformat(),
            uptime=health.uptime,
            version=health.version,
            components={
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "response_time": comp.response_time,
                    "last_check": comp.last_check.isoformat(),
                    "details": comp.details or {}
                }
                for name, comp in health.components.items()
            }
        )
        
    except Exception as e:
        logger.error("Error en health check", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al verificar salud del sistema: {str(e)}"
        )


@router.get("/health/summary", tags=["Health"])
async def health_summary(
    health_checker: HealthChecker = Depends(get_health_checker)
):
    """Obtener resumen de salud del sistema.
    
    Returns:
        Resumen simplificado del estado de salud
    """
    try:
        return health_checker.get_health_summary()
    except Exception as e:
        logger.error("Error en health summary", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener resumen de salud: {str(e)}"
        )


@router.get("/ready", tags=["Health"])
async def readiness_check(
    health_checker: HealthChecker = Depends(get_health_checker)
):
    """Verificar si el sistema está listo para recibir tráfico.
    
    Returns:
        Estado de preparación del sistema
    """
    try:
        health = await health_checker.check_health()
        
        # Sistema listo si está healthy o degraded (pero no unhealthy)
        is_ready = health.overall_status.value in ["healthy", "degraded"]
        
        if is_ready:
            return {"status": "ready", "message": "Sistema listo"}
        else:
            raise HTTPException(
                status_code=503,
                detail="Sistema no está listo"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en readiness check", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al verificar preparación: {str(e)}"
        )


@router.get("/live", tags=["Health"])
async def liveness_check():
    """Verificar si el sistema está vivo.
    
    Returns:
        Estado de vida del sistema
    """
    return {"status": "alive", "timestamp": datetime.now().isoformat()}


# Endpoints de sincronización
@router.post("/sync/full", response_model=SyncResponse, tags=["Sync"])
async def full_sync(
    background_tasks: BackgroundTasks,
    request: SyncRequest = SyncRequest(),
    sync_service: SyncService = Depends(get_sync_service)
):
    """Iniciar sincronización completa.
    
    Args:
        background_tasks: Tareas en segundo plano
        request: Parámetros de sincronización
        sync_service: Servicio de sincronización
        
    Returns:
        Resultado de la sincronización
    """
    try:
        if sync_service._sync_in_progress and not request.force:
            raise HTTPException(
                status_code=409,
                detail="Sincronización ya en progreso. Use force=true para forzar."
            )
        
        # Ejecutar sincronización
        result = await sync_service.full_sync()
        
        return SyncResponse(
            success=result.success,
            message="Sincronización completa finalizada",
            devices_processed=result.devices_processed,
            devices_created=result.devices_created,
            devices_updated=result.devices_updated,
            devices_failed=result.devices_failed,
            duration=result.duration,
            errors=result.errors[:10] if result.errors else None  # Limitar errores
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en sincronización completa", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en sincronización completa: {str(e)}"
        )


@router.post("/sync/incremental", response_model=SyncResponse, tags=["Sync"])
async def incremental_sync(
    background_tasks: BackgroundTasks,
    request: SyncRequest = SyncRequest(),
    sync_service: SyncService = Depends(get_sync_service)
):
    """Iniciar sincronización incremental.
    
    Args:
        background_tasks: Tareas en segundo plano
        request: Parámetros de sincronización
        sync_service: Servicio de sincronización
        
    Returns:
        Resultado de la sincronización
    """
    try:
        if sync_service._sync_in_progress and not request.force:
            raise HTTPException(
                status_code=409,
                detail="Sincronización ya en progreso. Use force=true para forzar."
            )
        
        # Ejecutar sincronización
        result = await sync_service.incremental_sync()
        
        return SyncResponse(
            success=result.success,
            message="Sincronización incremental finalizada",
            devices_processed=result.devices_processed,
            devices_created=result.devices_created,
            devices_updated=result.devices_updated,
            devices_failed=result.devices_failed,
            duration=result.duration,
            errors=result.errors[:10] if result.errors else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en sincronización incremental", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en sincronización incremental: {str(e)}"
        )


@router.post("/sync/manual", response_model=SyncResponse, tags=["Sync"])
async def manual_sync(
    request: SyncRequest,
    sync_service: SyncService = Depends(get_sync_service)
):
    """Iniciar sincronización manual de dispositivos específicos.
    
    Args:
        request: Parámetros de sincronización con device_ids
        sync_service: Servicio de sincronización
        
    Returns:
        Resultado de la sincronización
    """
    try:
        if not request.device_ids:
            raise HTTPException(
                status_code=400,
                detail="device_ids es requerido para sincronización manual"
            )
        
        if sync_service._sync_in_progress and not request.force:
            raise HTTPException(
                status_code=409,
                detail="Sincronización ya en progreso. Use force=true para forzar."
            )
        
        # Ejecutar sincronización
        result = await sync_service.manual_sync(request.device_ids)
        
        return SyncResponse(
            success=result.success,
            message=f"Sincronización manual de {len(request.device_ids)} dispositivos finalizada",
            devices_processed=result.devices_processed,
            devices_created=result.devices_created,
            devices_updated=result.devices_updated,
            devices_failed=result.devices_failed,
            duration=result.duration,
            errors=result.errors[:10] if result.errors else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en sincronización manual", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en sincronización manual: {str(e)}"
        )


@router.post("/sync/retry-failed", response_model=SyncResponse, tags=["Sync"])
async def retry_failed_sync(
    request: SyncRequest = SyncRequest(),
    sync_service: SyncService = Depends(get_sync_service)
):
    """Reintentar sincronización de dispositivos fallidos.
    
    Args:
        request: Parámetros opcionales (device_ids específicos)
        sync_service: Servicio de sincronización
        
    Returns:
        Resultado de la sincronización
    """
    try:
        if sync_service._sync_in_progress and not request.force:
            raise HTTPException(
                status_code=409,
                detail="Sincronización ya en progreso. Use force=true para forzar."
            )
        
        # Ejecutar reintento
        result = await sync_service.retry_failed_devices(request.device_ids)
        
        return SyncResponse(
            success=result.success,
            message="Reintento de dispositivos fallidos finalizado",
            devices_processed=result.devices_processed,
            devices_created=result.devices_created,
            devices_updated=result.devices_updated,
            devices_failed=result.devices_failed,
            duration=result.duration,
            errors=result.errors[:10] if result.errors else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en reintento de dispositivos fallidos", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en reintento: {str(e)}"
        )


# Endpoints de estado
@router.get("/status", response_model=StatusResponse, tags=["Status"])
async def get_status(
    sync_service: SyncService = Depends(get_sync_service)
):
    """Obtener estado actual del sistema.
    
    Args:
        sync_service: Servicio de sincronización
        
    Returns:
        Estado actual del sistema
    """
    try:
        status = sync_service.get_sync_status()
        
        return StatusResponse(
            sync_in_progress=status["sync_in_progress"],
            last_full_sync=status["last_full_sync"],
            last_incremental_sync=status["last_incremental_sync"],
            statistics=status["statistics"],
            last_sync_log=status["last_sync_log"]
        )
        
    except Exception as e:
        logger.error("Error al obtener estado", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener estado: {str(e)}"
        )


@router.get("/status/failed-devices", tags=["Status"])
async def get_failed_devices(
    limit: int = Query(50, ge=1, le=500, description="Número máximo de dispositivos"),
    sync_service: SyncService = Depends(get_sync_service)
):
    """Obtener dispositivos con errores de sincronización.
    
    Args:
        limit: Número máximo de dispositivos a retornar
        sync_service: Servicio de sincronización
        
    Returns:
        Lista de dispositivos con errores
    """
    try:
        failed_devices = sync_service.get_failed_devices(limit)
        
        return {
            "failed_devices": failed_devices,
            "count": len(failed_devices),
            "limit": limit
        }
        
    except Exception as e:
        logger.error("Error al obtener dispositivos fallidos", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener dispositivos fallidos: {str(e)}"
        )


# Endpoints de métricas
@router.get("/metrics", response_class=PlainTextResponse, tags=["Metrics"])
async def get_metrics(
    metrics_service: MetricsService = Depends(get_metrics_service)
):
    """Obtener métricas en formato Prometheus.
    
    Args:
        metrics_service: Servicio de métricas
        
    Returns:
        Métricas en formato texto de Prometheus
    """
    try:
        return metrics_service.get_metrics()
    except Exception as e:
        logger.error("Error al obtener métricas", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener métricas: {str(e)}"
        )


@router.get("/metrics/summary", tags=["Metrics"])
async def get_metrics_summary(
    metrics_service: MetricsService = Depends(get_metrics_service)
):
    """Obtener resumen de métricas principales.
    
    Args:
        metrics_service: Servicio de métricas
        
    Returns:
        Resumen de métricas en formato JSON
    """
    try:
        return metrics_service.get_metrics_summary()
    except Exception as e:
        logger.error("Error al obtener resumen de métricas", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener resumen de métricas: {str(e)}"
        )


# Endpoints de administración
@router.post("/admin/cleanup-logs", tags=["Admin"])
async def cleanup_logs(
    days: int = Query(30, ge=1, le=365, description="Días de antigüedad para limpiar"),
    sync_service: SyncService = Depends(get_sync_service)
):
    """Limpiar logs antiguos.
    
    Args:
        days: Días de antigüedad para limpiar
        sync_service: Servicio de sincronización
        
    Returns:
        Resultado de la limpieza
    """
    try:
        deleted_count = sync_service.cleanup_old_logs(days)
        
        return {
            "message": f"Limpieza completada. {deleted_count} registros eliminados.",
            "deleted_count": deleted_count,
            "days": days
        }
        
    except Exception as e:
        logger.error("Error en limpieza de logs", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Error en limpieza de logs: {str(e)}"
        )


@router.get("/version", tags=["Info"])
async def get_version():
    """Obtener información de versión.
    
    Returns:
        Información de versión y build
    """
    return {
        "version": "1.0.0",  # TODO: Obtener de configuración
        "build_date": "2024-01-20",  # TODO: Obtener de build
        "git_commit": "unknown",  # TODO: Obtener de git
        "python_version": "3.9+"
    }


@router.get("/info", tags=["Info"])
async def get_info(
    settings: Settings = Depends(get_settings)
):
    """Obtener información general del sistema.
    
    Args:
        settings: Configuración del sistema
        
    Returns:
        Información general del sistema
    """
    return {
        "name": "MDM-GLPI Integration",
        "description": "Integración entre ManageEngine MDM y GLPI",
        "version": "1.0.0",
        "mdm_url": settings.mdm.base_url,
        "glpi_url": settings.glpi.base_url,
        "sync_config": {
            "full_sync_cron": settings.sync.full_sync_cron,
            "incremental_sync_cron": settings.sync.incremental_sync_cron,
            "batch_size": settings.sync.batch_size,
            "max_retries": settings.sync.max_retries
        },
        "monitoring": {
            "metrics_enabled": settings.monitoring.metrics_enabled,
            "metrics_port": settings.monitoring.metrics_port
        }
    }


# Los manejadores de errores globales están en app.py


@router.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Manejador de excepciones generales."""
    logger.error(
        "Error no manejado en API",
        error=str(exc),
        path=request.url.path,
        method=request.method
    )
    
    return ErrorResponse(
        error="Error interno del servidor",
        detail=str(exc) if settings.logging.level == "DEBUG" else None,
        timestamp=datetime.now().isoformat()
    )