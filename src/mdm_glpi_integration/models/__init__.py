"""Modelos de datos para MDM-GLPI Integration."""

from .device import (
    DeviceStatus,
    OSType,
    DeviceUser,
    MDMDevice,
    GLPIDevice,
    GLPIPhone
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
    "GLPIPhone",
    
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