"""Interfaz de línea de comandos para MDM-GLPI Integration."""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .main import MDMGLPIIntegration
from .config.settings import Settings
from .utils.health_checker import HealthChecker

console = Console()


@click.group()
@click.version_option(version="1.0.0")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Ruta al archivo de configuración"
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path]) -> None:
    """MDM-GLPI Integration - Sincronización de dispositivos móviles."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.option(
    "--type",
    "-t",
    "sync_type",
    type=click.Choice(["full", "incremental"]),
    default="full",
    help="Tipo de sincronización a ejecutar"
)
@click.pass_context
def sync(ctx: click.Context, sync_type: str) -> None:
    """Ejecutar sincronización manual."""
    config_path = ctx.obj.get("config_path")
    
    async def run_sync():
        app = MDMGLPIIntegration(config_path)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"Ejecutando sincronización {sync_type}...", 
                total=None
            )
            
            try:
                await app.startup()
                await app.run_manual_sync(sync_type)
                progress.update(task, description="✅ Sincronización completada")
                console.print(f"[green]Sincronización {sync_type} completada exitosamente[/green]")
            except Exception as e:
                progress.update(task, description="❌ Error en sincronización")
                console.print(f"[red]Error: {e}[/red]")
                sys.exit(1)
            finally:
                await app.shutdown()
    
    asyncio.run(run_sync())


@cli.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Ejecutar la aplicación en modo daemon."""
    config_path = ctx.obj.get("config_path")
    
    console.print("[blue]Iniciando MDM-GLPI Integration...[/blue]")
    
    async def run_app():
        app = MDMGLPIIntegration(config_path)
        await app.run()
    
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        console.print("\n[yellow]Aplicación detenida por el usuario[/yellow]")
    except Exception as e:
        console.print(f"[red]Error crítico: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Verificar el estado de salud de las conexiones."""
    config_path = ctx.obj.get("config_path")
    
    async def check_health():
        settings = Settings(config_path)
        health_checker = HealthChecker(settings)
        
        table = Table(title="Estado de Salud del Sistema")
        table.add_column("Componente", style="cyan")
        table.add_column("Estado", style="magenta")
        table.add_column("Detalles", style="green")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Verificando conectividad...", total=None)
            
            # Verificar MDM
            try:
                mdm_ok = await health_checker.check_mdm_connectivity()
                mdm_status = "✅ OK" if mdm_ok else "❌ ERROR"
                mdm_details = "Conectado" if mdm_ok else "Sin conexión"
            except Exception as e:
                mdm_status = "❌ ERROR"
                mdm_details = str(e)
            
            table.add_row("ManageEngine MDM", mdm_status, mdm_details)
            
            # Verificar GLPI
            try:
                glpi_ok = await health_checker.check_glpi_connectivity()
                glpi_status = "✅ OK" if glpi_ok else "❌ ERROR"
                glpi_details = "Conectado" if glpi_ok else "Sin conexión"
            except Exception as e:
                glpi_status = "❌ ERROR"
                glpi_details = str(e)
            
            table.add_row("GLPI", glpi_status, glpi_details)
            
            # Verificar base de datos
            try:
                db_ok = await health_checker.check_database_health()
                db_status = "✅ OK" if db_ok else "❌ ERROR"
                db_details = "Conectado" if db_ok else "Sin conexión"
            except Exception as e:
                db_status = "❌ ERROR"
                db_details = str(e)
            
            table.add_row("Base de Datos", db_status, db_details)
            
            progress.update(task, description="✅ Verificación completada")
        
        console.print(table)
    
    asyncio.run(check_health())


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Archivo de salida para la configuración"
)
@click.pass_context
def init_config(ctx: click.Context, output: Optional[Path]) -> None:
    """Generar archivo de configuración de ejemplo."""
    if output is None:
        output = Path("config.yaml")
    
    config_template = """# Configuración MDM-GLPI Integration

# Configuración de ManageEngine MDM
mdm:
  base_url: "https://your-mdm-server.com"
  api_key: "${MDM_API_KEY}"  # Variable de entorno
  timeout: 30
  rate_limit: 100
  verify_ssl: true

# Configuración de GLPI
glpi:
  base_url: "https://your-glpi-server.com"
  app_token: "${GLPI_APP_TOKEN}"  # Variable de entorno
  user_token: "${GLPI_USER_TOKEN}"  # Variable de entorno
  timeout: 30
  verify_ssl: true

# Configuración de sincronización
sync:
  # Cron para sincronización completa (diaria a las 2:00 AM)
  full_sync_cron: "0 2 * * *"
  # Cron para sincronización incremental (cada 15 minutos)
  incremental_sync_cron: "*/15 * * * *"
  # Tamaño de lote para procesamiento
  batch_size: 100
  # Máximo número de reintentos
  max_retries: 3
  # Ejecutar sincronización inicial al inicio
  run_initial_sync: false

# Configuración de base de datos
database:
  url: "sqlite:///data/mdm_glpi.db"
  echo: false
  pool_size: 5
  max_overflow: 10

# Configuración de logging
logging:
  level: "INFO"
  format: "json"
  file: "logs/mdm_glpi.log"
  max_size: "10MB"
  backup_count: 5
  console: true

# Configuración de mapeo de datos
mapping:
  # Mapeo de tipos de dispositivos MDM a GLPI
  device_types:
    "iPhone": "Phone"
    "iPad": "Computer"
    "Android": "Phone"
    "Windows": "Computer"
  
  # Mapeo de campos personalizados
  custom_fields:
    mdm_device_id: "otherserial"
    enrollment_date: "date_creation"
    last_seen: "date_mod"

# Configuración de monitoreo
monitoring:
  enable_metrics: true
  metrics_port: 8080
  health_check_interval: 300
"""
    
    try:
        output.write_text(config_template)
        console.print(f"[green]Archivo de configuración creado: {output}[/green]")
        console.print("[yellow]Recuerda configurar las variables de entorno:[/yellow]")
        console.print("  - MDM_API_KEY")
        console.print("  - GLPI_APP_TOKEN")
        console.print("  - GLPI_USER_TOKEN")
    except Exception as e:
        console.print(f"[red]Error al crear archivo de configuración: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--days",
    "-d",
    type=int,
    default=30,
    help="Número de días de logs a mostrar"
)
@click.option(
    "--level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO",
    help="Nivel mínimo de log a mostrar"
)
@click.pass_context
def logs(ctx: click.Context, days: int, level: str) -> None:
    """Mostrar logs de sincronización."""
    # Implementar visualización de logs
    console.print(f"[blue]Mostrando logs de los últimos {days} días (nivel: {level})[/blue]")
    console.print("[yellow]Funcionalidad en desarrollo[/yellow]")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Mostrar estado actual del sistema."""
    # Implementar estado del sistema
    console.print("[blue]Estado del Sistema MDM-GLPI Integration[/blue]")
    console.print("[yellow]Funcionalidad en desarrollo[/yellow]")


def main() -> None:
    """Punto de entrada principal del CLI."""
    cli()


if __name__ == "__main__":
    main()