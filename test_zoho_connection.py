#!/usr/bin/env python3
"""Script de prueba rápida para verificar la conexión con Zoho MDM."""

import asyncio
import os
import sys
from pathlib import Path

# Agregar el directorio src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mdm_glpi_integration.config.settings import Settings
from mdm_glpi_integration.connectors.mdm_connector import ManageEngineMDMConnector


async def test_zoho_connection():
    """Probar la conexión con Zoho MDM usando el token configurado."""
    print("🔍 Probando conexión con Zoho MDM...")
    
    try:
        # Cargar configuración
        settings = Settings()
        print(f"📋 URL Base: {settings.mdm.base_url}")
        print(f"🔑 Token configurado: {settings.mdm.api_key[:20]}...")
        
        # Crear conector
        connector = ManageEngineMDMConnector(settings.mdm)
        
        # Probar conexión
        print("\n🔗 Probando conectividad...")
        is_connected = await connector.test_connection()
        
        if is_connected:
            print("✅ ¡Conexión exitosa con Zoho MDM!")
            
            # Intentar obtener información básica
            try:
                print("\n📱 Obteniendo información de dispositivos...")
                # Hacer una consulta básica para verificar que el token funciona
                response = await connector._make_request("GET", "/", params={"limit": 1})
                print(f"✅ Respuesta recibida: {len(response.get('devices', []))} dispositivos encontrados")
                
            except Exception as e:
                print(f"⚠️  Conexión OK pero error al obtener datos: {e}")
                
        else:
            print("❌ Error de conexión con Zoho MDM")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    finally:
        # Cerrar conexión
        if 'connector' in locals():
            await connector.close()
    
    return True


if __name__ == "__main__":
    print("🚀 Test de Conexión Zoho MDM")
    print("=" * 40)
    
    # Verificar que existe el archivo .env
    env_file = Path(".env")
    if not env_file.exists():
        print("⚠️  Archivo .env no encontrado. Creando uno de ejemplo...")
        print("Por favor, configura tu token de Zoho en el archivo .env")
        sys.exit(1)
    
    # Ejecutar prueba
    success = asyncio.run(test_zoho_connection())
    
    if success:
        print("\n🎉 ¡Configuración de Zoho completada correctamente!")
        print("Ya puedes usar la aplicación MDM-GLPI con tu token de Zoho.")
    else:
        print("\n❌ Hay problemas con la configuración.")
        print("Verifica tu token de Zoho y la conectividad de red.")
        sys.exit(1)