"""Conector para GLPI API REST."""

import asyncio
from datetime import datetime
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

from ..config.settings import GLPIConfig
from ..models.device import GLPIDevice, MDMDevice
from ..utils.rate_limiter import RateLimiter

logger = structlog.get_logger()


class GLPIConnectorError(Exception):
    """Excepción base para errores del conector GLPI."""
    pass


class GLPIAuthenticationError(GLPIConnectorError):
    """Error de autenticación con GLPI."""
    pass


class GLPIAPIError(GLPIConnectorError):
    """Error de API de GLPI."""
    pass


class GLPINotFoundError(GLPIConnectorError):
    """Recurso no encontrado en GLPI."""
    pass


class GLPIConnector:
    """Conector para GLPI API REST."""

    def __init__(self, config: GLPIConfig):
        """Inicializar el conector GLPI.
        
        Args:
            config: Configuración de GLPI
        """
        self.config = config
        self.logger = logger.bind(component="glpi_connector")
        self.rate_limiter = RateLimiter(60, 60)  # 60 requests per minute
        
        # Session token
        self._session_token: Optional[str] = None
        
        # Cliente HTTP
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            verify=config.verify_ssl,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        # Cache para metadatos
        self._manufacturers_cache: Optional[Dict[str, int]] = None
        self._models_cache: Optional[Dict[str, int]] = None
        self._os_cache: Optional[Dict[str, int]] = None
        self._types_cache: Optional[Dict[str, int]] = None
        self._states_cache: Optional[Dict[str, int]] = None
        self._users_cache: Optional[Dict[str, int]] = None

    async def __aenter__(self):
        """Entrada del context manager."""
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Salida del context manager."""
        await self.close()

    async def close(self):
        """Cerrar la sesión y el cliente HTTP."""
        if self._session_token:
            try:
                await self._make_request("GET", "/killSession")
            except Exception as e:
                self.logger.warning("Error al cerrar sesión GLPI", error=str(e))
        
        await self.client.aclose()

    async def authenticate(self) -> bool:
        """Autenticar con GLPI y obtener session token.
        
        Returns:
            True si la autenticación es exitosa
            
        Raises:
            GLPIAuthenticationError: Error de autenticación
        """
        try:
            headers = {
                "App-Token": self.config.app_token,
                "Authorization": f"user_token {self.config.user_token}"
            }
            
            response = await self.client.post(
                "/initSession",
                headers=headers
            )
            
            if response.status_code == 401:
                raise GLPIAuthenticationError("Credenciales GLPI inválidas")
            elif response.status_code != 200:
                raise GLPIAuthenticationError(f"Error de autenticación: {response.status_code}")
            
            data = response.json()
            self._session_token = data.get("session_token")
            
            if not self._session_token:
                raise GLPIAuthenticationError("No se recibió session token")
            
            # Actualizar headers del cliente
            self.client.headers["Session-Token"] = self._session_token
            self.client.headers["App-Token"] = self.config.app_token
            
            self.logger.info("Autenticación GLPI exitosa")
            return True
            
        except httpx.RequestError as e:
            raise GLPIAuthenticationError(f"Error de conexión: {e}")
        except Exception as e:
            if isinstance(e, GLPIAuthenticationError):
                raise
            raise GLPIAuthenticationError(f"Error inesperado: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, GLPIAPIError)),
        before_sleep=before_sleep_log(logger, "WARNING")
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Realizar una petición HTTP a la API de GLPI.
        
        Args:
            method: Método HTTP
            endpoint: Endpoint de la API
            params: Parámetros de consulta
            json_data: Datos JSON
            
        Returns:
            Respuesta de la API
            
        Raises:
            GLPIAuthenticationError: Error de autenticación
            GLPIAPIError: Error de API
            GLPINotFoundError: Recurso no encontrado
        """
        # Aplicar rate limiting
        await self.rate_limiter.acquire()
        
        # Verificar autenticación
        if not self._session_token and endpoint != "/initSession":
            await self.authenticate()
        
        try:
            self.logger.debug(
                "Realizando petición a GLPI",
                method=method,
                endpoint=endpoint,
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
                # Token expirado, intentar re-autenticar
                self._session_token = None
                await self.authenticate()
                # Reintentar la petición original
                return await self._make_request(method, endpoint, params, json_data)
            elif response.status_code == 404:
                raise GLPINotFoundError("Recurso no encontrado")
            elif response.status_code >= 400:
                error_msg = f"Error de API GLPI: {response.status_code}"
                try:
                    error_data = response.json()
                    if isinstance(error_data, list) and error_data:
                        error_msg += f" - {error_data[0]}"
                    elif isinstance(error_data, dict):
                        error_msg += f" - {error_data.get('message', 'Error desconocido')}"
                except:
                    error_msg += f" - {response.text}"
                raise GLPIAPIError(error_msg)
            
            response.raise_for_status()
            
            # Parsear respuesta
            try:
                if response.content:
                    data = response.json()
                else:
                    data = {}
                
                self.logger.debug(
                    "Respuesta recibida de GLPI",
                    status_code=response.status_code,
                    data_type=type(data).__name__
                )
                
                return data
                
            except ValueError as e:
                raise GLPIAPIError(f"Respuesta JSON inválida: {e}")
                
        except httpx.RequestError as e:
            self.logger.error("Error de conexión con GLPI", error=str(e))
            raise GLPIAPIError(f"Error de conexión: {e}")

    async def test_connection(self) -> bool:
        """Probar la conexión con GLPI.
        
        Returns:
            True si la conexión es exitosa
        """
        try:
            await self.authenticate()
            # Probar obtener información básica
            await self._make_request("GET", "/getMyProfiles")
            self.logger.info("Conexión con GLPI exitosa")
            return True
        except Exception as e:
            self.logger.error("Error al conectar con GLPI", error=str(e))
            return False

    async def search_computers(
        self,
        criteria: Dict[str, Any],
        range_start: int = 0,
        range_end: int = 50
    ) -> List[Dict[str, Any]]:
        """Buscar computadoras en GLPI.
        
        Args:
            criteria: Criterios de búsqueda
            range_start: Inicio del rango
            range_end: Fin del rango
            
        Returns:
            Lista de computadoras encontradas
        """
        params = {
            "criteria": criteria,
            "range": f"{range_start}-{range_end}"
        }
        
        try:
            response = await self._make_request(
                "GET", 
                "/search/Computer", 
                params=params
            )
            
            return response.get("data", [])
            
        except GLPINotFoundError:
            return []
        except Exception as e:
            self.logger.error("Error en búsqueda de computadoras", error=str(e))
            raise

    async def get_computer_by_serial(self, serial: str) -> Optional[Dict[str, Any]]:
        """Buscar computadora por número de serie.
        
        Args:
            serial: Número de serie
            
        Returns:
            Datos de la computadora o None si no se encuentra
        """
        criteria = [
            {
                "field": "5",  # Campo serial
                "searchtype": "equals",
                "value": serial
            }
        ]
        
        computers = await self.search_computers({"criteria": criteria})
        
        if computers:
            # Obtener detalles completos del primer resultado
            computer_id = computers[0].get("2")  # ID
            if computer_id:
                return await self.get_computer(int(computer_id))
        
        return None

    async def get_computer_by_mdm_id(self, mdm_device_id: str) -> Optional[Dict[str, Any]]:
        """Buscar computadora por ID de dispositivo MDM.
        
        Args:
            mdm_device_id: ID del dispositivo en MDM
            
        Returns:
            Datos de la computadora o None si no se encuentra
        """
        # Buscar en el campo de comentarios
        criteria = [
            {
                "field": "16",  # Campo comment
                "searchtype": "contains",
                "value": f"ID MDM: {mdm_device_id}"
            }
        ]
        
        computers = await self.search_computers({"criteria": criteria})
        
        if computers:
            computer_id = computers[0].get("2")  # ID
            if computer_id:
                return await self.get_computer(int(computer_id))
        
        return None

    async def get_computer(self, computer_id: int) -> Optional[Dict[str, Any]]:
        """Obtener detalles de una computadora.
        
        Args:
            computer_id: ID de la computadora
            
        Returns:
            Datos de la computadora
        """
        try:
            response = await self._make_request(
                "GET", 
                f"/Computer/{computer_id}"
            )
            return response
        except GLPINotFoundError:
            return None

    async def create_computer(self, computer_data: Dict[str, Any]) -> Optional[int]:
        """Crear una nueva computadora en GLPI.
        
        Args:
            computer_data: Datos de la computadora
            
        Returns:
            ID de la computadora creada o None si falla
        """
        try:
            response = await self._make_request(
                "POST",
                "/Computer",
                json_data={"input": computer_data}
            )
            
            if isinstance(response, dict) and "id" in response:
                computer_id = response["id"]
                self.logger.info(
                    "Computadora creada en GLPI",
                    computer_id=computer_id,
                    name=computer_data.get("name")
                )
                return computer_id
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Error al crear computadora",
                computer_data=computer_data,
                error=str(e)
            )
            raise

    async def update_computer(
        self, 
        computer_id: int, 
        computer_data: Dict[str, Any]
    ) -> bool:
        """Actualizar una computadora existente.
        
        Args:
            computer_id: ID de la computadora
            computer_data: Datos actualizados
            
        Returns:
            True si la actualización es exitosa
        """
        try:
            # Agregar ID a los datos
            update_data = {"id": computer_id, **computer_data}
            
            response = await self._make_request(
                "PUT",
                f"/Computer/{computer_id}",
                json_data={"input": update_data}
            )
            
            self.logger.info(
                "Computadora actualizada en GLPI",
                computer_id=computer_id,
                name=computer_data.get("name")
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Error al actualizar computadora",
                computer_id=computer_id,
                error=str(e)
            )
            raise

    async def delete_computer(self, computer_id: int) -> bool:
        """Marcar una computadora como eliminada.
        
        Args:
            computer_id: ID de la computadora
            
        Returns:
            True si la eliminación es exitosa
        """
        try:
            await self._make_request(
                "PUT",
                f"/Computer/{computer_id}",
                json_data={
                    "input": {
                        "id": computer_id,
                        "is_deleted": True
                    }
                }
            )
            
            self.logger.info("Computadora marcada como eliminada", computer_id=computer_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "Error al eliminar computadora",
                computer_id=computer_id,
                error=str(e)
            )
            return False

    async def sync_device_from_mdm(self, mdm_device: MDMDevice) -> Optional[int]:
        """Sincronizar un dispositivo MDM con GLPI.
        
        Args:
            mdm_device: Dispositivo desde MDM
            
        Returns:
            ID de la computadora en GLPI
        """
        try:
            # Buscar si ya existe
            existing = await self.get_computer_by_mdm_id(mdm_device.device_id)
            
            if not existing:
                # Buscar por serial como fallback
                if mdm_device.serial_number:
                    existing = await self.get_computer_by_serial(mdm_device.serial_number)
            
            # Convertir a formato GLPI
            glpi_device = GLPIDevice.from_mdm_device(mdm_device)
            
            # Resolver IDs de metadatos
            await self._resolve_metadata_ids(glpi_device, mdm_device)
            
            # Preparar datos para GLPI
            computer_data = glpi_device.to_glpi_format()
            
            if existing:
                # Actualizar existente
                computer_id = existing.get("id")
                if computer_id:
                    await self.update_computer(computer_id, computer_data)
                    return computer_id
            else:
                # Crear nuevo
                return await self.create_computer(computer_data)
            
            return None
            
        except Exception as e:
            self.logger.error(
                "Error al sincronizar dispositivo",
                device_id=mdm_device.device_id,
                error=str(e)
            )
            raise

    async def _resolve_metadata_ids(
        self, 
        glpi_device: GLPIDevice, 
        mdm_device: MDMDevice
    ) -> None:
        """Resolver IDs de metadatos (fabricantes, modelos, etc.).
        
        Args:
            glpi_device: Dispositivo GLPI a actualizar
            mdm_device: Dispositivo MDM fuente
        """
        # Resolver fabricante
        if mdm_device.manufacturer:
            manufacturer_id = await self._get_or_create_manufacturer(mdm_device.manufacturer)
            glpi_device.manufacturers_id = manufacturer_id
        
        # Resolver modelo
        if mdm_device.model:
            model_id = await self._get_or_create_model(mdm_device.model)
            glpi_device.computermodels_id = model_id
        
        # Resolver tipo de computadora
        device_type = "Mobile Device" if mdm_device.is_mobile else "Computer"
        type_id = await self._get_or_create_computer_type(device_type)
        glpi_device.computertypes_id = type_id
        
        # Resolver sistema operativo
        if mdm_device.os_type:
            os_id = await self._get_or_create_operating_system(mdm_device.os_type)
            glpi_device.operatingsystems_id = os_id
        
        # Resolver estado
        state_name = "Active" if mdm_device.is_active else "Inactive"
        state_id = await self._get_or_create_state(state_name)
        glpi_device.states_id = state_id
        
        # Resolver usuario
        if mdm_device.user_email:
            user_id = await self._get_user_by_email(mdm_device.user_email)
            glpi_device.users_id = user_id

    async def _get_or_create_manufacturer(self, name: str) -> Optional[int]:
        """Obtener o crear fabricante."""
        # Implementación simplificada - en producción usar cache
        try:
            # Buscar existente
            criteria = [
                {
                    "field": "1",  # name
                    "searchtype": "equals",
                    "value": name
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/Manufacturer",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            # Crear nuevo
            response = await self._make_request(
                "POST",
                "/Manufacturer",
                json_data={"input": {"name": name}}
            )
            
            return response.get("id")
            
        except Exception as e:
            self.logger.warning("Error al resolver fabricante", name=name, error=str(e))
            return None

    async def _get_or_create_model(self, name: str) -> Optional[int]:
        """Obtener o crear modelo de computadora."""
        try:
            criteria = [
                {
                    "field": "1",  # name
                    "searchtype": "equals",
                    "value": name
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/ComputerModel",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            # Crear nuevo
            response = await self._make_request(
                "POST",
                "/ComputerModel",
                json_data={"input": {"name": name}}
            )
            
            return response.get("id")
            
        except Exception as e:
            self.logger.warning("Error al resolver modelo", name=name, error=str(e))
            return None

    async def _get_or_create_computer_type(self, name: str) -> Optional[int]:
        """Obtener o crear tipo de computadora."""
        try:
            criteria = [
                {
                    "field": "1",  # name
                    "searchtype": "equals",
                    "value": name
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/ComputerType",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            # Crear nuevo
            response = await self._make_request(
                "POST",
                "/ComputerType",
                json_data={"input": {"name": name}}
            )
            
            return response.get("id")
            
        except Exception as e:
            self.logger.warning("Error al resolver tipo", name=name, error=str(e))
            return None

    async def _get_or_create_operating_system(self, name: str) -> Optional[int]:
        """Obtener o crear sistema operativo."""
        try:
            criteria = [
                {
                    "field": "1",  # name
                    "searchtype": "equals",
                    "value": name.title()
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/OperatingSystem",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            # Crear nuevo
            response = await self._make_request(
                "POST",
                "/OperatingSystem",
                json_data={"input": {"name": name.title()}}
            )
            
            return response.get("id")
            
        except Exception as e:
            self.logger.warning("Error al resolver OS", name=name, error=str(e))
            return None

    async def _get_or_create_state(self, name: str) -> Optional[int]:
        """Obtener o crear estado."""
        try:
            criteria = [
                {
                    "field": "1",  # name
                    "searchtype": "equals",
                    "value": name
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/State",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            # Crear nuevo
            response = await self._make_request(
                "POST",
                "/State",
                json_data={"input": {"name": name}}
            )
            
            return response.get("id")
            
        except Exception as e:
            self.logger.warning("Error al resolver estado", name=name, error=str(e))
            return None

    async def _get_user_by_email(self, email: str) -> Optional[int]:
        """Buscar usuario por email."""
        try:
            criteria = [
                {
                    "field": "5",  # email
                    "searchtype": "equals",
                    "value": email
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/User",
                params={"criteria": criteria}
            )
            
            data = response.get("data", [])
            if data:
                return int(data[0].get("2"))  # ID
            
            return None
            
        except Exception as e:
            self.logger.warning("Error al buscar usuario", email=email, error=str(e))
            return None

    async def get_sync_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de sincronización.
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            # Buscar dispositivos sincronizados desde MDM
            criteria = [
                {
                    "field": "16",  # comment
                    "searchtype": "contains",
                    "value": "Dispositivo sincronizado desde MDM"
                }
            ]
            
            response = await self._make_request(
                "GET",
                "/search/Computer",
                params={"criteria": criteria, "range": "0-1"}
            )
            
            total_synced = response.get("totalcount", 0)
            
            return {
                "total_synced_devices": total_synced,
                "last_check": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error("Error al obtener estadísticas", error=str(e))
            return {
                "total_synced_devices": 0,
                "last_check": datetime.now().isoformat(),
                "error": str(e)
            }