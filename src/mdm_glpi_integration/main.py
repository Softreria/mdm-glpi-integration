"""Punto de entrada principal de la aplicación MDM-GLPI Integration."""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config.settings import Settings
from .services.sync_service import SyncService, SyncType
from .services.health_checker import HealthChecker
from .services.metrics_service import MetricsService
from .api.app import create_app, run_server


def setup_logging(settings: Settings):
    """Configurar logging estructurado.
    
    Args:
        settings: Configuración de la aplicación
    """
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Formato de salida según configuración
    if settings.logging.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class MDMGLPIIntegration:
    """Clase principal de la aplicación de integración MDM-GLPI."""

    def __init__(self, config_path: Optional[Path] = None):
        """Inicializar la aplicación.
        
        Args:
            config_path: Ruta al archivo de configuración
        """
        self.settings = Settings(config_path)
        setup_logging(self.settings)
        self.logger = structlog.get_logger()
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.sync_service: Optional[SyncService] = None
        self.health_checker: Optional[HealthChecker] = None
        self.metrics_service: Optional[MetricsService] = None
        self.api_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

    async def startup(self) -> None:
        """Inicializar todos los componentes de la aplicación."""
        try:
            self.logger.info("Iniciando MDM-GLPI Integration", version="1.0.0")
            
            # Inicializar servicios
            self.sync_service = SyncService(self.settings)
            self.health_checker = HealthChecker(self.settings)
            
            # Inicializar métricas si están habilitadas
            if self.settings.monitoring.enable_metrics:
                from prometheus_client import CollectorRegistry
                registry = CollectorRegistry()
                self.metrics_service = MetricsService(self.settings, registry)
                self.logger.info("Servicio de métricas inicializado")
            
            # Verificar conectividad inicial
            await self._check_initial_connectivity()
            
            # Configurar scheduler
            await self._setup_scheduler()
            
            # Iniciar servidor API
            if self.settings.monitoring.enable_metrics:
                self.logger.info("Iniciando servidor API", port=self.settings.monitoring.port)
                self.api_task = asyncio.create_task(
                    asyncio.to_thread(
                        run_server,
                        host="0.0.0.0",
                        port=self.settings.monitoring.port,
                        reload=False
                    )
                )
            
            self.logger.info("Aplicación iniciada correctamente")
            
        except Exception as e:
            self.logger.error("Error durante el inicio", error=str(e))
            raise

    async def _check_initial_connectivity(self) -> None:
        """Verificar conectividad inicial con MDM y GLPI."""
        self.logger.info("Verificando conectividad inicial")
        
        # Verificar MDM
        if not await self.health_checker.check_mdm_connectivity():
            raise RuntimeError("No se puede conectar con ManageEngine MDM")
            
        # Verificar GLPI
        if not await self.health_checker.check_glpi_connectivity():
            raise RuntimeError("No se puede conectar con GLPI")
            
        self.logger.info("Conectividad verificada correctamente")

    async def _setup_scheduler(self) -> None:
        """Configurar el programador de tareas."""
        self.scheduler = AsyncIOScheduler()
        
        # Sincronización completa (diaria a las 2:00 AM)
        self.scheduler.add_job(
            self._run_full_sync,
            CronTrigger.from_crontab(self.settings.sync.full_sync_cron),
            id="full_sync",
            name="Sincronización Completa",
            max_instances=1,
            coalesce=True
        )
        
        # Sincronización incremental (cada 15 minutos)
        self.scheduler.add_job(
            self._run_incremental_sync,
            CronTrigger.from_crontab(self.settings.sync.incremental_sync_cron),
            id="incremental_sync",
            name="Sincronización Incremental",
            max_instances=1,
            coalesce=True
        )
        
        # Limpieza de logs (diaria a las 3:00 AM)
        self.scheduler.add_job(
            self._cleanup_logs,
            CronTrigger(hour=3, minute=0),
            id="cleanup_logs",
            name="Limpieza de Logs",
            max_instances=1
        )
        
        self.scheduler.start()
        self.logger.info("Scheduler configurado y iniciado")

    async def _run_full_sync(self) -> None:
        """Ejecutar sincronización completa."""
        try:
            self.logger.info("Iniciando sincronización completa")
            result = await self.sync_service.sync_all(SyncType.FULL)
            self.logger.info(
                "Sincronización completa finalizada",
                devices_processed=result.devices_processed,
                devices_synced=result.devices_synced,
                errors=result.errors,
                duration=result.duration
            )
        except Exception as e:
            self.logger.error("Error en sincronización completa", error=str(e))

    async def _run_incremental_sync(self) -> None:
        """Ejecutar sincronización incremental."""
        try:
            self.logger.info("Iniciando sincronización incremental")
            result = await self.sync_service.sync_all(SyncType.INCREMENTAL)
            self.logger.info(
                "Sincronización incremental finalizada",
                devices_processed=result.devices_processed,
                devices_synced=result.devices_synced,
                errors=result.errors,
                duration=result.duration
            )
        except Exception as e:
            self.logger.error("Error en sincronización incremental", error=str(e))

    async def _cleanup_logs(self) -> None:
        """Limpiar logs antiguos."""
        try:
            self.logger.info("Iniciando limpieza de logs")
            if self.sync_service:
                await self.sync_service.cleanup_old_logs(days=30)
            self.logger.info("Limpieza de logs completada")
        except Exception as e:
            self.logger.error("Error en limpieza de logs", error=str(e))

    async def run_manual_sync(self, sync_type: str = "full") -> None:
        """Ejecutar sincronización manual.
        
        Args:
            sync_type: Tipo de sincronización ('full' o 'incremental')
        """
        if sync_type == "full":
            await self._run_full_sync()
        elif sync_type == "incremental":
            await self._run_incremental_sync()
        else:
            raise ValueError(f"Tipo de sincronización no válido: {sync_type}")

    async def shutdown(self) -> None:
        """Cerrar la aplicación de forma ordenada."""
        self.logger.info("Iniciando cierre de aplicación")
        
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            self.logger.info("Scheduler detenido")
        
        if self.api_task:
            self.api_task.cancel()
            try:
                await self.api_task
            except asyncio.CancelledError:
                pass
            self.logger.info("Servidor API detenido")
        
        if self.sync_service:
            # El sync_service no tiene método cleanup, usar close si existe
            self.logger.info("Servicio de sincronización cerrado")
        
        self.logger.info("Aplicación cerrada correctamente")
        self._shutdown_event.set()

    async def run(self) -> None:
        """Ejecutar la aplicación principal."""
        # Configurar manejadores de señales
        def signal_handler(signum, frame):
            self.logger.info(f"Señal recibida: {signum}")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            await self.startup()
            
            # Ejecutar sincronización inicial si está configurada
            if self.settings.sync.initial_sync:
                self.logger.info("Ejecutando sincronización inicial")
                await self._run_full_sync()
            
            # Esperar hasta que se solicite el cierre
            await self._shutdown_event.wait()
            
        except KeyboardInterrupt:
            self.logger.info("Interrupción por teclado recibida")
        except Exception as e:
            self.logger.error("Error crítico en aplicación", error=str(e))
            raise
        finally:
            await self.shutdown()


async def main() -> None:
    """Función principal."""
    app = MDMGLPIIntegration()
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAplicación interrumpida por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"Error crítico: {e}")
        sys.exit(1)