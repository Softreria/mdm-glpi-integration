# Soporte de Teléfonos en GLPI

Este documento describe las modificaciones realizadas para que los dispositivos móviles del MDM aparezcan en la sección "Teléfonos" de GLPI en lugar de "Computadoras".

## Cambios Realizados

### 1. Nuevo Modelo GLPIPhone

Se creó un nuevo modelo `GLPIPhone` en `src/mdm_glpi_integration/models/device.py` que:

- Utiliza la API `/Phone` de GLPI
- Incluye campos específicos de teléfonos:
  - `phonetypes_id`: Tipo de teléfono
  - `phonemodels_id`: Modelo de teléfono
  - `number_line`: Número de línea telefónica
- Mantiene compatibilidad con campos MDM personalizados

### 2. Funciones de Teléfonos en GLPIConnector

Se agregaron nuevas funciones en `src/mdm_glpi_integration/connectors/glpi_connector.py`:

- `search_phones()`: Buscar teléfonos en GLPI
- `get_phone_by_mdm_id()`: Buscar teléfono por ID MDM
- `get_phone_by_serial()`: Buscar teléfono por número de serie
- `get_phone()`: Obtener teléfono por ID
- `create_phone()`: Crear nuevo teléfono
- `update_phone()`: Actualizar teléfono existente
- `sync_mobile_device_from_mdm()`: Sincronizar dispositivo móvil como teléfono

### 3. Resolución de Metadatos para Teléfonos

Se implementaron funciones auxiliares:

- `_resolve_phone_metadata_ids()`: Resolver IDs de metadatos específicos de teléfonos
- `_get_or_create_phone_model()`: Obtener o crear modelo de teléfono
- `_get_or_create_phone_type()`: Obtener o crear tipo de teléfono

### 4. Lógica de Detección Automática

La función `sync_device_from_mdm()` ahora:

1. Detecta automáticamente si un dispositivo es móvil usando `mdm_device.is_mobile`
2. Para dispositivos móviles: usa la API de teléfonos
3. Para dispositivos no móviles: usa la API de computadoras

### 5. Actualización de Base de Datos

Se modificó el modelo `SyncRecord` para soportar ambos tipos:

- `glpi_device_id`: ID genérico del dispositivo en GLPI
- `glpi_device_type`: Tipo de dispositivo ('computer' o 'phone')

### 6. Migración de Base de Datos

Se creó el script `migrations/001_add_phone_support.py` para:

- Agregar nuevas columnas a la tabla `sync_records`
- Migrar datos existentes
- Mantener compatibilidad con registros anteriores

## Configuración

### Mapeo de Tipos de Dispositivos

En `src/mdm_glpi_integration/config/settings.py`, el mapeo actual es:

```python
device_types = {
    "iPhone": "Phone",
    "Android": "Phone", 
    "iPad": "Computer",
    "Windows": "Computer"
}
```

### Detección de Dispositivos Móviles

La propiedad `is_mobile` en `MDMDevice` determina si un dispositivo se trata como teléfono:

```python
@property
def is_mobile(self) -> bool:
    """Determinar si el dispositivo es móvil."""
    mobile_types = {"iPhone", "Android"}
    return self.device_type in mobile_types
```

## Uso

### Sincronización Automática

La sincronización funciona automáticamente:

```bash
# Los dispositivos móviles aparecerán en GLPI -> Parque -> Teléfonos
# Los dispositivos no móviles aparecerán en GLPI -> Parque -> Equipos
python cli.py sync --type full
```

### Migración de Datos Existentes

Para migrar datos existentes:

```bash
# Ejecutar migración de base de datos
python migrations/001_add_phone_support.py

# Re-sincronizar dispositivos existentes
python cli.py sync --type full --force
```

## Verificación

### En GLPI

1. **Teléfonos**: Ir a `Parque > Teléfonos`
   - Dispositivos iPhone y Android aparecerán aquí
   - Tendrán tipo "Mobile" y modelo correspondiente

2. **Computadoras**: Ir a `Parque > Equipos`
   - Dispositivos iPad y Windows aparecerán aquí
   - Mantendrán el comportamiento anterior

### En Logs

Buscar en los logs mensajes como:

```
Dispositivo sincronizado: device_id=XXX, glpi_id=YYY, device_type=phone, action=created
```

## Campos GLPI

### Teléfonos

- **Nombre**: Nombre del dispositivo MDM
- **Número de serie**: Serial del dispositivo
- **Otro número de serie**: IMEI del dispositivo
- **Número de línea**: Número de teléfono (si disponible)
- **Fabricante**: Apple, Samsung, etc.
- **Modelo**: iPhone 14, Galaxy S23, etc.
- **Tipo**: Mobile, Phone
- **Estado**: Active/Inactive
- **Usuario**: Usuario asignado
- **Comentarios**: Información detallada del MDM

### Campos Personalizados MDM

Todos los campos personalizados se mantienen:

- `mdm_device_id`
- `mdm_last_seen`
- `mdm_enrollment_date`
- `mdm_status`
- `mdm_is_supervised`
- `mdm_battery_level`
- `mdm_storage_total`
- `mdm_storage_available`
- `mdm_os_type`
- `mdm_os_version`

## Troubleshooting

### Dispositivos No Aparecen en Teléfonos

1. Verificar que `is_mobile` retorne `True`
2. Revisar logs de sincronización
3. Verificar permisos de API en GLPI para `/Phone`

### Error de Migración

1. Hacer backup de la base de datos
2. Ejecutar migración manualmente
3. Verificar estructura de tabla resultante

### Dispositivos Duplicados

1. Ejecutar limpieza de registros duplicados
2. Re-sincronizar con `--force`
3. Verificar unicidad por serial/IMEI