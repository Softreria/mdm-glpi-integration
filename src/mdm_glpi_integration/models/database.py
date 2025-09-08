"""Modelos de base de datos para MDM-GLPI Integration."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Boolean, Float,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class SyncRecord(Base):
    """Registro de sincronización de dispositivos."""
    
    __tablename__ = "sync_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), nullable=False, index=True)
    mdm_device_id = Column(String(255), nullable=False)
    glpi_computer_id = Column(Integer, nullable=True)
    
    # Información de sincronización
    sync_type = Column(String(50), nullable=False)  # full, incremental, manual
    sync_status = Column(String(50), nullable=False)  # success, error, pending
    sync_hash = Column(String(64), nullable=True)  # Hash de los datos para detectar cambios
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    last_sync_at = Column(DateTime, nullable=True)
    
    # Información adicional
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # Metadatos del dispositivo
    device_name = Column(String(255), nullable=True)
    device_type = Column(String(100), nullable=True)
    serial_number = Column(String(255), nullable=True)
    os_name = Column(String(100), nullable=True)
    os_version = Column(String(100), nullable=True)
    
    # Relaciones
    logs = relationship("SyncLog", back_populates="sync_record", cascade="all, delete-orphan")
    
    # Índices
    __table_args__ = (
        Index("idx_device_id_sync_type", "device_id", "sync_type"),
        Index("idx_sync_status_created", "sync_status", "created_at"),
        Index("idx_last_sync_at", "last_sync_at"),
        UniqueConstraint("device_id", name="uq_sync_records_device_id"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<SyncRecord(id={self.id}, device_id='{self.device_id}', "
            f"status='{self.sync_status}', last_sync='{self.last_sync_at}')>"
        )


class SyncLog(Base):
    """Log detallado de operaciones de sincronización."""
    
    __tablename__ = "sync_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_record_id = Column(Integer, ForeignKey("sync_records.id"), nullable=False)
    
    # Información del log
    level = Column(String(20), nullable=False)  # INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)  # JSON con detalles adicionales
    
    # Contexto de la operación
    operation = Column(String(100), nullable=True)  # create, update, delete, etc.
    component = Column(String(100), nullable=True)  # mdm, glpi, sync
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Información de rendimiento
    duration_ms = Column(Float, nullable=True)
    
    # Relaciones
    sync_record = relationship("SyncRecord", back_populates="logs")
    
    # Índices
    __table_args__ = (
        Index("idx_sync_record_level", "sync_record_id", "level"),
        Index("idx_created_at_level", "created_at", "level"),
        Index("idx_operation_component", "operation", "component"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<SyncLog(id={self.id}, level='{self.level}', "
            f"operation='{self.operation}', created='{self.created_at}')>"
        )


class DeviceMapping(Base):
    """Mapeo entre dispositivos MDM y computadoras GLPI."""
    
    __tablename__ = "device_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificadores
    mdm_device_id = Column(String(255), nullable=False, unique=True)
    glpi_computer_id = Column(Integer, nullable=False, unique=True)
    
    # Información de mapeo
    mapping_type = Column(String(50), nullable=False, default="automatic")  # automatic, manual
    confidence_score = Column(Float, nullable=True)  # Confianza del mapeo automático
    
    # Metadatos
    device_serial = Column(String(255), nullable=True)
    device_name = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    verified_at = Column(DateTime, nullable=True)  # Última verificación manual
    
    # Estado
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Índices
    __table_args__ = (
        Index("idx_mdm_device_id", "mdm_device_id"),
        Index("idx_glpi_computer_id", "glpi_computer_id"),
        Index("idx_device_serial", "device_serial"),
        Index("idx_is_active_updated", "is_active", "updated_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<DeviceMapping(id={self.id}, mdm_id='{self.mdm_device_id}', "
            f"glpi_id={self.glpi_computer_id}, active={self.is_active})>"
        )


class SyncStatistics(Base):
    """Estadísticas de sincronización por período."""
    
    __tablename__ = "sync_statistics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Período
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(String(20), nullable=False)  # hourly, daily, weekly, monthly
    
    # Estadísticas de sincronización
    total_syncs = Column(Integer, nullable=False, default=0)
    successful_syncs = Column(Integer, nullable=False, default=0)
    failed_syncs = Column(Integer, nullable=False, default=0)
    
    # Estadísticas de dispositivos
    devices_processed = Column(Integer, nullable=False, default=0)
    devices_created = Column(Integer, nullable=False, default=0)
    devices_updated = Column(Integer, nullable=False, default=0)
    devices_deleted = Column(Integer, nullable=False, default=0)
    
    # Rendimiento
    avg_sync_duration = Column(Float, nullable=True)
    max_sync_duration = Column(Float, nullable=True)
    min_sync_duration = Column(Float, nullable=True)
    
    # Errores
    mdm_errors = Column(Integer, nullable=False, default=0)
    glpi_errors = Column(Integer, nullable=False, default=0)
    mapping_errors = Column(Integer, nullable=False, default=0)
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Índices
    __table_args__ = (
        Index("idx_period_type_start", "period_type", "period_start"),
        Index("idx_period_start_end", "period_start", "period_end"),
        UniqueConstraint("period_start", "period_end", "period_type", 
                        name="uq_sync_statistics_period"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<SyncStatistics(id={self.id}, period='{self.period_type}', "
            f"start='{self.period_start}', syncs={self.total_syncs})>"
        )


class ConfigurationHistory(Base):
    """Historial de cambios de configuración."""
    
    __tablename__ = "configuration_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Información del cambio
    config_section = Column(String(100), nullable=False)  # mdm, glpi, sync, etc.
    config_key = Column(String(255), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    
    # Contexto
    change_reason = Column(String(255), nullable=True)
    changed_by = Column(String(100), nullable=True)  # user, system, api
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    # Índices
    __table_args__ = (
        Index("idx_config_section_key", "config_section", "config_key"),
        Index("idx_created_at", "created_at"),
        Index("idx_changed_by", "changed_by"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<ConfigurationHistory(id={self.id}, section='{self.config_section}', "
            f"key='{self.config_key}', created='{self.created_at}')>"
        )


# Funciones de utilidad para crear tablas
def create_tables(engine):
    """Crear todas las tablas en la base de datos.
    
    Args:
        engine: Motor de SQLAlchemy
    """
    Base.metadata.create_all(engine)


def drop_tables(engine):
    """Eliminar todas las tablas de la base de datos.
    
    Args:
        engine: Motor de SQLAlchemy
    """
    Base.metadata.drop_all(engine)