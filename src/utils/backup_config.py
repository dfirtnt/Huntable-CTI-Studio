#!/usr/bin/env python3
"""
Backup Configuration Manager for CTI Scraper

This module handles backup configuration loading, validation, and management.
Supports YAML configuration files with environment-specific overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class BackupConfig:
    """Backup configuration data class."""
    
    # Schedule settings
    backup_time: str = "02:00"
    cleanup_time: str = "03:00"
    cleanup_day: int = 0  # 0=Sunday
    
    # Retention policy
    daily: int = 7
    weekly: int = 4
    monthly: int = 3
    max_size_gb: int = 50
    
    # Backup settings
    backup_dir: str = "backups"
    compress: bool = True
    verify: bool = True
    backup_type: str = "full"
    
    # Components to backup
    database: bool = True
    models: bool = True
    config: bool = True
    outputs: bool = True
    logs: bool = True
    docker_volumes: bool = True
    
    # Docker volume settings
    volume_list: List[str] = field(default_factory=lambda: ["postgres_data", "redis_data", "ollama_data"])
    stop_containers: bool = True
    
    # Verification settings
    checksums: bool = True
    test_restore: bool = False
    critical_patterns: Dict[str, List[str]] = field(default_factory=dict)
    
    # Logging settings
    log_file: str = "logs/backup.log"
    log_level: str = "INFO"
    rotate_logs: bool = True
    keep_logs: int = 30
    
    # Security settings
    encrypt: bool = False
    key_file: str = "backup.key"
    file_permissions: str = "0644"
    dir_permissions: str = "0755"
    
    # Performance settings
    max_threads: int = 4
    timeout: int = 300
    progress: bool = True
    chunk_size: int = 4096

class BackupConfigManager:
    """Manages backup configuration loading and validation."""
    
    def __init__(self, config_file: Optional[str] = None, environment: Optional[str] = None):
        """
        Initialize the backup configuration manager.
        
        Args:
            config_file: Path to configuration file (default: config/backup.yaml)
            environment: Environment name for overrides (development, production, testing)
        """
        self.config_file = config_file or "config/backup.yaml"
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.config = BackupConfig()
        
        # Set default critical patterns
        self.config.critical_patterns = {
            "models": ["*.pkl", "*.joblib", "*.h5", "*.onnx"],
            "config": ["*.yaml", "*.yml", "*.json"],
            "outputs": ["*.csv", "*.json", "*.txt"],
            "training_data": ["*.csv", "*.json"]
        }
        
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_path = Path(self.config_file)
        
        if not config_path.exists():
            logger.warning(f"Configuration file not found: {config_path}")
            return
        
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                logger.warning("Configuration file is empty")
                return
            
            # Apply base configuration
            self._apply_config(config_data)
            
            # Apply environment-specific overrides
            if self.environment in config_data.get("environments", {}):
                env_config = config_data["environments"][self.environment]
                self._apply_config(env_config)
            
            logger.info(f"Loaded backup configuration from {config_path} (environment: {self.environment})")
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing configuration file {config_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading configuration file {config_path}: {e}")
    
    def _apply_config(self, config_data: Dict[str, Any]) -> None:
        """Apply configuration data to the config object."""
        
        # Schedule settings
        if "schedule" in config_data:
            schedule = config_data["schedule"]
            if "backup_time" in schedule:
                self.config.backup_time = schedule["backup_time"]
            if "cleanup_time" in schedule:
                self.config.cleanup_time = schedule["cleanup_time"]
            if "cleanup_day" in schedule:
                self.config.cleanup_day = schedule["cleanup_day"]
        
        # Retention policy
        if "retention" in config_data:
            retention = config_data["retention"]
            if "daily" in retention:
                self.config.daily = retention["daily"]
            if "weekly" in retention:
                self.config.weekly = retention["weekly"]
            if "monthly" in retention:
                self.config.monthly = retention["monthly"]
            if "max_size_gb" in retention:
                self.config.max_size_gb = retention["max_size_gb"]
        
        # Backup settings
        if "backup" in config_data:
            backup = config_data["backup"]
            if "directory" in backup:
                self.config.backup_dir = backup["directory"]
            if "compress" in backup:
                self.config.compress = backup["compress"]
            if "verify" in backup:
                self.config.verify = backup["verify"]
            if "type" in backup:
                self.config.backup_type = backup["type"]
        
        # Components
        if "components" in config_data:
            components = config_data["components"]
            if "database" in components:
                self.config.database = components["database"]
            if "models" in components:
                self.config.models = components["models"]
            if "config" in components:
                self.config.config = components["config"]
            if "outputs" in components:
                self.config.outputs = components["outputs"]
            if "logs" in components:
                self.config.logs = components["logs"]
            if "docker_volumes" in components:
                self.config.docker_volumes = components["docker_volumes"]
        
        # Docker volumes
        if "docker_volumes" in config_data:
            docker_volumes = config_data["docker_volumes"]
            if "volumes" in docker_volumes:
                self.config.volume_list = docker_volumes["volumes"]
            if "stop_containers" in docker_volumes:
                self.config.stop_containers = docker_volumes["stop_containers"]
        
        # Verification settings
        if "verification" in config_data:
            verification = config_data["verification"]
            if "checksums" in verification:
                self.config.checksums = verification["checksums"]
            if "test_restore" in verification:
                self.config.test_restore = verification["test_restore"]
            if "critical_patterns" in verification:
                self.config.critical_patterns = verification["critical_patterns"]
        
        # Logging settings
        if "logging" in config_data:
            logging_config = config_data["logging"]
            if "log_file" in logging_config:
                self.config.log_file = logging_config["log_file"]
            if "level" in logging_config:
                self.config.log_level = logging_config["level"]
            if "rotate" in logging_config:
                self.config.rotate_logs = logging_config["rotate"]
            if "keep_logs" in logging_config:
                self.config.keep_logs = logging_config["keep_logs"]
        
        # Security settings
        if "security" in config_data:
            security = config_data["security"]
            if "encrypt" in security:
                self.config.encrypt = security["encrypt"]
            if "key_file" in security:
                self.config.key_file = security["key_file"]
            if "file_permissions" in security:
                self.config.file_permissions = security["file_permissions"]
            if "dir_permissions" in security:
                self.config.dir_permissions = security["dir_permissions"]
        
        # Performance settings
        if "performance" in config_data:
            performance = config_data["performance"]
            if "max_threads" in performance:
                self.config.max_threads = performance["max_threads"]
            if "timeout" in performance:
                self.config.timeout = performance["timeout"]
            if "progress" in performance:
                self.config.progress = performance["progress"]
            if "chunk_size" in performance:
                self.config.chunk_size = performance["chunk_size"]
    
    def get_config(self) -> BackupConfig:
        """Get the current configuration."""
        return self.config
    
    def get_retention_policy(self) -> Dict[str, int]:
        """Get retention policy as dictionary."""
        return {
            "daily": self.config.daily,
            "weekly": self.config.weekly,
            "monthly": self.config.monthly,
            "max_size_gb": self.config.max_size_gb
        }
    
    def get_schedule_config(self) -> Dict[str, Any]:
        """Get schedule configuration as dictionary."""
        return {
            "backup_time": self.config.backup_time,
            "cleanup_time": self.config.cleanup_time,
            "cleanup_day": self.config.cleanup_day
        }
    
    def get_backup_settings(self) -> Dict[str, Any]:
        """Get backup settings as dictionary."""
        return {
            "directory": self.config.backup_dir,
            "compress": self.config.compress,
            "verify": self.config.verify,
            "type": self.config.backup_type
        }
    
    def get_components(self) -> Dict[str, bool]:
        """Get component settings as dictionary."""
        return {
            "database": self.config.database,
            "models": self.config.models,
            "config": self.config.config,
            "outputs": self.config.outputs,
            "logs": self.config.logs,
            "docker_volumes": self.config.docker_volumes
        }
    
    def get_docker_volumes(self) -> List[str]:
        """Get list of Docker volumes to backup."""
        return self.config.volume_list.copy()
    
    def get_critical_patterns(self) -> Dict[str, List[str]]:
        """Get critical file patterns for validation."""
        return self.config.critical_patterns.copy()
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Validate time format
        try:
            hour, minute = self.config.backup_time.split(":")
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                errors.append(f"Invalid backup_time: {self.config.backup_time}")
        except ValueError:
            errors.append(f"Invalid backup_time format: {self.config.backup_time}")
        
        try:
            hour, minute = self.config.cleanup_time.split(":")
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                errors.append(f"Invalid cleanup_time: {self.config.cleanup_time}")
        except ValueError:
            errors.append(f"Invalid cleanup_time format: {self.config.cleanup_time}")
        
        # Validate retention policy
        if self.config.daily < 0:
            errors.append("daily retention must be >= 0")
        if self.config.weekly < 0:
            errors.append("weekly retention must be >= 0")
        if self.config.monthly < 0:
            errors.append("monthly retention must be >= 0")
        if self.config.max_size_gb <= 0:
            errors.append("max_size_gb must be > 0")
        
        # Validate backup type
        if self.config.backup_type not in ["full", "database", "files"]:
            errors.append("backup_type must be one of: full, database, files")
        
        # Validate log level
        if self.config.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            errors.append("log_level must be one of: DEBUG, INFO, WARNING, ERROR")
        
        # Validate performance settings
        if self.config.max_threads <= 0:
            errors.append("max_threads must be > 0")
        if self.config.timeout <= 0:
            errors.append("timeout must be > 0")
        if self.config.chunk_size <= 0:
            errors.append("chunk_size must be > 0")
        
        return errors
    
    def save_config(self, config_file: Optional[str] = None) -> bool:
        """Save current configuration to YAML file."""
        config_path = Path(config_file or self.config_file)
        
        try:
            # Create directory if it doesn't exist
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert config to dictionary
            config_data = {
                "schedule": {
                    "backup_time": self.config.backup_time,
                    "cleanup_time": self.config.cleanup_time,
                    "cleanup_day": self.config.cleanup_day
                },
                "retention": {
                    "daily": self.config.daily,
                    "weekly": self.config.weekly,
                    "monthly": self.config.monthly,
                    "max_size_gb": self.config.max_size_gb
                },
                "backup": {
                    "directory": self.config.backup_dir,
                    "compress": self.config.compress,
                    "verify": self.config.verify,
                    "type": self.config.backup_type
                },
                "components": {
                    "database": self.config.database,
                    "models": self.config.models,
                    "config": self.config.config,
                    "outputs": self.config.outputs,
                    "logs": self.config.logs,
                    "docker_volumes": self.config.docker_volumes
                },
                "docker_volumes": {
                    "volumes": self.config.volume_list,
                    "stop_containers": self.config.stop_containers
                },
                "verification": {
                    "checksums": self.config.checksums,
                    "test_restore": self.config.test_restore,
                    "critical_patterns": self.config.critical_patterns
                },
                "logging": {
                    "log_file": self.config.log_file,
                    "level": self.config.log_level,
                    "rotate": self.config.rotate_logs,
                    "keep_logs": self.config.keep_logs
                },
                "security": {
                    "encrypt": self.config.encrypt,
                    "key_file": self.config.key_file,
                    "file_permissions": self.config.file_permissions,
                    "dir_permissions": self.config.dir_permissions
                },
                "performance": {
                    "max_threads": self.config.max_threads,
                    "timeout": self.config.timeout,
                    "progress": self.config.progress,
                    "chunk_size": self.config.chunk_size
                }
            }
            
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Configuration saved to {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving configuration to {config_path}: {e}")
            return False

# Global configuration instance
_config_manager: Optional[BackupConfigManager] = None

def get_backup_config(config_file: Optional[str] = None, environment: Optional[str] = None) -> BackupConfig:
    """Get backup configuration instance."""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = BackupConfigManager(config_file, environment)
    
    return _config_manager.get_config()

def get_backup_config_manager(config_file: Optional[str] = None, environment: Optional[str] = None) -> BackupConfigManager:
    """Get backup configuration manager instance."""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = BackupConfigManager(config_file, environment)
    
    return _config_manager
