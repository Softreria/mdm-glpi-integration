#!/usr/bin/env python3
"""Migración para agregar soporte de teléfonos.

Esta migración actualiza la tabla sync_records para soportar
tanto computadoras como teléfonos de GLPI.
"""

import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Agregar el directorio src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mdm_glpi_integration.config.settings import Settings


def run_migration():
    """Ejecutar migración de base de datos."""
    print("Iniciando migración: Agregar soporte de teléfonos...")
    
    # Cargar configuración
    settings = Settings()
    
    # Crear conexión a la base de datos
    engine = create_engine(settings.database.url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Verificar si las columnas ya existen
        result = session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'sync_records' 
            AND column_name IN ('glpi_device_type', 'glpi_device_id')
        """))
        
        existing_columns = [row[0] for row in result.fetchall()]
        
        # Agregar columna glpi_device_type si no existe
        if 'glpi_device_type' not in existing_columns:
            print("Agregando columna glpi_device_type...")
            session.execute(text("""
                ALTER TABLE sync_records 
                ADD COLUMN glpi_device_type VARCHAR(50)
            """))
        
        # Renombrar glpi_computer_id a glpi_device_id si es necesario
        if 'glpi_device_id' not in existing_columns:
            print("Renombrando glpi_computer_id a glpi_device_id...")
            session.execute(text("""
                ALTER TABLE sync_records 
                CHANGE COLUMN glpi_computer_id glpi_device_id INTEGER
            """))
        
        # Actualizar registros existentes para marcarlos como 'computer'
        print("Actualizando registros existentes...")
        session.execute(text("""
            UPDATE sync_records 
            SET glpi_device_type = 'computer' 
            WHERE glpi_device_type IS NULL AND glpi_device_id IS NOT NULL
        """))
        
        session.commit()
        print("✅ Migración completada exitosamente")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error durante la migración: {e}")
        raise
    
    finally:
        session.close()


if __name__ == "__main__":
    run_migration()