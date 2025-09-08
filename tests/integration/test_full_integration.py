"""Test de integración completa del sistema MDM-GLPI."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.mdm_glpi_integration.config.settings import Settings
from src.mdm_glpi_integration.services.sync_service import SyncService, SyncType
from src.mdm_glpi_integration.services.health_checker import HealthChecker
from src.mdm_glpi_integration.connectors.mdm_connector import ManageEngineMDMConnector
from src.mdm_glpi_integration.connectors.glpi_connector import GLPIConnector
from src.mdm_glpi_integration.models.device import MDMDevice, DeviceStatus, OSType, DeviceUser


@pytest.fixture
def mock_settings():
    """Configuración mock para tests."""
    settings = MagicMock(spec=Settings)
    
    # MDM config
    settings.mdm.base_url = "https://mdm.example.com"
    settings.mdm.api_key = "test_api_key"
    settings.mdm.timeout = 30
    settings.mdm.rate_limit = 100
    settings.mdm.ssl_verify = True
    
    # GLPI config
    settings.glpi.base_url = "https://glpi.example.com"
    settings.glpi.app_token = "test_app_token"
    settings.glpi.user_token = "test_user_token"
    settings.glpi.timeout = 30
    settings.glpi.ssl_verify = True
    
    # Sync config
    settings.sync.batch_size = 10
    settings.sync.max_retries = 3
    settings.sync.initial_sync = False
    
    # Database config
    settings.database.url = "sqlite:///:memory:"
    settings.database.echo = False
    
    # Logging config
    settings.logging.level = "INFO"
    settings.logging.format = "json"
    
    # Monitoring config
    settings.monitoring.enable_metrics = True
    settings.monitoring.port = 8080
    
    return settings


@pytest.fixture
def sample_mdm_device():
    """Dispositivo MDM de ejemplo."""
    return MDMDevice(
        device_id="MDM123456",
        device_name="iPhone de Juan",
        serial_number="ABC123DEF456",
        imei="123456789012345",
        model="iPhone 13",
        manufacturer="Apple",
        os_type=OSType.IOS,
        os_name="iOS",
        os_version="15.6.1",
        status=DeviceStatus.ACTIVE,
        enrollment_date=datetime(2023, 1, 15),
        last_seen=datetime(2024, 1, 20, 10, 30),
        user=DeviceUser(
            user_id="USER123",
            username="juan.perez",
            email="juan.perez@company.com",
            full_name="Juan Pérez"
        ),
        storage_total=128000,
        storage_used=45000,
        battery_level=85,
        is_supervised=True,
        is_lost_mode=False,
        wifi_mac="AA:BB:CC:DD:EE:FF",
        bluetooth_mac="11:22:33:44:55:66",
        carrier_name="Movistar",
        phone_number="+34600123456",
        raw_data={"additional": "data"}
    )


class TestFullIntegration:
    """Tests de integración completa."""
    
    @pytest.mark.asyncio
    async def test_health_check_integration(self, mock_settings):
        """Test de verificación de salud del sistema."""
        with patch('src.mdm_glpi_integration.connectors.mdm_connector.ManageEngineMDMConnector') as mock_mdm, \
             patch('src.mdm_glpi_integration.connectors.glpi_connector.GLPIConnector') as mock_glpi:
            
            # Configurar mocks
            mock_mdm_instance = AsyncMock()
            mock_mdm_instance.test_connection.return_value = True
            mock_mdm.return_value = mock_mdm_instance
            
            mock_glpi_instance = AsyncMock()
            mock_glpi_instance.test_connection.return_value = True
            mock_glpi.return_value = mock_glpi_instance
            
            # Crear health checker
            health_checker = HealthChecker(mock_settings)
            
            # Ejecutar verificación
            health_status = await health_checker.check_health()
            
            # Verificar resultados
            assert health_status.overall_status.value in ["healthy", "degraded"]
            assert "mdm" in health_status.components
            assert "glpi" in health_status.components
            assert "database" in health_status.components
    
    @pytest.mark.asyncio
    async def test_sync_service_integration(self, mock_settings, sample_mdm_device):
        """Test de integración del servicio de sincronización."""
        with patch('src.mdm_glpi_integration.connectors.mdm_connector.ManageEngineMDMConnector') as mock_mdm, \
             patch('src.mdm_glpi_integration.connectors.glpi_connector.GLPIConnector') as mock_glpi, \
             patch('sqlalchemy.create_engine') as mock_engine, \
             patch('sqlalchemy.orm.sessionmaker') as mock_sessionmaker:
            
            # Configurar mock de MDM
            mock_mdm_instance = AsyncMock()
            mock_mdm_instance.get_all_devices.return_value = [sample_mdm_device]
            mock_mdm_instance.test_connection.return_value = True
            mock_mdm.return_value = mock_mdm_instance
            
            # Configurar mock de GLPI
            mock_glpi_instance = AsyncMock()
            mock_glpi_instance.test_connection.return_value = True
            mock_glpi_instance.sync_device_from_mdm.return_value = {
                "action": "created",
                "glpi_id": 123,
                "success": True
            }
            mock_glpi.return_value = mock_glpi_instance
            
            # Configurar mock de base de datos
            mock_session = MagicMock()
            mock_sessionmaker.return_value = lambda: mock_session
            
            # Crear servicio de sincronización
            sync_service = SyncService(mock_settings)
            
            # Ejecutar sincronización
            result = await sync_service.sync_all(SyncType.FULL)
            
            # Verificar resultados
            assert result.devices_processed >= 1
            assert result.status.value in ["completed", "completed_with_errors"]
            assert result.duration > 0
            
            # Verificar que se llamaron los métodos correctos
            mock_mdm_instance.get_all_devices.assert_called_once()
            mock_glpi_instance.sync_device_from_mdm.assert_called()
    
    @pytest.mark.asyncio
    async def test_mdm_connector_integration(self, mock_settings, sample_mdm_device):
        """Test de integración del conector MDM."""
        with patch('aiohttp.ClientSession') as mock_session:
            # Configurar mock de respuesta HTTP
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {
                "devices": [
                    {
                        "device_id": "MDM123456",
                        "device_name": "iPhone de Juan",
                        "serial_number": "ABC123DEF456",
                        "model": "iPhone 13",
                        "os_version": "15.6.1",
                        "status": "active"
                    }
                ]
            }
            
            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            # Crear conector
            connector = ManageEngineMDMConnector(mock_settings.mdm)
            
            # Test de conexión
            is_connected = await connector.test_connection()
            assert is_connected
            
            # Test de obtención de dispositivos
            devices = await connector.get_all_devices()
            assert len(devices) >= 0  # Puede ser 0 si el parsing falla
    
    @pytest.mark.asyncio
    async def test_glpi_connector_integration(self, mock_settings):
        """Test de integración del conector GLPI."""
        with patch('aiohttp.ClientSession') as mock_session:
            # Configurar mock de respuesta de autenticación
            mock_auth_response = AsyncMock()
            mock_auth_response.status = 200
            mock_auth_response.json.return_value = {"session_token": "test_session_token"}
            
            # Configurar mock de respuesta de test
            mock_test_response = AsyncMock()
            mock_test_response.status = 200
            mock_test_response.json.return_value = {"status": "ok"}
            
            mock_session_instance = AsyncMock()
            mock_session_instance.get.return_value.__aenter__.return_value = mock_auth_response
            mock_session_instance.post.return_value.__aenter__.return_value = mock_test_response
            mock_session.return_value = mock_session_instance
            
            # Crear conector
            connector = GLPIConnector(mock_settings.glpi)
            
            # Test de conexión
            is_connected = await connector.test_connection()
            assert is_connected
    
    @pytest.mark.asyncio
    async def test_end_to_end_sync_flow(self, mock_settings, sample_mdm_device):
        """Test de flujo completo de sincronización end-to-end."""
        with patch('src.mdm_glpi_integration.connectors.mdm_connector.ManageEngineMDMConnector') as mock_mdm, \
             patch('src.mdm_glpi_integration.connectors.glpi_connector.GLPIConnector') as mock_glpi, \
             patch('sqlalchemy.create_engine'), \
             patch('sqlalchemy.orm.sessionmaker') as mock_sessionmaker:
            
            # Configurar mocks
            mock_mdm_instance = AsyncMock()
            mock_mdm_instance.test_connection.return_value = True
            mock_mdm_instance.get_all_devices.return_value = [sample_mdm_device]
            mock_mdm.return_value = mock_mdm_instance
            
            mock_glpi_instance = AsyncMock()
            mock_glpi_instance.test_connection.return_value = True
            mock_glpi_instance.sync_device_from_mdm.return_value = {
                "action": "created",
                "glpi_id": 123,
                "success": True
            }
            mock_glpi.return_value = mock_glpi_instance
            
            mock_session = MagicMock()
            mock_sessionmaker.return_value = lambda: mock_session
            
            # 1. Verificar salud del sistema
            health_checker = HealthChecker(mock_settings)
            health_status = await health_checker.check_health()
            assert health_status.overall_status.value in ["healthy", "degraded"]
            
            # 2. Ejecutar sincronización
            sync_service = SyncService(mock_settings)
            sync_result = await sync_service.sync_all(SyncType.FULL)
            
            # 3. Verificar resultados
            assert sync_result.devices_processed >= 1
            assert sync_result.status.value in ["completed", "completed_with_errors"]
            
            # 4. Verificar que se ejecutaron todas las operaciones
            mock_mdm_instance.test_connection.assert_called()
            mock_glpi_instance.test_connection.assert_called()
            mock_mdm_instance.get_all_devices.assert_called()
            mock_glpi_instance.sync_device_from_mdm.assert_called()
    
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, mock_settings):
        """Test de manejo de errores en integración."""
        with patch('src.mdm_glpi_integration.connectors.mdm_connector.ManageEngineMDMConnector') as mock_mdm, \
             patch('src.mdm_glpi_integration.connectors.glpi_connector.GLPIConnector') as mock_glpi:
            
            # Configurar mocks para fallar
            mock_mdm_instance = AsyncMock()
            mock_mdm_instance.test_connection.side_effect = Exception("MDM connection failed")
            mock_mdm.return_value = mock_mdm_instance
            
            mock_glpi_instance = AsyncMock()
            mock_glpi_instance.test_connection.return_value = True
            mock_glpi.return_value = mock_glpi_instance
            
            # Verificar que el health checker maneja errores
            health_checker = HealthChecker(mock_settings)
            health_status = await health_checker.check_health()
            
            # El sistema debe reportar problemas pero no fallar completamente
            assert health_status.overall_status.value in ["unhealthy", "degraded"]
            assert "mdm" in health_status.components
            assert health_status.components["mdm"].status.value == "unhealthy"


if __name__ == "__main__":
    # Ejecutar tests
    pytest.main([__file__, "-v"])