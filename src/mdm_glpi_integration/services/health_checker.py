"""Servicio de monitoreo de salud del sistema."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import structlog
from prometheus_client import Gauge, Counter, Histogram

from ..config.settings import Settings
from ..connectors.mdm_connector import ManageEngineMDMConnector, MDMConnectorError
from ..connectors.glpi_connector import GLPIConnector, GLPIConnectorError

logger = structlog.get_logger()


class HealthStatus(Enum):
    """Estados de salud del sistema."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Estado de salud de un componente."""
    name: str
    status: HealthStatus
    message: str
    last_check: datetime
    response_time: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """Estado de salud del sistema completo."""
    overall_status: HealthStatus
    components: Dict[str, ComponentHealth]
    timestamp: datetime
    uptime: float
    version: str


class HealthChecker:
    """Servicio de monitoreo de salud."""
    
    def __init__(self, settings: Settings):
        """Inicializar el monitor de salud.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.logger = logger.bind(component="health_checker")
        self.start_time = datetime.now()
        
        # Métricas de Prometheus
        self.health_status_gauge = Gauge(
            'mdm_glpi_health_status',
            'Health status of components',
            ['component']
        )
        
        self.response_time_histogram = Histogram(
            'mdm_glpi_response_time_seconds',
            'Response time of health checks',
            ['component']
        )
        
        self.health_check_counter = Counter(
            'mdm_glpi_health_checks_total',
            'Total number of health checks',
            ['component', 'status']
        )
        
        # Cache de estado
        self._last_health_check: Optional[SystemHealth] = None
        self._check_in_progress = False
    
    async def check_health(self, force: bool = False) -> SystemHealth:
        """Verificar salud del sistema.
        
        Args:
            force: Forzar verificación aunque esté en progreso
            
        Returns:
            Estado de salud del sistema
        """
        if self._check_in_progress and not force:
            if self._last_health_check:
                return self._last_health_check
            # Si no hay check previo, esperar
            await asyncio.sleep(0.1)
            return await self.check_health(force=False)
        
        self._check_in_progress = True
        
        try:
            self.logger.debug("Iniciando verificación de salud")
            
            # Verificar componentes en paralelo
            tasks = {
                "mdm": self._check_mdm_health(),
                "glpi": self._check_glpi_health(),
                "database": self._check_database_health(),
                "system": self._check_system_health()
            }
            
            # Ejecutar verificaciones con timeout
            results = {}
            for name, task in tasks.items():
                try:
                    results[name] = await asyncio.wait_for(task, timeout=30.0)
                except asyncio.TimeoutError:
                    results[name] = ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message="Timeout en verificación de salud",
                        last_check=datetime.now()
                    )
                except Exception as e:
                    results[name] = ComponentHealth(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Error en verificación: {str(e)}",
                        last_check=datetime.now()
                    )
            
            # Determinar estado general
            overall_status = self._calculate_overall_status(results)
            
            # Calcular uptime
            uptime = (datetime.now() - self.start_time).total_seconds()
            
            # Crear resultado
            system_health = SystemHealth(
                overall_status=overall_status,
                components=results,
                timestamp=datetime.now(),
                uptime=uptime,
                version="1.0.0"  # TODO: Obtener de configuración
            )
            
            # Actualizar métricas
            self._update_metrics(system_health)
            
            # Guardar en cache
            self._last_health_check = system_health
            
            self.logger.info(
                "Verificación de salud completada",
                overall_status=overall_status.value,
                components={name: comp.status.value for name, comp in results.items()}
            )
            
            return system_health
            
        finally:
            self._check_in_progress = False
    
    async def _check_mdm_health(self) -> ComponentHealth:
        """Verificar salud del conector MDM.
        
        Returns:
            Estado de salud del MDM
        """
        start_time = datetime.now()
        
        try:
            async with ManageEngineMDMConnector(self.settings.mdm) as connector:
                # Verificar conectividad básica
                is_connected = await connector.test_connection()
                
                if not is_connected:
                    return ComponentHealth(
                        name="mdm",
                        status=HealthStatus.UNHEALTHY,
                        message="No se puede conectar al servidor MDM",
                        last_check=datetime.now(),
                        response_time=(datetime.now() - start_time).total_seconds()
                    )
                
                # Verificar funcionalidad básica
                try:
                    device_count = await connector.get_device_count()
                    
                    response_time = (datetime.now() - start_time).total_seconds()
                    
                    return ComponentHealth(
                        name="mdm",
                        status=HealthStatus.HEALTHY,
                        message=f"Conectado correctamente. {device_count} dispositivos disponibles",
                        last_check=datetime.now(),
                        response_time=response_time,
                        details={
                            "device_count": device_count,
                            "base_url": self.settings.mdm.base_url,
                            "ssl_verify": self.settings.mdm.ssl_verify
                        }
                    )
                    
                except Exception as e:
                    return ComponentHealth(
                        name="mdm",
                        status=HealthStatus.DEGRADED,
                        message=f"Conectado pero con problemas: {str(e)}",
                        last_check=datetime.now(),
                        response_time=(datetime.now() - start_time).total_seconds()
                    )
        
        except MDMConnectorError as e:
            return ComponentHealth(
                name="mdm",
                status=HealthStatus.UNHEALTHY,
                message=f"Error de conexión MDM: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
        
        except Exception as e:
            return ComponentHealth(
                name="mdm",
                status=HealthStatus.UNHEALTHY,
                message=f"Error inesperado: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
    
    async def _check_glpi_health(self) -> ComponentHealth:
        """Verificar salud del conector GLPI.
        
        Returns:
            Estado de salud de GLPI
        """
        start_time = datetime.now()
        
        try:
            async with GLPIConnector(self.settings.glpi) as connector:
                # Verificar conectividad básica
                is_connected = await connector.test_connection()
                
                if not is_connected:
                    return ComponentHealth(
                        name="glpi",
                        status=HealthStatus.UNHEALTHY,
                        message="No se puede conectar al servidor GLPI",
                        last_check=datetime.now(),
                        response_time=(datetime.now() - start_time).total_seconds()
                    )
                
                # Verificar funcionalidad básica
                try:
                    # Buscar computadoras (test básico)
                    computers = await connector.search_computers_by_serial("test_health_check")
                    
                    response_time = (datetime.now() - start_time).total_seconds()
                    
                    return ComponentHealth(
                        name="glpi",
                        status=HealthStatus.HEALTHY,
                        message="Conectado correctamente y funcional",
                        last_check=datetime.now(),
                        response_time=response_time,
                        details={
                            "base_url": self.settings.glpi.base_url,
                            "ssl_verify": self.settings.glpi.ssl_verify,
                            "search_test": "passed"
                        }
                    )
                    
                except Exception as e:
                    return ComponentHealth(
                        name="glpi",
                        status=HealthStatus.DEGRADED,
                        message=f"Conectado pero con problemas: {str(e)}",
                        last_check=datetime.now(),
                        response_time=(datetime.now() - start_time).total_seconds()
                    )
        
        except GLPIConnectorError as e:
            return ComponentHealth(
                name="glpi",
                status=HealthStatus.UNHEALTHY,
                message=f"Error de conexión GLPI: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
        
        except Exception as e:
            return ComponentHealth(
                name="glpi",
                status=HealthStatus.UNHEALTHY,
                message=f"Error inesperado: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
    
    async def _check_database_health(self) -> ComponentHealth:
        """Verificar salud de la base de datos.
        
        Returns:
            Estado de salud de la base de datos
        """
        start_time = datetime.now()
        
        try:
            from sqlalchemy import create_engine, text
            
            # Crear conexión temporal
            engine = create_engine(
                self.settings.database.url,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False} if "sqlite" in self.settings.database.url else {}
            )
            
            # Probar conexión
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
            
            response_time = (datetime.now() - start_time).total_seconds()
            
            return ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Base de datos conectada y funcional",
                last_check=datetime.now(),
                response_time=response_time,
                details={
                    "url": self.settings.database.url.split("@")[-1] if "@" in self.settings.database.url else "local",
                    "pool_size": self.settings.database.pool_size,
                    "max_overflow": self.settings.database.max_overflow
                }
            )
            
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Error de base de datos: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
    
    async def _check_system_health(self) -> ComponentHealth:
        """Verificar salud del sistema.
        
        Returns:
            Estado de salud del sistema
        """
        start_time = datetime.now()
        
        try:
            import psutil
            import os
            
            # Obtener métricas del sistema
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Verificar espacio en disco para logs
            log_dir = os.path.dirname(self.settings.logging.file) if self.settings.logging.file else "/tmp"
            if os.path.exists(log_dir):
                log_disk = psutil.disk_usage(log_dir)
                log_space_free_gb = log_disk.free / (1024**3)
            else:
                log_space_free_gb = 0
            
            # Determinar estado basado en métricas
            status = HealthStatus.HEALTHY
            messages = []
            
            if cpu_percent > 90:
                status = HealthStatus.DEGRADED
                messages.append(f"CPU alta: {cpu_percent:.1f}%")
            
            if memory.percent > 90:
                status = HealthStatus.DEGRADED
                messages.append(f"Memoria alta: {memory.percent:.1f}%")
            
            if disk.percent > 90:
                status = HealthStatus.DEGRADED
                messages.append(f"Disco lleno: {disk.percent:.1f}%")
            
            if log_space_free_gb < 1:
                status = HealthStatus.DEGRADED
                messages.append(f"Poco espacio para logs: {log_space_free_gb:.1f}GB")
            
            message = "Sistema funcionando correctamente"
            if messages:
                message = "; ".join(messages)
            
            response_time = (datetime.now() - start_time).total_seconds()
            
            return ComponentHealth(
                name="system",
                status=status,
                message=message,
                last_check=datetime.now(),
                response_time=response_time,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3),
                    "log_space_free_gb": log_space_free_gb,
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
                }
            )
            
        except ImportError:
            # psutil no disponible
            return ComponentHealth(
                name="system",
                status=HealthStatus.UNKNOWN,
                message="Métricas del sistema no disponibles (psutil no instalado)",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
        
        except Exception as e:
            return ComponentHealth(
                name="system",
                status=HealthStatus.UNHEALTHY,
                message=f"Error al obtener métricas del sistema: {str(e)}",
                last_check=datetime.now(),
                response_time=(datetime.now() - start_time).total_seconds()
            )
    
    def _calculate_overall_status(self, components: Dict[str, ComponentHealth]) -> HealthStatus:
        """Calcular estado general del sistema.
        
        Args:
            components: Componentes verificados
            
        Returns:
            Estado general del sistema
        """
        statuses = [comp.status for comp in components.values()]
        
        # Si algún componente crítico está unhealthy
        critical_components = ["mdm", "glpi", "database"]
        for comp_name in critical_components:
            if comp_name in components and components[comp_name].status == HealthStatus.UNHEALTHY:
                return HealthStatus.UNHEALTHY
        
        # Si algún componente está degraded
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        
        # Si algún componente está unhealthy (no crítico)
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.DEGRADED
        
        # Si algún componente es unknown
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.DEGRADED
        
        # Todos healthy
        return HealthStatus.HEALTHY
    
    def _update_metrics(self, system_health: SystemHealth) -> None:
        """Actualizar métricas de Prometheus.
        
        Args:
            system_health: Estado de salud del sistema
        """
        try:
            # Mapear estados a valores numéricos
            status_values = {
                HealthStatus.HEALTHY: 1,
                HealthStatus.DEGRADED: 0.5,
                HealthStatus.UNHEALTHY: 0,
                HealthStatus.UNKNOWN: -1
            }
            
            # Actualizar métricas por componente
            for comp_name, comp_health in system_health.components.items():
                # Estado de salud
                self.health_status_gauge.labels(component=comp_name).set(
                    status_values.get(comp_health.status, -1)
                )
                
                # Tiempo de respuesta
                if comp_health.response_time is not None:
                    self.response_time_histogram.labels(component=comp_name).observe(
                        comp_health.response_time
                    )
                
                # Contador de verificaciones
                self.health_check_counter.labels(
                    component=comp_name,
                    status=comp_health.status.value
                ).inc()
            
            # Estado general
            self.health_status_gauge.labels(component="overall").set(
                status_values.get(system_health.overall_status, -1)
            )
            
        except Exception as e:
            self.logger.warning(
                "Error al actualizar métricas de salud",
                error=str(e)
            )
    
    def get_last_health_check(self) -> Optional[SystemHealth]:
        """Obtener último resultado de verificación de salud.
        
        Returns:
            Último estado de salud o None si no hay
        """
        return self._last_health_check
    
    def is_healthy(self) -> bool:
        """Verificar si el sistema está saludable.
        
        Returns:
            True si el sistema está saludable
        """
        if not self._last_health_check:
            return False
        
        return self._last_health_check.overall_status == HealthStatus.HEALTHY
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Obtener resumen de salud del sistema.
        
        Returns:
            Diccionario con resumen de salud
        """
        if not self._last_health_check:
            return {
                "status": "unknown",
                "message": "No hay verificaciones de salud disponibles",
                "timestamp": None
            }
        
        health = self._last_health_check
        
        return {
            "status": health.overall_status.value,
            "message": self._get_health_message(health),
            "timestamp": health.timestamp.isoformat(),
            "uptime": health.uptime,
            "version": health.version,
            "components": {
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "response_time": comp.response_time
                }
                for name, comp in health.components.items()
            }
        }
    
    def _get_health_message(self, health: SystemHealth) -> str:
        """Generar mensaje de estado de salud.
        
        Args:
            health: Estado de salud del sistema
            
        Returns:
            Mensaje descriptivo del estado
        """
        if health.overall_status == HealthStatus.HEALTHY:
            return "Todos los componentes funcionan correctamente"
        
        elif health.overall_status == HealthStatus.DEGRADED:
            degraded_components = [
                name for name, comp in health.components.items()
                if comp.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
            ]
            return f"Problemas detectados en: {', '.join(degraded_components)}"
        
        elif health.overall_status == HealthStatus.UNHEALTHY:
            unhealthy_components = [
                name for name, comp in health.components.items()
                if comp.status == HealthStatus.UNHEALTHY
            ]
            return f"Componentes críticos con problemas: {', '.join(unhealthy_components)}"
        
        else:
            return "Estado de salud desconocido"