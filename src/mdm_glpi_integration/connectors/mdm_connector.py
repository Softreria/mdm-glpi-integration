"""Conector para ManageEngine MDM API."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import httpx
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from ..config.settings import MDMConfig
from ..models.device import MDMDevice, DeviceUser
from ..utils.rate_limiter import RateLimiter

logger = structlog.get_logger()


class MDMConnectorError(Exception):
    """Excepción base para errores del conector MDM."""
    pass


class MDMAuthenticationError(MDMConnectorError):
    """Error de autenticación con MDM."""
    pass


class MDMAPIError(MDMConnectorError):
    """Error de API de MDM."""
    pass


class MDMRateLimitError(MDMConnectorError):
    """Error de límite de velocidad de MDM."""
    pass


class ManageEngineMDMConnector:
    """Conector para ManageEngine MDM API."""

    def __init__(self, config: MDMConfig):
        """Inicializar el conector MDM.
        
        Args:
            config: Configuración de MDM
        """
        self.config = config
        self.logger = logger.bind(component="mdm_connector")
        self.rate_limiter = RateLimiter(config.rate_limit, 60)  # requests per minute
        
        # Cliente HTTP
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            verify=config.verify_ssl,
            headers={
                "Authorization": f"Zoho-oauthtoken {config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        # Cache para metadatos
        self._device_types_cache: Optional[Dict[str, Any]] = None
        self._users_cache: Optional[Dict[str, DeviceUser]] = None
        self._cache_expiry: Optional[datetime] = None
        self._cache_duration = timedelta(hours=1)

    async def __aenter__(self):
        """Entrada del context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salida del context manager."""
        await self.close()

    async def close(self):
        """Cerrar el cliente HTTP."""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, MDMAPIError)),
        before_sleep=before_sleep_log(logger, "WARNING")
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Realizar una petición HTTP a la API de MDM.
        
        Args:
            method: Método HTTP (GET, POST, etc.)
            endpoint: Endpoint de la API
            params: Parámetros de consulta
            json_data: Datos JSON para el cuerpo
            
        Returns:
            Respuesta de la API
            
        Raises:
            MDMAuthenticationError: Error de autenticación
            MDMAPIError: Error de API
            MDMRateLimitError: Límite de velocidad excedido
        """
        # Aplicar rate limiting
        await self.rate_limiter.acquire()
        
        url = urljoin(self.config.base_url, endpoint)
        
        try:
            self.logger.debug(
                "Realizando petición a MDM",
                method=method,
                url=url,
                params=params
            )
            
            response = await self.client.request(
                method=method,
                url=endpoint,
                params=params,
                json=json_data
            )
            
            # Manejar códigos de estado
            if response.status_code == 401:
                raise MDMAuthenticationError("Token de API inválido o expirado")
            elif response.status_code == 429:
                raise MDMRateLimitError("Límite de velocidad excedido")
            elif response.status_code >= 400:
                error_msg = f"Error de API MDM: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f" - {error_data.get('message', 'Error desconocido')}"
                except:
                    error_msg += f" - {response.text}"
                raise MDMAPIError(error_msg)
            
            response.raise_for_status()
            
            # Parsear respuesta JSON
            try:
                data = response.json()
                self.logger.debug(
                    "Respuesta recibida de MDM",
                    status_code=response.status_code,
                    data_keys=list(data.keys()) if isinstance(data, dict) else None
                )
                return data
            except ValueError as e:
                raise MDMAPIError(f"Respuesta JSON inválida: {e}")
                
        except httpx.RequestError as e:
            self.logger.error("Error de conexión con MDM", error=str(e))
            raise MDMAPIError(f"Error de conexión: {e}")

    async def test_connection(self) -> bool:
        """Probar la conexión con MDM.
        
        Returns:
            True si la conexión es exitosa
        """
        try:
            await self._make_request("GET", "/", params={"limit": 1})
            self.logger.info("Conexión con MDM exitosa")
            return True
        except Exception as e:
            self.logger.error("Error al conectar con MDM", error=str(e))
            return False

    async def get_devices(
        self,
        limit: int = 100,
        offset: int = 0,
        modified_since: Optional[datetime] = None,
        device_type: Optional[str] = None
    ) -> List[MDMDevice]:
        """Obtener dispositivos desde MDM.
        
        Args:
            limit: Número máximo de dispositivos a obtener
            offset: Offset para paginación
            modified_since: Obtener solo dispositivos modificados desde esta fecha
            device_type: Filtrar por tipo de dispositivo
            
        Returns:
            Lista de dispositivos MDM
        """
        params = {
            "limit": limit,
            "offset": offset
        }
        
        if modified_since:
            params["modified_since"] = modified_since.isoformat()
        
        if device_type:
            params["device_type"] = device_type
        
        try:
            response = await self._make_request("GET", "/", params=params)
            
            devices = []
            for device_data in response.get("devices", []):
                try:
                    device = self._parse_device(device_data)
                    devices.append(device)
                except Exception as e:
                    self.logger.warning(
                        "Error al parsear dispositivo",
                        device_id=device_data.get("device_id"),
                        error=str(e)
                    )
            
            self.logger.info(
                "Dispositivos obtenidos de MDM",
                count=len(devices),
                total=response.get("total", len(devices))
            )
            
            return devices
            
        except Exception as e:
            self.logger.error("Error al obtener dispositivos", error=str(e))
            raise

    async def get_device_details(self, device_id: str) -> Optional[MDMDevice]:
        """Obtener detalles de un dispositivo específico.
        
        Args:
            device_id: ID del dispositivo
            
        Returns:
            Dispositivo MDM o None si no se encuentra
        """
        try:
            response = await self._make_request(
                "GET", 
                f"/{device_id}"
            )
            
            device_data = response.get("device")
            if device_data:
                return self._parse_device(device_data)
            
            return None
            
        except MDMAPIError as e:
            if "404" in str(e):
                return None
            raise

    async def get_all_devices(
        self,
        modified_since: Optional[datetime] = None,
        batch_size: int = 100
    ) -> List[MDMDevice]:
        """Obtener todos los dispositivos usando paginación.
        
        Args:
            modified_since: Obtener solo dispositivos modificados desde esta fecha
            batch_size: Tamaño del lote para paginación
            
        Returns:
            Lista completa de dispositivos
        """
        all_devices = []
        offset = 0
        
        while True:
            devices = await self.get_devices(
                limit=batch_size,
                offset=offset,
                modified_since=modified_since
            )
            
            if not devices:
                break
            
            all_devices.extend(devices)
            
            # Si obtuvimos menos dispositivos que el límite, hemos terminado
            if len(devices) < batch_size:
                break
            
            offset += batch_size
            
            # Pequeña pausa para evitar sobrecargar la API
            await asyncio.sleep(0.1)
        
        self.logger.info(
            "Todos los dispositivos obtenidos",
            total_devices=len(all_devices)
        )
        
        return all_devices

    async def get_users(self) -> Dict[str, DeviceUser]:
        """Obtener usuarios desde MDM con cache.
        
        Returns:
            Diccionario de usuarios por email
        """
        # Verificar cache
        if (self._users_cache is not None and 
            self._cache_expiry is not None and 
            datetime.now() < self._cache_expiry):
            return self._users_cache
        
        try:
            response = await self._make_request("GET", "/users")
            
            users = {}
            for user_data in response.get("users", []):
                try:
                    user = DeviceUser(
                        user_id=user_data.get("user_id"),
                        email=user_data.get("email"),
                        name=user_data.get("name"),
                        department=user_data.get("department"),
                        phone=user_data.get("phone")
                    )
                    users[user.email] = user
                except Exception as e:
                    self.logger.warning(
                        "Error al parsear usuario",
                        user_data=user_data,
                        error=str(e)
                    )
            
            # Actualizar cache
            self._users_cache = users
            self._cache_expiry = datetime.now() + self._cache_duration
            
            self.logger.info("Usuarios obtenidos de MDM", count=len(users))
            return users
            
        except Exception as e:
            self.logger.error("Error al obtener usuarios", error=str(e))
            raise

    async def get_device_apps(self, device_id: str) -> List[Dict[str, Any]]:
        """Obtener aplicaciones instaladas en un dispositivo.
        
        Args:
            device_id: ID del dispositivo
            
        Returns:
            Lista de aplicaciones
        """
        try:
            response = await self._make_request(
                "GET", 
                f"/{device_id}/apps"
            )
            
            apps = response.get("apps", [])
            self.logger.debug(
                "Aplicaciones obtenidas",
                device_id=device_id,
                app_count=len(apps)
            )
            
            return apps
            
        except Exception as e:
            self.logger.error(
                "Error al obtener aplicaciones",
                device_id=device_id,
                error=str(e)
            )
            return []

    def _parse_device(self, device_data: Dict[str, Any]) -> MDMDevice:
        """Parsear datos de dispositivo desde la API de MDM.
        
        Args:
            device_data: Datos del dispositivo desde la API
            
        Returns:
            Objeto MDMDevice
        """
        try:
            # Parsear fechas
            enrollment_date = None
            if device_data.get("enrollment_date"):
                enrollment_date = datetime.fromisoformat(
                    device_data["enrollment_date"].replace("Z", "+00:00")
                )
            
            last_seen = None
            if device_data.get("last_seen"):
                last_seen = datetime.fromisoformat(
                    device_data["last_seen"].replace("Z", "+00:00")
                )
            
            return MDMDevice(
                device_id=device_data["device_id"],
                device_name=device_data.get("device_name", ""),
                model=device_data.get("model", ""),
                manufacturer=device_data.get("manufacturer", ""),
                os_type=device_data.get("platform_type", ""),
                os_version=device_data.get("os_version", ""),
                serial_number=device_data.get("serial_number", ""),
                imei=device_data.get("imei", ""),
                user_email=device_data.get("user_email", ""),
                user_name=device_data.get("user_name", ""),
                enrollment_date=enrollment_date,
                last_seen=last_seen,
                status=device_data.get("device_status", "unknown"),
                is_supervised=device_data.get("is_supervised", False),
                is_lost_mode=device_data.get("is_lost_mode", False),
                battery_level=device_data.get("battery_level"),
                storage_total=device_data.get("total_capacity"),
                storage_available=device_data.get("available_capacity"),
                wifi_mac=device_data.get("wifi_mac", ""),
                cellular_technology=device_data.get("cellular_technology", ""),
                carrier_settings_version=device_data.get("carrier_settings_version", ""),
                phone_number=device_data.get("phone_number", ""),
                raw_data=device_data
            )
            
        except KeyError as e:
            raise ValueError(f"Campo requerido faltante en datos del dispositivo: {e}")
        except Exception as e:
            raise ValueError(f"Error al parsear dispositivo: {e}")

    async def get_device_count(
        self,
        modified_since: Optional[datetime] = None
    ) -> int:
        """Obtener el número total de dispositivos.
        
        Args:
            modified_since: Contar solo dispositivos modificados desde esta fecha
            
        Returns:
            Número total de dispositivos
        """
        params = {"limit": 1}
        
        if modified_since:
            params["modified_since"] = modified_since.isoformat()
        
        try:
            response = await self._make_request("GET", "/", params=params)
            return response.get("total", 0)
        except Exception as e:
            self.logger.error("Error al obtener conteo de dispositivos", error=str(e))
            return 0

    async def search_devices(
        self,
        query: str,
        search_field: str = "device_name"
    ) -> List[MDMDevice]:
        """Buscar dispositivos por criterio.
        
        Args:
            query: Término de búsqueda
            search_field: Campo en el que buscar
            
        Returns:
            Lista de dispositivos que coinciden
        """
        params = {
            "search": query,
            "search_field": search_field
        }
        
        try:
            response = await self._make_request(
                "GET", 
                "/search", 
                params=params
            )
            
            devices = []
            for device_data in response.get("devices", []):
                try:
                    device = self._parse_device(device_data)
                    devices.append(device)
                except Exception as e:
                    self.logger.warning(
                        "Error al parsear dispositivo en búsqueda",
                        device_id=device_data.get("device_id"),
                        error=str(e)
                    )
            
            return devices
            
        except Exception as e:
            self.logger.error("Error en búsqueda de dispositivos", error=str(e))
            return []