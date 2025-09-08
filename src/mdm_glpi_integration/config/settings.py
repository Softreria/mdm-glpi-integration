"""Configuración del sistema MDM-GLPI Integration."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
import yaml


class MDMConfig(BaseModel):
    """Configuración para ManageEngine MDM."""
    
    base_url: str = Field(..., description="URL base del servidor MDM")
    api_key: str = Field(..., description="Clave API para MDM")
    timeout: int = Field(30, description="Timeout en segundos")
    rate_limit: int = Field(100, description="Límite de requests por minuto")
    verify_ssl: bool = Field(True, description="Verificar certificados SSL")
    
    @validator('base_url')
    def validate_base_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('base_url debe comenzar con http:// o https://')
        return v.rstrip('/')
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError('api_key debe tener al menos 10 caracteres')
        return v


class GLPIConfig(BaseModel):
    """Configuración para GLPI."""
    
    base_url: str = Field(..., description="URL base del servidor GLPI")
    app_token: str = Field(..., description="Token de aplicación GLPI")
    user_token: str = Field(..., description="Token de usuario GLPI")
    timeout: int = Field(30, description="Timeout en segundos")
    verify_ssl: bool = Field(True, description="Verificar certificados SSL")
    
    @validator('base_url')
    def validate_base_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('base_url debe comenzar con http:// o https://')
        return v.rstrip('/')
    
    @validator('app_token', 'user_token')
    def validate_tokens(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Los tokens deben tener al menos 10 caracteres')
        return v


class SyncConfig(BaseModel):
    """Configuración de sincronización."""
    
    full_sync_cron: str = Field("0 2 * * *", description="Cron para sync completa")
    incremental_sync_cron: str = Field("*/15 * * * *", description="Cron para sync incremental")
    batch_size: int = Field(100, description="Tamaño de lote")
    max_retries: int = Field(3, description="Máximo número de reintentos")
    run_initial_sync: bool = Field(False, description="Ejecutar sync inicial")
    
    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v < 1 or v > 1000:
            raise ValueError('batch_size debe estar entre 1 y 1000')
        return v
    
    @validator('max_retries')
    def validate_max_retries(cls, v):
        if v < 0 or v > 10:
            raise ValueError('max_retries debe estar entre 0 y 10')
        return v


class DatabaseConfig(BaseModel):
    """Configuración de base de datos."""
    
    url: str = Field("sqlite:///data/mdm_glpi.db", description="URL de conexión")
    echo: bool = Field(False, description="Habilitar logging SQL")
    pool_size: int = Field(5, description="Tamaño del pool de conexiones")
    max_overflow: int = Field(10, description="Máximo overflow del pool")
    
    @validator('pool_size', 'max_overflow')
    def validate_pool_settings(cls, v):
        if v < 1:
            raise ValueError('Los valores del pool deben ser positivos')
        return v


class LoggingConfig(BaseModel):
    """Configuración de logging."""
    
    level: str = Field("INFO", description="Nivel de logging")
    format: str = Field("json", description="Formato de logs")
    file: str = Field("logs/mdm_glpi.log", description="Archivo de logs")
    max_size: str = Field("10MB", description="Tamaño máximo del archivo")
    backup_count: int = Field(5, description="Número de backups")
    console: bool = Field(True, description="Mostrar logs en consola")
    
    @validator('level')
    def validate_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'level debe ser uno de: {valid_levels}')
        return v.upper()
    
    @validator('format')
    def validate_format(cls, v):
        valid_formats = ['json', 'text']
        if v.lower() not in valid_formats:
            raise ValueError(f'format debe ser uno de: {valid_formats}')
        return v.lower()


class MappingConfig(BaseModel):
    """Configuración de mapeo de datos."""
    
    device_types: Dict[str, str] = Field(
        default_factory=lambda: {
            "iPhone": "Phone",
            "iPad": "Computer", 
            "Android": "Phone",
            "Windows": "Computer"
        },
        description="Mapeo de tipos de dispositivos"
    )
    
    custom_fields: Dict[str, str] = Field(
        default_factory=lambda: {
            "mdm_device_id": "otherserial",
            "enrollment_date": "date_creation",
            "last_seen": "date_mod"
        },
        description="Mapeo de campos personalizados"
    )


class MonitoringConfig(BaseModel):
    """Configuración de monitoreo."""
    
    enable_metrics: bool = Field(True, description="Habilitar métricas")
    metrics_port: int = Field(8080, description="Puerto para métricas")
    health_check_interval: int = Field(300, description="Intervalo de health check")
    
    @validator('metrics_port')
    def validate_metrics_port(cls, v):
        if v < 1024 or v > 65535:
            raise ValueError('metrics_port debe estar entre 1024 y 65535')
        return v


class Settings(BaseSettings):
    """Configuración principal del sistema."""
    
    mdm: MDMConfig
    glpi: GLPIConfig
    sync: SyncConfig = Field(default_factory=SyncConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        case_sensitive = False
    
    def __init__(self, config_path: Optional[Path] = None, **kwargs):
        """Inicializar configuración.
        
        Args:
            config_path: Ruta al archivo de configuración YAML
            **kwargs: Argumentos adicionales
        """
        # Cargar configuración desde archivo YAML si se proporciona
        if config_path and config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
            
            # Expandir variables de entorno en la configuración
            yaml_config = self._expand_env_vars(yaml_config)
            
            # Combinar con kwargs
            kwargs.update(yaml_config)
        
        super().__init__(**kwargs)
    
    def _expand_env_vars(self, config: Any) -> Any:
        """Expandir variables de entorno en la configuración.
        
        Args:
            config: Configuración a procesar
            
        Returns:
            Configuración con variables expandidas
        """
        if isinstance(config, dict):
            return {k: self._expand_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._expand_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            # Extraer nombre de variable de entorno
            env_var = config[2:-1]
            default_value = None
            
            # Soportar valores por defecto: ${VAR:default}
            if ':' in env_var:
                env_var, default_value = env_var.split(':', 1)
            
            return os.getenv(env_var, default_value)
        else:
            return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir configuración a diccionario.
        
        Returns:
            Diccionario con la configuración
        """
        return self.dict()
    
    def save_to_file(self, file_path: Path) -> None:
        """Guardar configuración en archivo YAML.
        
        Args:
            file_path: Ruta donde guardar el archivo
        """
        config_dict = self.to_dict()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, indent=2)
    
    @classmethod
    def from_file(cls, file_path: Path) -> 'Settings':
        """Crear configuración desde archivo.
        
        Args:
            file_path: Ruta al archivo de configuración
            
        Returns:
            Instancia de Settings
        """
        return cls(config_path=file_path)
    
    def validate_configuration(self) -> bool:
        """Validar que la configuración sea correcta.
        
        Returns:
            True si la configuración es válida
            
        Raises:
            ValueError: Si la configuración no es válida
        """
        try:
            # Validar que las URLs sean accesibles (básico)
            if not self.mdm.base_url or not self.glpi.base_url:
                raise ValueError("URLs base son requeridas")
            
            # Validar que los tokens estén configurados
            if not self.mdm.api_key:
                raise ValueError("MDM API key es requerida")
            
            if not self.glpi.app_token or not self.glpi.user_token:
                raise ValueError("GLPI tokens son requeridos")
            
            return True
            
        except Exception as e:
            raise ValueError(f"Configuración inválida: {e}")