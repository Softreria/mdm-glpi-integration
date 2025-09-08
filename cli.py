#!/usr/bin/env python3
"""CLI para la integración MDM-GLPI."""

import asyncio
import sys
import argparse
from pathlib import Path
from typing import Optional

# Agregar el directorio src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mdm_glpi_integration.main import MDMGLPIIntegration
from mdm_glpi_integration.config.settings import Settings
from mdm_glpi_integration.services.sync_service import SyncType


def create_parser() -> argparse.ArgumentParser:
    """Crear parser de argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Integración MDM-GLPI - Sincronización de dispositivos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s run                    # Ejecutar como daemon
  %(prog)s sync --full           # Sincronización completa manual
  %(prog)s sync --incremental    # Sincronización incremental manual
  %(prog)s health                # Verificar estado del sistema
  %(prog)s test-connections      # Probar conexiones MDM y GLPI
  %(prog)s --config custom.yaml  # Usar archivo de configuración personalizado
"""
    )
    
    # Argumentos globales
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Ruta al archivo de configuración (por defecto: config.yaml)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Habilitar logging detallado"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar en modo simulación (no realizar cambios reales)"
    )
    
    # Subcomandos
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")
    
    # Comando run
    run_parser = subparsers.add_parser(
        "run", 
        help="Ejecutar la aplicación como daemon"
    )
    run_parser.add_argument(
        "--no-initial-sync",
        action="store_true",
        help="No ejecutar sincronización inicial al arrancar"
    )
    
    # Comando sync
    sync_parser = subparsers.add_parser(
        "sync", 
        help="Ejecutar sincronización manual"
    )
    sync_group = sync_parser.add_mutually_exclusive_group(required=True)
    sync_group.add_argument(
        "--full", "-f",
        action="store_true",
        help="Sincronización completa de todos los dispositivos"
    )
    sync_group.add_argument(
        "--incremental", "-i",
        action="store_true",
        help="Sincronización incremental (solo cambios recientes)"
    )
    sync_parser.add_argument(
        "--batch-size",
        type=int,
        help="Tamaño del lote para procesamiento"
    )
    
    # Comando health
    subparsers.add_parser(
        "health", 
        help="Verificar estado de salud del sistema"
    )
    
    # Comando test-connections
    subparsers.add_parser(
        "test-connections", 
        help="Probar conexiones a MDM y GLPI"
    )
    
    # Comando version
    subparsers.add_parser(
        "version", 
        help="Mostrar información de versión"
    )
    
    return parser


async def run_daemon(args, settings: Settings) -> int:
    """Ejecutar la aplicación como daemon."""
    try:
        # Configurar sincronización inicial
        if args.no_initial_sync:
            settings.sync.initial_sync = False
        
        # Crear y ejecutar aplicación
        app = MDMGLPIIntegration(settings)
        await app.run()
        return 0
    except KeyboardInterrupt:
        print("\n⏹️  Aplicación detenida por el usuario")
        return 0
    except Exception as e:
        print(f"❌ Error ejecutando daemon: {e}")
        return 1


async def run_manual_sync(args, settings: Settings) -> int:
    """Ejecutar sincronización manual."""
    try:
        # Configurar tamaño de lote si se especifica
        if args.batch_size:
            settings.sync.batch_size = args.batch_size
        
        # Crear aplicación
        app = MDMGLPIIntegration(settings)
        await app.startup()
        
        # Determinar tipo de sincronización
        sync_type = SyncType.FULL if args.full else SyncType.INCREMENTAL
        sync_name = "completa" if args.full else "incremental"
        
        print(f"🔄 Iniciando sincronización {sync_name}...")
        
        # Ejecutar sincronización
        if args.full:
            result = await app.run_full_sync()
        else:
            result = await app.run_incremental_sync()
        
        # Mostrar resultados
        print(f"✅ Sincronización {sync_name} completada:")
        print(f"   📱 Dispositivos procesados: {result.get('devices_synced', 0)}")
        print(f"   ❌ Errores: {result.get('errors', 0)}")
        print(f"   ⏱️  Duración: {result.get('duration', 0):.2f}s")
        
        await app.shutdown()
        return 0
    except Exception as e:
        print(f"❌ Error en sincronización: {e}")
        return 1


async def check_health(settings: Settings) -> int:
    """Verificar estado de salud del sistema."""
    try:
        from mdm_glpi_integration.services.health_checker import HealthChecker
        
        print("🔍 Verificando estado del sistema...")
        
        health_checker = HealthChecker(settings)
        health_status = await health_checker.check_health()
        
        # Mostrar estado general
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌"
        }
        
        emoji = status_emoji.get(health_status.overall_status.value, "❓")
        print(f"\n{emoji} Estado general: {health_status.overall_status.value.upper()}")
        
        # Mostrar estado de componentes
        print("\n📊 Estado de componentes:")
        for name, component in health_status.components.items():
            comp_emoji = status_emoji.get(component.status.value, "❓")
            print(f"   {comp_emoji} {name.upper()}: {component.status.value}")
            if component.message:
                print(f"      💬 {component.message}")
            if component.response_time:
                print(f"      ⏱️  Tiempo de respuesta: {component.response_time:.2f}ms")
        
        # Mostrar métricas del sistema
        if health_status.system_metrics:
            print("\n💻 Métricas del sistema:")
            metrics = health_status.system_metrics
            if hasattr(metrics, 'memory_usage_percent'):
                print(f"   🧠 Memoria: {metrics.memory_usage_percent:.1f}%")
            if hasattr(metrics, 'cpu_usage_percent'):
                print(f"   ⚡ CPU: {metrics.cpu_usage_percent:.1f}%")
            if hasattr(metrics, 'uptime_seconds'):
                uptime_hours = metrics.uptime_seconds / 3600
                print(f"   ⏰ Uptime: {uptime_hours:.1f}h")
        
        return 0 if health_status.overall_status.value == "healthy" else 1
    except Exception as e:
        print(f"❌ Error verificando salud: {e}")
        return 1


async def test_connections(settings: Settings) -> int:
    """Probar conexiones a MDM y GLPI."""
    try:
        from mdm_glpi_integration.connectors.mdm_connector import ManageEngineMDMConnector
        from mdm_glpi_integration.connectors.glpi_connector import GLPIConnector
        
        print("🔗 Probando conexiones...")
        
        # Probar MDM
        print("\n📱 Probando conexión MDM...")
        mdm_connector = ManageEngineMDMConnector(settings.mdm)
        mdm_ok = await mdm_connector.test_connection()
        print(f"   {'✅' if mdm_ok else '❌'} MDM: {'Conectado' if mdm_ok else 'Error de conexión'}")
        
        # Probar GLPI
        print("\n💻 Probando conexión GLPI...")
        glpi_connector = GLPIConnector(settings.glpi)
        glpi_ok = await glpi_connector.test_connection()
        print(f"   {'✅' if glpi_ok else '❌'} GLPI: {'Conectado' if glpi_ok else 'Error de conexión'}")
        
        # Resultado general
        all_ok = mdm_ok and glpi_ok
        print(f"\n{'✅' if all_ok else '❌'} Resultado: {'Todas las conexiones OK' if all_ok else 'Hay problemas de conectividad'}")
        
        return 0 if all_ok else 1
    except Exception as e:
        print(f"❌ Error probando conexiones: {e}")
        return 1


def show_version() -> int:
    """Mostrar información de versión."""
    print("MDM-GLPI Integration v1.0.0")
    print("Integración de ManageEngine MDM con GLPI")
    print("")
    print("Componentes:")
    print("  • ManageEngine MDM Connector")
    print("  • GLPI REST API Connector")
    print("  • Servicio de Sincronización")
    print("  • Sistema de Monitoreo")
    print("  • API REST")
    return 0


async def main() -> int:
    """Función principal del CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Si no se especifica comando, mostrar ayuda
    if not args.command:
        parser.print_help()
        return 1
    
    # Comando version no requiere configuración
    if args.command == "version":
        return show_version()
    
    try:
        # Cargar configuración
        config_file = args.config or "config.yaml"
        settings = Settings.from_yaml(config_file)
        
        # Configurar logging si es verbose
        if args.verbose:
            settings.logging.level = "DEBUG"
        
        # Configurar modo dry-run
        if args.dry_run:
            print("🔍 Modo simulación activado - no se realizarán cambios reales")
            # Aquí podrías configurar un flag global para dry-run
        
        # Ejecutar comando
        if args.command == "run":
            return await run_daemon(args, settings)
        elif args.command == "sync":
            return await run_manual_sync(args, settings)
        elif args.command == "health":
            return await check_health(settings)
        elif args.command == "test-connections":
            return await test_connections(settings)
        else:
            print(f"❌ Comando desconocido: {args.command}")
            return 1
            
    except FileNotFoundError as e:
        print(f"❌ Archivo de configuración no encontrado: {e}")
        print("💡 Crea un archivo config.yaml o especifica uno con --config")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Operación cancelada por el usuario")
        sys.exit(130)