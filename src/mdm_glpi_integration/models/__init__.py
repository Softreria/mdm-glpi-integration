"""Modelos de datos para MDM-GLPI Integration."""

from .device import (
    DeviceStatus,
    OSType,
    DeviceUser,
    MDMDevice,
    GLPIDevice
)
from .database import (
    Base,
    SyncRecord,
    SyncLog,
    DeviceMapping,
    SyncStatistics,
    ConfigurationHistory,
    create_tables,
    drop_tables
)

__all__ = [
    # Device models
    "DeviceStatus",
    "OSType",
    "DeviceUser",
    "MDMDevice",
    "GLPIDevice",
    
    # Database models
    "Base",
    "SyncRecord",
    "SyncLog",
    "DeviceMapping",
    "SyncStatistics",
    "ConfigurationHistory",
    "create_tables",
    "drop_tables"
]