"""Modelos de datos para dispositivos."""

from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


class DeviceStatus(Enum):
    """Estados posibles de un dispositivo."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOST = "lost"
    WIPED = "wiped"
    PENDING = "pending"
    UNKNOWN = "unknown"


class OSType(Enum):
    """Tipos de sistema operativo."""
    IOS = "ios"
    ANDROID = "android"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


@dataclass
class DeviceUser:
    """Información del usuario de un dispositivo."""
    user_id: str
    email: str
    name: str
    department: Optional[str] = None
    phone: Optional[str] = None

    def __post_init__(self):
        """Validación post-inicialización."""
        if not self.user_id:
            raise ValueError("user_id es requerido")
        if not self.email:
            raise ValueError("email es requerido")
        if not self.name:
            raise ValueError("name es requerido")


@dataclass
class MDMDevice:
    """Modelo de dispositivo desde ManageEngine MDM."""
    
    # Identificadores únicos
    device_id: str
    device_name: str
    
    # Información del hardware
    model: str
    manufacturer: str
    serial_number: str
    
    # Sistema operativo
    os_type: str
    os_version: str
    
    # Campos opcionales
    imei: Optional[str] = None
    
    # Usuario asignado
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    
    # Fechas importantes
    enrollment_date: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    
    # Estado del dispositivo
    status: str = "unknown"
    is_supervised: bool = False
    is_lost_mode: bool = False
    
    # Información técnica
    battery_level: Optional[int] = None
    storage_total: Optional[int] = None  # en MB
    storage_available: Optional[int] = None  # en MB
    
    # Conectividad
    wifi_mac: Optional[str] = None
    cellular_technology: Optional[str] = None
    carrier_settings_version: Optional[str] = None
    phone_number: Optional[str] = None
    
    # Datos originales de la API
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Metadatos de sincronización
    last_sync: Optional[datetime] = field(default=None, init=False)
    sync_hash: Optional[str] = field(default=None, init=False)
    
    def __post_init__(self):
        """Validación y normalización post-inicialización."""
        # Validaciones básicas
        if not self.device_id:
            raise ValueError("device_id es requerido")
        if not self.device_name:
            raise ValueError("device_name es requerido")
        
        # Normalizar OS type
        self.os_type = self._normalize_os_type(self.os_type)
        
        # Normalizar status
        self.status = self._normalize_status(self.status)
        
        # Validar battery level
        if self.battery_level is not None:
            if not 0 <= self.battery_level <= 100:
                self.battery_level = None
    
    def _normalize_os_type(self, os_type: str) -> str:
        """Normalizar el tipo de sistema operativo."""
        if not os_type:
            return OSType.UNKNOWN.value
        
        os_lower = os_type.lower()
        
        if "ios" in os_lower or "iphone" in os_lower or "ipad" in os_lower:
            return OSType.IOS.value
        elif "android" in os_lower:
            return OSType.ANDROID.value
        elif "windows" in os_lower:
            return OSType.WINDOWS.value
        elif "mac" in os_lower or "darwin" in os_lower:
            return OSType.MACOS.value
        else:
            return OSType.UNKNOWN.value
    
    def _normalize_status(self, status: str) -> str:
        """Normalizar el estado del dispositivo."""
        if not status:
            return DeviceStatus.UNKNOWN.value
        
        status_lower = status.lower()
        
        if status_lower in ["active", "enrolled", "managed"]:
            return DeviceStatus.ACTIVE.value
        elif status_lower in ["inactive", "unmanaged", "retired"]:
            return DeviceStatus.INACTIVE.value
        elif status_lower in ["lost", "missing"]:
            return DeviceStatus.LOST.value
        elif status_lower in ["wiped", "erased"]:
            return DeviceStatus.WIPED.value
        elif status_lower in ["pending", "enrolling"]:
            return DeviceStatus.PENDING.value
        else:
            return DeviceStatus.UNKNOWN.value
    
    @property
    def is_mobile(self) -> bool:
        """Verificar si es un dispositivo móvil."""
        return self.os_type in [OSType.IOS.value, OSType.ANDROID.value]
    
    @property
    def is_active(self) -> bool:
        """Verificar si el dispositivo está activo."""
        return self.status == DeviceStatus.ACTIVE.value
    
    @property
    def storage_used_mb(self) -> Optional[int]:
        """Calcular almacenamiento usado en MB."""
        if self.storage_total is not None and self.storage_available is not None:
            return self.storage_total - self.storage_available
        return None
    
    @property
    def storage_used_percent(self) -> Optional[float]:
        """Calcular porcentaje de almacenamiento usado."""
        if self.storage_total and self.storage_total > 0:
            used = self.storage_used_mb
            if used is not None:
                return round((used / self.storage_total) * 100, 2)
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para serialización."""
        data = {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "serial_number": self.serial_number,
            "imei": self.imei,
            "os_type": self.os_type,
            "os_version": self.os_version,
            "user_email": self.user_email,
            "user_name": self.user_name,
            "status": self.status,
            "is_supervised": self.is_supervised,
            "is_lost_mode": self.is_lost_mode,
            "battery_level": self.battery_level,
            "storage_total": self.storage_total,
            "storage_available": self.storage_available,
            "wifi_mac": self.wifi_mac,
            "cellular_technology": self.cellular_technology,
            "carrier_settings_version": self.carrier_settings_version,
            "phone_number": self.phone_number,
            "is_mobile": self.is_mobile,
            "is_active": self.is_active,
            "storage_used_mb": self.storage_used_mb,
            "storage_used_percent": self.storage_used_percent
        }
        
        # Agregar fechas como ISO strings
        if self.enrollment_date:
            data["enrollment_date"] = self.enrollment_date.isoformat()
        if self.last_seen:
            data["last_seen"] = self.last_seen.isoformat()
        if self.last_sync:
            data["last_sync"] = self.last_sync.isoformat()
        
        return data
    
    def get_unique_identifier(self) -> str:
        """Obtener identificador único para el dispositivo."""
        # Preferir IMEI para móviles, serial number para otros
        if self.is_mobile and self.imei:
            return self.imei
        elif self.serial_number:
            return self.serial_number
        else:
            return self.device_id
    
    def calculate_sync_hash(self) -> str:
        """Calcular hash para detectar cambios."""
        import hashlib
        
        # Campos relevantes para detectar cambios
        relevant_fields = [
            self.device_name,
            self.model,
            self.manufacturer,
            self.os_version,
            self.user_email,
            self.user_name,
            self.status,
            str(self.is_supervised),
            str(self.is_lost_mode),
            str(self.battery_level),
            str(self.storage_total),
            str(self.storage_available),
            self.phone_number
        ]
        
        # Crear string concatenado
        concat_string = "|".join(str(field) for field in relevant_fields)
        
        # Calcular hash MD5
        return hashlib.md5(concat_string.encode()).hexdigest()
    
    def has_changed(self, other_hash: str) -> bool:
        """Verificar si el dispositivo ha cambiado comparando hashes."""
        current_hash = self.calculate_sync_hash()
        return current_hash != other_hash
    
    def update_sync_metadata(self):
        """Actualizar metadatos de sincronización."""
        self.last_sync = datetime.now()
        self.sync_hash = self.calculate_sync_hash()


@dataclass
class GLPIDevice:
    """Modelo de dispositivo para GLPI."""
    
    # Identificadores
    id: Optional[int] = None  # ID en GLPI
    name: str = ""
    
    # Información básica
    serial: str = ""
    otherserial: str = ""  # Para IMEI u otro identificador
    
    # Tipo y modelo
    computertypes_id: Optional[int] = None
    computermodels_id: Optional[int] = None
    manufacturers_id: Optional[int] = None
    
    # Sistema operativo
    operatingsystems_id: Optional[int] = None
    operatingsystemversions_id: Optional[int] = None
    
    # Usuario y ubicación
    users_id: Optional[int] = None
    locations_id: Optional[int] = None
    
    # Estado
    states_id: Optional[int] = None
    is_deleted: bool = False
    
    # Fechas
    date_creation: Optional[datetime] = None
    date_mod: Optional[datetime] = None
    
    # Comentarios y notas
    comment: str = ""
    
    # Campos personalizados para MDM
    mdm_device_id: str = ""
    mdm_last_seen: Optional[datetime] = None
    mdm_enrollment_date: Optional[datetime] = None
    mdm_status: str = ""
    mdm_is_supervised: bool = False
    mdm_battery_level: Optional[int] = None
    mdm_storage_total: Optional[int] = None
    mdm_storage_available: Optional[int] = None
    
    def to_glpi_format(self) -> Dict[str, Any]:
        """Convertir a formato esperado por GLPI API."""
        data = {
            "name": self.name,
            "serial": self.serial,
            "comment": self.comment,
            "is_deleted": self.is_deleted
        }
        
        # Agregar campos opcionales si tienen valor
        optional_fields = [
            "otherserial", "computertypes_id", "computermodels_id",
            "manufacturers_id", "operatingsystems_id", "operatingsystemversions_id",
            "users_id", "locations_id", "states_id"
        ]
        
        for field in optional_fields:
            value = getattr(self, field)
            if value is not None:
                data[field] = value
        
        # Agregar ID si existe (para updates)
        if self.id is not None:
            data["id"] = self.id
        
        return data
    
    @classmethod
    def from_mdm_device(cls, mdm_device: MDMDevice) -> "GLPIDevice":
        """Crear dispositivo GLPI desde dispositivo MDM."""
        # Crear comentario con información MDM
        comment_parts = [
            f"Dispositivo sincronizado desde MDM",
            f"ID MDM: {mdm_device.device_id}",
            f"OS: {mdm_device.os_type} {mdm_device.os_version}"
        ]
        
        if mdm_device.user_email:
            comment_parts.append(f"Usuario: {mdm_device.user_email}")
        
        if mdm_device.battery_level is not None:
            comment_parts.append(f"Batería: {mdm_device.battery_level}%")
        
        if mdm_device.storage_used_percent is not None:
            comment_parts.append(f"Almacenamiento usado: {mdm_device.storage_used_percent}%")
        
        return cls(
            name=mdm_device.device_name,
            serial=mdm_device.serial_number,
            otherserial=mdm_device.imei or "",
            comment="\n".join(comment_parts),
            mdm_device_id=mdm_device.device_id,
            mdm_last_seen=mdm_device.last_seen,
            mdm_enrollment_date=mdm_device.enrollment_date,
            mdm_status=mdm_device.status,
            mdm_is_supervised=mdm_device.is_supervised,
            mdm_battery_level=mdm_device.battery_level,
            mdm_storage_total=mdm_device.storage_total,
            mdm_storage_available=mdm_device.storage_available
        )