"""Servicio de métricas y monitoreo con Prometheus."""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from functools import wraps

import structlog
from prometheus_client import (
    Counter, Gauge, Histogram, Summary, Info,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)

from ..config.settings import Settings

logger = structlog.get_logger()


class MetricsService:
    """Servicio de métricas y monitoreo."""
    
    def __init__(self, settings: Settings, registry: Optional[CollectorRegistry] = None):
        """Inicializar el servicio de métricas.
        
        Args:
            settings: Configuración de la aplicación
            registry: Registro de métricas personalizado
        """
        self.settings = settings
        self.logger = logger.bind(component="metrics_service")
        self.registry = registry or CollectorRegistry()
        
        # Información de la aplicación
        self.app_info = Info(
            'mdm_glpi_integration_info',
            'Information about the MDM-GLPI integration application',
            registry=self.registry
        )
        
        # Métricas de sincronización
        self.sync_operations_total = Counter(
            'mdm_glpi_sync_operations_total',
            'Total number of sync operations',
            ['sync_type', 'status'],
            registry=self.registry
        )
        
        self.sync_duration_seconds = Histogram(
            'mdm_glpi_sync_duration_seconds',
            'Duration of sync operations in seconds',
            ['sync_type'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],
            registry=self.registry
        )
        
        self.devices_processed_total = Counter(
            'mdm_glpi_devices_processed_total',
            'Total number of devices processed',
            ['operation', 'status'],
            registry=self.registry
        )
        
        self.devices_in_sync = Gauge(
            'mdm_glpi_devices_in_sync',
            'Number of devices currently in sync',
            registry=self.registry
        )
        
        self.last_sync_timestamp = Gauge(
            'mdm_glpi_last_sync_timestamp',
            'Timestamp of last successful sync',
            ['sync_type'],
            registry=self.registry
        )
        
        # Métricas de API
        self.api_requests_total = Counter(
            'mdm_glpi_api_requests_total',
            'Total number of API requests',
            ['service', 'method', 'status_code'],
            registry=self.registry
        )
        
        self.api_request_duration_seconds = Histogram(
            'mdm_glpi_api_request_duration_seconds',
            'Duration of API requests in seconds',
            ['service', 'method'],
            buckets=[0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50],
            registry=self.registry
        )
        
        self.api_rate_limit_hits = Counter(
            'mdm_glpi_api_rate_limit_hits_total',
            'Total number of rate limit hits',
            ['service'],
            registry=self.registry
        )
        
        # Métricas de errores
        self.errors_total = Counter(
            'mdm_glpi_errors_total',
            'Total number of errors',
            ['component', 'error_type'],
            registry=self.registry
        )
        
        self.connection_errors_total = Counter(
            'mdm_glpi_connection_errors_total',
            'Total number of connection errors',
            ['service'],
            registry=self.registry
        )
        
        # Métricas de base de datos
        self.database_operations_total = Counter(
            'mdm_glpi_database_operations_total',
            'Total number of database operations',
            ['operation', 'table', 'status'],
            registry=self.registry
        )
        
        self.database_connection_pool_size = Gauge(
            'mdm_glpi_database_connection_pool_size',
            'Current database connection pool size',
            registry=self.registry
        )
        
        # Métricas de sistema
        self.memory_usage_bytes = Gauge(
            'mdm_glpi_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )
        
        self.cpu_usage_percent = Gauge(
            'mdm_glpi_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        # Métricas de salud
        self.health_status = Gauge(
            'mdm_glpi_health_status',
            'Health status of components (1=healthy, 0.5=degraded, 0=unhealthy)',
            ['component'],
            registry=self.registry
        )
        
        self.uptime_seconds = Gauge(
            'mdm_glpi_uptime_seconds',
            'Application uptime in seconds',
            registry=self.registry
        )
        
        # Métricas de configuración
        self.config_reloads_total = Counter(
            'mdm_glpi_config_reloads_total',
            'Total number of configuration reloads',
            ['status'],
            registry=self.registry
        )
        
        # Inicializar información de la aplicación
        self._initialize_app_info()
        
        # Tiempo de inicio
        self.start_time = time.time()
    
    def _initialize_app_info(self) -> None:
        """Inicializar información de la aplicación."""
        self.app_info.info({
            'version': '1.0.0',  # TODO: Obtener de configuración
            'mdm_base_url': self.settings.mdm.base_url,
            'glpi_base_url': self.settings.glpi.base_url,
            'sync_full_cron': self.settings.sync.full_sync_cron,
            'sync_incremental_cron': self.settings.sync.incremental_sync_cron,
            'batch_size': str(self.settings.sync.batch_size)
        })
    
    # Decoradores para métricas automáticas
    def track_sync_operation(self, sync_type: str):
        """Decorador para rastrear operaciones de sincronización.
        
        Args:
            sync_type: Tipo de sincronización
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                status = 'success'
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    status = 'error'
                    self.record_error('sync_service', type(e).__name__)
                    raise
                finally:
                    duration = time.time() - start_time
                    self.sync_operations_total.labels(
                        sync_type=sync_type,
                        status=status
                    ).inc()
                    self.sync_duration_seconds.labels(sync_type=sync_type).observe(duration)
                    
                    if status == 'success':
                        self.last_sync_timestamp.labels(sync_type=sync_type).set(time.time())
            
            return wrapper
        return decorator
    
    def track_api_request(self, service: str, method: str):
        """Decorador para rastrear requests de API.
        
        Args:
            service: Nombre del servicio (mdm, glpi)
            method: Método de la API
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                status_code = '200'
                
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    # Intentar extraer código de estado del error
                    if hasattr(e, 'status_code'):
                        status_code = str(e.status_code)
                    elif 'rate limit' in str(e).lower():
                        status_code = '429'
                        self.api_rate_limit_hits.labels(service=service).inc()
                    elif 'timeout' in str(e).lower():
                        status_code = '408'
                    elif 'connection' in str(e).lower():
                        status_code = '503'
                        self.connection_errors_total.labels(service=service).inc()
                    else:
                        status_code = '500'
                    
                    raise
                finally:
                    duration = time.time() - start_time
                    self.api_requests_total.labels(
                        service=service,
                        method=method,
                        status_code=status_code
                    ).inc()
                    self.api_request_duration_seconds.labels(
                        service=service,
                        method=method
                    ).observe(duration)
            
            return wrapper
        return decorator
    
    @contextmanager
    def track_database_operation(self, operation: str, table: str):
        """Context manager para rastrear operaciones de base de datos.
        
        Args:
            operation: Tipo de operación (select, insert, update, delete)
            table: Nombre de la tabla
        """
        start_time = time.time()
        status = 'success'
        
        try:
            yield
        except Exception as e:
            status = 'error'
            self.record_error('database', type(e).__name__)
            raise
        finally:
            self.database_operations_total.labels(
                operation=operation,
                table=table,
                status=status
            ).inc()
    
    # Métodos para registrar métricas específicas
    def record_device_processed(self, operation: str, status: str) -> None:
        """Registrar dispositivo procesado.
        
        Args:
            operation: Tipo de operación (create, update, delete, skip)
            status: Estado (success, error)
        """
        self.devices_processed_total.labels(
            operation=operation,
            status=status
        ).inc()
    
    def set_devices_in_sync(self, count: int) -> None:
        """Establecer número de dispositivos en sincronización.
        
        Args:
            count: Número de dispositivos
        """
        self.devices_in_sync.set(count)
    
    def record_error(self, component: str, error_type: str) -> None:
        """Registrar error.
        
        Args:
            component: Componente donde ocurrió el error
            error_type: Tipo de error
        """
        self.errors_total.labels(
            component=component,
            error_type=error_type
        ).inc()
    
    def record_config_reload(self, status: str) -> None:
        """Registrar recarga de configuración.
        
        Args:
            status: Estado de la recarga (success, error)
        """
        self.config_reloads_total.labels(status=status).inc()
    
    def update_system_metrics(self) -> None:
        """Actualizar métricas del sistema."""
        try:
            import psutil
            import os
            
            # Memoria
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            self.memory_usage_bytes.set(memory_info.rss)
            
            # CPU
            cpu_percent = process.cpu_percent()
            self.cpu_usage_percent.set(cpu_percent)
            
            # Uptime
            uptime = time.time() - self.start_time
            self.uptime_seconds.set(uptime)
            
        except ImportError:
            self.logger.debug("psutil no disponible para métricas del sistema")
        except Exception as e:
            self.logger.warning(
                "Error al actualizar métricas del sistema",
                error=str(e)
            )
    
    def update_health_metrics(self, health_data: Dict[str, Any]) -> None:
        """Actualizar métricas de salud.
        
        Args:
            health_data: Datos de salud del sistema
        """
        try:
            # Mapear estados a valores numéricos
            status_values = {
                'healthy': 1.0,
                'degraded': 0.5,
                'unhealthy': 0.0,
                'unknown': -1.0
            }
            
            # Estado general
            overall_status = health_data.get('status', 'unknown')
            self.health_status.labels(component='overall').set(
                status_values.get(overall_status, -1.0)
            )
            
            # Estados de componentes
            components = health_data.get('components', {})
            for comp_name, comp_data in components.items():
                comp_status = comp_data.get('status', 'unknown')
                self.health_status.labels(component=comp_name).set(
                    status_values.get(comp_status, -1.0)
                )
            
        except Exception as e:
            self.logger.warning(
                "Error al actualizar métricas de salud",
                error=str(e)
            )
    
    def get_metrics(self) -> str:
        """Obtener métricas en formato Prometheus.
        
        Returns:
            Métricas en formato texto de Prometheus
        """
        # Actualizar métricas del sistema antes de exportar
        self.update_system_metrics()
        
        return generate_latest(self.registry)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Obtener resumen de métricas principales.
        
        Returns:
            Diccionario con resumen de métricas
        """
        try:
            # Obtener valores actuales de métricas principales
            summary = {
                'uptime_seconds': self.uptime_seconds._value._value if hasattr(self.uptime_seconds, '_value') else 0,
                'sync_operations': {
                    'total': sum(self.sync_operations_total._value.values()) if hasattr(self.sync_operations_total, '_value') else 0
                },
                'devices_processed': {
                    'total': sum(self.devices_processed_total._value.values()) if hasattr(self.devices_processed_total, '_value') else 0
                },
                'api_requests': {
                    'total': sum(self.api_requests_total._value.values()) if hasattr(self.api_requests_total, '_value') else 0
                },
                'errors': {
                    'total': sum(self.errors_total._value.values()) if hasattr(self.errors_total, '_value') else 0
                },
                'health_status': {
                    'overall': self.health_status.labels(component='overall')._value._value if hasattr(self.health_status.labels(component='overall'), '_value') else -1
                }
            }
            
            return summary
            
        except Exception as e:
            self.logger.warning(
                "Error al generar resumen de métricas",
                error=str(e)
            )
            return {}
    
    def reset_metrics(self) -> None:
        """Resetear todas las métricas (útil para testing)."""
        self.logger.warning("Reseteando todas las métricas")
        
        # Crear nuevo registro
        self.registry = CollectorRegistry()
        
        # Reinicializar todas las métricas
        self.__init__(self.settings, self.registry)
    
    def export_metrics_to_file(self, file_path: str) -> None:
        """Exportar métricas a archivo.
        
        Args:
            file_path: Ruta del archivo donde guardar las métricas
        """
        try:
            metrics_data = self.get_metrics()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(metrics_data)
            
            self.logger.info(
                "Métricas exportadas a archivo",
                file_path=file_path
            )
            
        except Exception as e:
            self.logger.error(
                "Error al exportar métricas a archivo",
                file_path=file_path,
                error=str(e)
            )
            raise
    
    def get_content_type(self) -> str:
        """Obtener content type para métricas de Prometheus.
        
        Returns:
            Content type para HTTP response
        """
        return CONTENT_TYPE_LATEST