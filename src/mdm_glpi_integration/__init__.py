"""MDM-GLPI Integration Package.

Este paquete proporciona integración entre ManageEngine MDM y GLPI
para centralizar el inventario de dispositivos móviles.
"""

__version__ = "1.0.0"
__author__ = "David Hernández"
__email__ = "david@softreria.com"
__description__ = "Integración entre ManageEngine MDM y GLPI"

from .config.settings import Settings
from .models.device import Device
from .services.sync_service import SyncService

__all__ = [
    "Settings",
    "Device", 
    "SyncService",
    "__version__",
    "__author__",
    "__email__",
    "__description__",
]