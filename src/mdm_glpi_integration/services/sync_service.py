"""Servicio principal de sincronización entre MDM y GLPI."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import structlog
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from ..config.settings import Settings
from ..connectors.mdm_connector import ManageEngineMDMConnector, MDMConnectorError
from ..connectors.glpi_connector import GLPIConnector, GLPIConnectorError
from ..models.device import MDMDevice, GLPIDevice
from ..utils.rate_limiter import AdaptiveRateLimiter

logger = structlog.get_logger()

# Base para modelos de base de datos
Base = declarative_base()


class SyncStatus(Enum):
    """Estados de sincronización."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncType(Enum):
    """Tipos de sincronización."""
    FULL = "full"
    INCREMENTAL = "incremental"
    MANUAL = "manual"


@dataclass
class SyncResult:
    """Resultado de una operación de sincronización."""
    success: bool
    devices_processed: int
    devices_created: int
    devices_updated: int
    devices_failed: int
    errors: List[str]
    duration: float
    sync_type: SyncType
    timestamp: datetime


class SyncRecord(Base):
    """Registro de sincronización en base de datos."""
    __tablename__ = "sync_records"
    
    id = Column(Integer, primary_key=True)
    device_id = Column(String(255), nullable=False, index=True)
    mdm_device_id = Column(String(255), nullable=False, index=True)
    glpi_computer_id = Column(Integer, nullable=True)
    last_sync = Column(DateTime, nullable=False)
    last_hash = Column(String(32), nullable=True)
    sync_status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SyncLog(Base):
    """Log de operaciones de sincronización."""
    __tablename__ = "sync_logs"
    
    id = Column(Integer, primary_key=True)
    sync_type = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    devices_processed = Column(Integer, default=0)
    devices_created = Column(Integer, default=0)
    devices_updated = Column(Integer, default=0)
    devices_failed = Column(Integer, default=0)
    duration = Column(Integer, nullable=True)  # en segundos
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class SyncService:
    """Servicio principal de sincronización."""
    
    def __init__(self, settings: Settings):
        """Inicializar el servicio de sincronización.
        
        Args:
            settings: Configuración de la aplicación
        """
        self.settings = settings
        self.logger = logger.bind(component="sync_service")
        
        # Configurar base de datos
        self.engine = create_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow
        )
        
        # Crear tablas
        Base.metadata.create_all(self.engine)
        
        # Session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Rate limiter adaptativo
        self.rate_limiter = AdaptiveRateLimiter(
            max_requests=30,  # Conservador para evitar sobrecargar APIs
            time_window=60
        )
        
        # Estado interno
        self._sync_in_progress = False
        self._last_full_sync: Optional[datetime] = None
        self._last_incremental_sync: Optional[datetime] = None
    
    async def full_sync(self) -> SyncResult:
        """Realizar sincronización completa.
        
        Returns:
            Resultado de la sincronización
        """
        return await self._perform_sync(SyncType.FULL)
    
    async def incremental_sync(self) -> SyncResult:
        """Realizar sincronización incremental.
        
        Returns:
            Resultado de la sincronización
        """
        return await self._perform_sync(SyncType.INCREMENTAL)
    
    async def manual_sync(
        self, 
        device_ids: Optional[List[str]] = None
    ) -> SyncResult:
        """Realizar sincronización manual.
        
        Args:
            device_ids: IDs específicos de dispositivos a sincronizar
            
        Returns:
            Resultado de la sincronización
        """
        return await self._perform_sync(SyncType.MANUAL, device_ids)
    
    async def _perform_sync(
        self, 
        sync_type: SyncType, 
        device_ids: Optional[List[str]] = None
    ) -> SyncResult:
        """Realizar sincronización.
        
        Args:
            sync_type: Tipo de sincronización
            device_ids: IDs específicos para sincronización manual
            
        Returns:
            Resultado de la sincronización
        """
        if self._sync_in_progress:
            raise RuntimeError("Sincronización ya en progreso")
        
        self._sync_in_progress = True
        start_time = datetime.now()
        
        # Crear log de sincronización
        db_session = self.SessionLocal()
        sync_log = SyncLog(
            sync_type=sync_type.value,
            status=SyncStatus.IN_PROGRESS.value,
            started_at=start_time
        )
        db_session.add(sync_log)
        db_session.commit()
        
        try:
            self.logger.info(
                "Iniciando sincronización",
                sync_type=sync_type.value,
                device_ids=device_ids
            )
            
            # Inicializar contadores
            devices_processed = 0
            devices_created = 0
            devices_updated = 0
            devices_failed = 0
            errors = []
            
            # Conectar a APIs
            async with ManageEngineMDMConnector(self.settings.mdm) as mdm_connector:
                async with GLPIConnector(self.settings.glpi) as glpi_connector:
                    
                    # Verificar conectividad
                    if not await mdm_connector.test_connection():
                        raise MDMConnectorError("No se puede conectar a MDM")
                    
                    if not await glpi_connector.test_connection():
                        raise GLPIConnectorError("No se puede conectar a GLPI")
                    
                    # Obtener dispositivos desde MDM
                    mdm_devices = await self._get_mdm_devices(
                        mdm_connector, sync_type, device_ids
                    )
                    
                    self.logger.info(
                        "Dispositivos obtenidos de MDM",
                        count=len(mdm_devices)
                    )
                    
                    # Procesar dispositivos en lotes
                    batch_size = self.settings.sync.batch_size
                    
                    for i in range(0, len(mdm_devices), batch_size):
                        batch = mdm_devices[i:i + batch_size]
                        
                        batch_results = await self._process_device_batch(
                            batch, glpi_connector, db_session
                        )
                        
                        # Actualizar contadores
                        devices_processed += batch_results["processed"]
                        devices_created += batch_results["created"]
                        devices_updated += batch_results["updated"]
                        devices_failed += batch_results["failed"]
                        errors.extend(batch_results["errors"])
                        
                        # Pausa entre lotes
                        if i + batch_size < len(mdm_devices):
                            await asyncio.sleep(1)
            
            # Calcular duración
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # Actualizar log
            sync_log.status = SyncStatus.SUCCESS.value
            sync_log.devices_processed = devices_processed
            sync_log.devices_created = devices_created
            sync_log.devices_updated = devices_updated
            sync_log.devices_failed = devices_failed
            sync_log.duration = int(duration)
            sync_log.completed_at = end_time
            
            if errors:
                sync_log.error_message = "\n".join(errors[:10])  # Primeros 10 errores
            
            db_session.commit()
            
            # Actualizar timestamps
            if sync_type == SyncType.FULL:
                self._last_full_sync = end_time
            elif sync_type == SyncType.INCREMENTAL:
                self._last_incremental_sync = end_time
            
            result = SyncResult(
                success=devices_failed == 0,
                devices_processed=devices_processed,
                devices_created=devices_created,
                devices_updated=devices_updated,
                devices_failed=devices_failed,
                errors=errors,
                duration=duration,
                sync_type=sync_type,
                timestamp=end_time
            )
            
            self.logger.info(
                "Sincronización completada",
                sync_type=sync_type.value,
                duration=duration,
                devices_processed=devices_processed,
                devices_created=devices_created,
                devices_updated=devices_updated,
                devices_failed=devices_failed
            )
            
            return result
            
        except Exception as e:
            # Actualizar log con error
            sync_log.status = SyncStatus.FAILED.value
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.now()
            db_session.commit()
            
            self.logger.error(
                "Error en sincronización",
                sync_type=sync_type.value,
                error=str(e)
            )
            
            raise
        
        finally:
            self._sync_in_progress = False
            db_session.close()
    
    async def _get_mdm_devices(
        self,
        mdm_connector: ManageEngineMDMConnector,
        sync_type: SyncType,
        device_ids: Optional[List[str]] = None
    ) -> List[MDMDevice]:
        """Obtener dispositivos desde MDM según el tipo de sincronización.
        
        Args:
            mdm_connector: Conector MDM
            sync_type: Tipo de sincronización
            device_ids: IDs específicos para sincronización manual
            
        Returns:
            Lista de dispositivos MDM
        """
        if sync_type == SyncType.MANUAL and device_ids:
            # Obtener dispositivos específicos
            devices = []
            for device_id in device_ids:
                device = await mdm_connector.get_device_details(device_id)
                if device:
                    devices.append(device)
            return devices
        
        elif sync_type == SyncType.INCREMENTAL and self._last_incremental_sync:
            # Obtener solo dispositivos modificados
            modified_since = self._last_incremental_sync - timedelta(minutes=5)  # Buffer
            return await mdm_connector.get_all_devices(
                modified_since=modified_since,
                batch_size=self.settings.sync.batch_size
            )
        
        else:
            # Sincronización completa
            return await mdm_connector.get_all_devices(
                batch_size=self.settings.sync.batch_size
            )
    
    async def _process_device_batch(
        self,
        devices: List[MDMDevice],
        glpi_connector: GLPIConnector,
        db_session: Session
    ) -> Dict[str, Any]:
        """Procesar un lote de dispositivos.
        
        Args:
            devices: Lista de dispositivos MDM
            glpi_connector: Conector GLPI
            db_session: Sesión de base de datos
            
        Returns:
            Diccionario con resultados del lote
        """
        processed = 0
        created = 0
        updated = 0
        failed = 0
        errors = []
        
        for device in devices:
            try:
                await self.rate_limiter.acquire()
                
                result = await self._sync_single_device(
                    device, glpi_connector, db_session
                )
                
                processed += 1
                
                if result["action"] == "created":
                    created += 1
                elif result["action"] == "updated":
                    updated += 1
                
                # Reportar éxito al rate limiter
                self.rate_limiter.report_success()
                
            except Exception as e:
                failed += 1
                error_msg = f"Error en dispositivo {device.device_id}: {str(e)}"
                errors.append(error_msg)
                
                self.logger.warning(
                    "Error al sincronizar dispositivo",
                    device_id=device.device_id,
                    error=str(e)
                )
                
                # Reportar error al rate limiter
                self.rate_limiter.report_error()
                
                # Actualizar registro con error
                self._update_sync_record(
                    db_session, device, None, SyncStatus.FAILED, str(e)
                )
        
        return {
            "processed": processed,
            "created": created,
            "updated": updated,
            "failed": failed,
            "errors": errors
        }
    
    async def _sync_single_device(
        self,
        mdm_device: MDMDevice,
        glpi_connector: GLPIConnector,
        db_session: Session
    ) -> Dict[str, Any]:
        """Sincronizar un dispositivo individual.
        
        Args:
            mdm_device: Dispositivo MDM
            glpi_connector: Conector GLPI
            db_session: Sesión de base de datos
            
        Returns:
            Diccionario con resultado de la sincronización
        """
        # Verificar si necesita sincronización
        sync_record = db_session.query(SyncRecord).filter_by(
            mdm_device_id=mdm_device.device_id
        ).first()
        
        current_hash = mdm_device.calculate_sync_hash()
        
        # Si existe y no ha cambiado, saltar
        if (sync_record and 
            sync_record.last_hash == current_hash and
            sync_record.sync_status == SyncStatus.SUCCESS.value):
            
            self.logger.debug(
                "Dispositivo sin cambios, saltando",
                device_id=mdm_device.device_id
            )
            
            return {"action": "skipped", "glpi_id": sync_record.glpi_computer_id}
        
        # Sincronizar con GLPI
        glpi_computer_id = await glpi_connector.sync_device_from_mdm(mdm_device)
        
        if glpi_computer_id:
            action = "updated" if sync_record else "created"
            
            # Actualizar registro de sincronización
            self._update_sync_record(
                db_session, mdm_device, glpi_computer_id, SyncStatus.SUCCESS
            )
            
            self.logger.debug(
                "Dispositivo sincronizado",
                device_id=mdm_device.device_id,
                glpi_id=glpi_computer_id,
                action=action
            )
            
            return {"action": action, "glpi_id": glpi_computer_id}
        
        else:
            raise Exception("No se pudo sincronizar con GLPI")
    
    def _update_sync_record(
        self,
        db_session: Session,
        mdm_device: MDMDevice,
        glpi_computer_id: Optional[int],
        status: SyncStatus,
        error_message: Optional[str] = None
    ) -> None:
        """Actualizar registro de sincronización.
        
        Args:
            db_session: Sesión de base de datos
            mdm_device: Dispositivo MDM
            glpi_computer_id: ID en GLPI
            status: Estado de sincronización
            error_message: Mensaje de error opcional
        """
        sync_record = db_session.query(SyncRecord).filter_by(
            mdm_device_id=mdm_device.device_id
        ).first()
        
        if sync_record:
            sync_record.last_sync = datetime.now()
            sync_record.sync_status = status.value
            sync_record.error_message = error_message
            
            if glpi_computer_id:
                sync_record.glpi_computer_id = glpi_computer_id
            
            if status == SyncStatus.SUCCESS:
                sync_record.last_hash = mdm_device.calculate_sync_hash()
        
        else:
            sync_record = SyncRecord(
                device_id=mdm_device.get_unique_identifier(),
                mdm_device_id=mdm_device.device_id,
                glpi_computer_id=glpi_computer_id,
                last_sync=datetime.now(),
                last_hash=mdm_device.calculate_sync_hash() if status == SyncStatus.SUCCESS else None,
                sync_status=status.value,
                error_message=error_message
            )
            db_session.add(sync_record)
        
        db_session.commit()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Obtener estado actual de sincronización.
        
        Returns:
            Diccionario con estado de sincronización
        """
        db_session = self.SessionLocal()
        
        try:
            # Último log de sincronización
            last_sync = db_session.query(SyncLog).order_by(
                SyncLog.started_at.desc()
            ).first()
            
            # Estadísticas de registros
            total_records = db_session.query(SyncRecord).count()
            successful_records = db_session.query(SyncRecord).filter_by(
                sync_status=SyncStatus.SUCCESS.value
            ).count()
            failed_records = db_session.query(SyncRecord).filter_by(
                sync_status=SyncStatus.FAILED.value
            ).count()
            
            return {
                "sync_in_progress": self._sync_in_progress,
                "last_full_sync": self._last_full_sync.isoformat() if self._last_full_sync else None,
                "last_incremental_sync": self._last_incremental_sync.isoformat() if self._last_incremental_sync else None,
                "last_sync_log": {
                    "type": last_sync.sync_type if last_sync else None,
                    "status": last_sync.status if last_sync else None,
                    "started_at": last_sync.started_at.isoformat() if last_sync else None,
                    "completed_at": last_sync.completed_at.isoformat() if last_sync and last_sync.completed_at else None,
                    "devices_processed": last_sync.devices_processed if last_sync else 0,
                    "devices_created": last_sync.devices_created if last_sync else 0,
                    "devices_updated": last_sync.devices_updated if last_sync else 0,
                    "devices_failed": last_sync.devices_failed if last_sync else 0,
                    "duration": last_sync.duration if last_sync else None
                },
                "statistics": {
                    "total_records": total_records,
                    "successful_records": successful_records,
                    "failed_records": failed_records,
                    "success_rate": round((successful_records / total_records * 100), 2) if total_records > 0 else 0
                }
            }
            
        finally:
            db_session.close()
    
    def get_failed_devices(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener dispositivos con errores de sincronización.
        
        Args:
            limit: Número máximo de registros
            
        Returns:
            Lista de dispositivos con errores
        """
        db_session = self.SessionLocal()
        
        try:
            failed_records = db_session.query(SyncRecord).filter_by(
                sync_status=SyncStatus.FAILED.value
            ).order_by(SyncRecord.updated_at.desc()).limit(limit).all()
            
            return [
                {
                    "device_id": record.device_id,
                    "mdm_device_id": record.mdm_device_id,
                    "last_sync": record.last_sync.isoformat(),
                    "error_message": record.error_message,
                    "updated_at": record.updated_at.isoformat()
                }
                for record in failed_records
            ]
            
        finally:
            db_session.close()
    
    async def retry_failed_devices(self, device_ids: Optional[List[str]] = None) -> SyncResult:
        """Reintentar sincronización de dispositivos fallidos.
        
        Args:
            device_ids: IDs específicos a reintentar, None para todos los fallidos
            
        Returns:
            Resultado de la sincronización
        """
        db_session = self.SessionLocal()
        
        try:
            # Obtener dispositivos fallidos
            query = db_session.query(SyncRecord).filter_by(
                sync_status=SyncStatus.FAILED.value
            )
            
            if device_ids:
                query = query.filter(SyncRecord.mdm_device_id.in_(device_ids))
            
            failed_records = query.all()
            failed_device_ids = [record.mdm_device_id for record in failed_records]
            
            if not failed_device_ids:
                return SyncResult(
                    success=True,
                    devices_processed=0,
                    devices_created=0,
                    devices_updated=0,
                    devices_failed=0,
                    errors=[],
                    duration=0.0,
                    sync_type=SyncType.MANUAL,
                    timestamp=datetime.now()
                )
            
            # Realizar sincronización manual
            return await self.manual_sync(failed_device_ids)
            
        finally:
            db_session.close()
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """Limpiar logs antiguos.
        
        Args:
            days: Días de antigüedad para limpiar
            
        Returns:
            Número de registros eliminados
        """
        db_session = self.SessionLocal()
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Eliminar logs antiguos
            deleted_logs = db_session.query(SyncLog).filter(
                SyncLog.started_at < cutoff_date
            ).delete()
            
            # Eliminar registros de sincronización antiguos exitosos
            deleted_records = db_session.query(SyncRecord).filter(
                SyncRecord.updated_at < cutoff_date,
                SyncRecord.sync_status == SyncStatus.SUCCESS.value
            ).delete()
            
            db_session.commit()
            
            total_deleted = deleted_logs + deleted_records
            
            self.logger.info(
                "Limpieza de logs completada",
                deleted_logs=deleted_logs,
                deleted_records=deleted_records,
                total_deleted=total_deleted
            )
            
            return total_deleted
            
        finally:
            db_session.close()