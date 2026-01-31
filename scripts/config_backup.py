#!/usr/bin/env python3
"""
Backup Configuration Management Script for CTI Scraper

This script provides a command-line interface for managing backup configuration:
- View current configuration
- Update configuration settings
- Validate configuration
- Export/import configuration
- Environment-specific settings

Features:
- Interactive configuration editor
- Configuration validation
- Environment management
- Backup configuration templates
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from utils.backup_config import BackupConfigManager
except ImportError:
    print("Error: Could not import backup configuration module")
    sys.exit(1)


def show_config(config_manager: BackupConfigManager) -> None:
    """Show current configuration."""
    config = config_manager.get_config()

    print("📋 Current Backup Configuration")
    print("=" * 50)

    print(f"Environment: {config_manager.environment}")
    print(f"Config file: {config_manager.config_file}")
    print()

    print("🕐 Schedule:")
    print(f"  Backup time: {config.backup_time}")
    print(f"  Cleanup time: {config.cleanup_time}")
    print(f"  Cleanup day: {config.cleanup_day} (0=Sunday)")
    print()

    print("📊 Retention Policy:")
    print(f"  Daily: {config.daily} backups")
    print(f"  Weekly: {config.weekly} backups")
    print(f"  Monthly: {config.monthly} backups")
    print(f"  Max size: {config.max_size_gb} GB")
    print()

    print("💾 Backup Settings:")
    print(f"  Directory: {config.backup_dir}")
    print(f"  Compress: {config.compress}")
    print(f"  Verify: {config.verify}")
    print(f"  Type: {config.backup_type}")
    print()

    print("🧩 Components:")
    components = {
        "Database": config.database,
        "Models": config.models,
        "Config": config.config,
        "Outputs": config.outputs,
        "Logs": config.logs,
        "Docker Volumes": config.docker_volumes,
    }
    for name, enabled in components.items():
        status = "✅" if enabled else "❌"
        print(f"  {status} {name}")
    print()

    print("🐳 Docker Volumes:")
    for volume in config.volume_list:
        print(f"  • {volume}")
    print(f"  Stop containers: {config.stop_containers}")
    print()

    print("🔍 Verification:")
    print(f"  Checksums: {config.checksums}")
    print(f"  Test restore: {config.test_restore}")
    print()

    print("📝 Logging:")
    print(f"  Log file: {config.log_file}")
    print(f"  Level: {config.log_level}")
    print(f"  Rotate: {config.rotate_logs}")
    print(f"  Keep logs: {config.keep_logs}")
    print()

    print("🔒 Security:")
    print(f"  Encrypt: {config.encrypt}")
    print(f"  Key file: {config.key_file}")
    print(f"  File permissions: {config.file_permissions}")
    print(f"  Dir permissions: {config.dir_permissions}")
    print()

    print("⚡ Performance:")
    print(f"  Max threads: {config.max_threads}")
    print(f"  Timeout: {config.timeout}s")
    print(f"  Progress: {config.progress}")
    print(f"  Chunk size: {config.chunk_size}")


def validate_config(config_manager: BackupConfigManager) -> None:
    """Validate current configuration."""
    print("🔍 Validating Configuration")
    print("=" * 30)

    errors = config_manager.validate_config()

    if not errors:
        print("✅ Configuration is valid!")
    else:
        print("❌ Configuration validation failed:")
        for error in errors:
            print(f"  • {error}")


def update_config(config_manager: BackupConfigManager, args: argparse.Namespace) -> None:
    """Update configuration based on command line arguments."""
    config = config_manager.get_config()

    print("🔄 Updating Configuration")
    print("=" * 30)

    # Update schedule
    if args.backup_time:
        config.backup_time = args.backup_time
        print(f"✅ Backup time set to: {args.backup_time}")

    if args.cleanup_time:
        config.cleanup_time = args.cleanup_time
        print(f"✅ Cleanup time set to: {args.cleanup_time}")

    # Update retention policy
    if args.daily is not None:
        config.daily = args.daily
        print(f"✅ Daily retention set to: {args.daily}")

    if args.weekly is not None:
        config.weekly = args.weekly
        print(f"✅ Weekly retention set to: {args.weekly}")

    if args.monthly is not None:
        config.monthly = args.monthly
        print(f"✅ Monthly retention set to: {args.monthly}")

    if args.max_size_gb is not None:
        config.max_size_gb = args.max_size_gb
        print(f"✅ Max size set to: {args.max_size_gb} GB")

    # Update backup settings
    if args.backup_dir:
        config.backup_dir = args.backup_dir
        print(f"✅ Backup directory set to: {args.backup_dir}")

    if args.compress is not None:
        config.compress = args.compress
        print(f"✅ Compression set to: {args.compress}")

    if args.verify is not None:
        config.verify = args.verify
        print(f"✅ Verification set to: {args.verify}")

    # Update components
    if args.disable_components:
        for component in args.disable_components:
            if hasattr(config, component):
                setattr(config, component, False)
                print(f"✅ Disabled component: {component}")

    if args.enable_components:
        for component in args.enable_components:
            if hasattr(config, component):
                setattr(config, component, True)
                print(f"✅ Enabled component: {component}")

    # Update performance settings
    if args.max_threads is not None:
        config.max_threads = args.max_threads
        print(f"✅ Max threads set to: {args.max_threads}")

    if args.timeout is not None:
        config.timeout = args.timeout
        print(f"✅ Timeout set to: {args.timeout}s")

    # Validate updated configuration
    errors = config_manager.validate_config()
    if errors:
        print("\n❌ Configuration validation failed:")
        for error in errors:
            print(f"  • {error}")
        return

    # Save configuration
    if config_manager.save_config():
        print("\n✅ Configuration updated and saved successfully!")
    else:
        print("\n❌ Failed to save configuration")


def export_config(config_manager: BackupConfigManager, output_file: str) -> None:
    """Export configuration to file."""
    print(f"📤 Exporting configuration to: {output_file}")

    config = config_manager.get_config()

    # Convert config to dictionary
    config_data = {
        "schedule": {
            "backup_time": config.backup_time,
            "cleanup_time": config.cleanup_time,
            "cleanup_day": config.cleanup_day,
        },
        "retention": {
            "daily": config.daily,
            "weekly": config.weekly,
            "monthly": config.monthly,
            "max_size_gb": config.max_size_gb,
        },
        "backup": {
            "directory": config.backup_dir,
            "compress": config.compress,
            "verify": config.verify,
            "type": config.backup_type,
        },
        "components": {
            "database": config.database,
            "models": config.models,
            "config": config.config,
            "outputs": config.outputs,
            "logs": config.logs,
            "docker_volumes": config.docker_volumes,
        },
        "docker_volumes": {"volumes": config.volume_list, "stop_containers": config.stop_containers},
        "verification": {
            "checksums": config.checksums,
            "test_restore": config.test_restore,
            "critical_patterns": config.critical_patterns,
        },
        "logging": {
            "log_file": config.log_file,
            "level": config.log_level,
            "rotate": config.rotate_logs,
            "keep_logs": config.keep_logs,
        },
        "security": {
            "encrypt": config.encrypt,
            "key_file": config.key_file,
            "file_permissions": config.file_permissions,
            "dir_permissions": config.dir_permissions,
        },
        "performance": {
            "max_threads": config.max_threads,
            "timeout": config.timeout,
            "progress": config.progress,
            "chunk_size": config.chunk_size,
        },
    }

    try:
        with open(output_file, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, indent=2)
        print("✅ Configuration exported successfully!")
    except Exception as e:
        print(f"❌ Failed to export configuration: {e}")


def sync_with_ui_settings(config_manager: BackupConfigManager, ui_settings_file: str | None) -> None:
    """Sync configuration with UI settings."""
    print("🔄 Syncing configuration with UI settings")

    if not ui_settings_file:
        # Try to find UI settings in common locations
        possible_paths = ["ui_settings.json", "settings.json", "backup_ui_settings.json"]

        for path in possible_paths:
            if Path(path).exists():
                ui_settings_file = path
                break

        if not ui_settings_file:
            print("❌ No UI settings file found. Please specify --ui-settings")
            return

    try:
        with open(ui_settings_file) as f:
            ui_settings = json.load(f)

        backup_settings = ui_settings.get("backupSettings", {})
        if not backup_settings:
            print("❌ No backup settings found in UI settings")
            return

        config = config_manager.get_config()

        # Update configuration from UI settings
        if "backupTime" in backup_settings:
            config.backup_time = backup_settings["backupTime"]
            print(f"✅ Updated backup time: {config.backup_time}")

        if "cleanupTime" in backup_settings:
            config.cleanup_time = backup_settings["cleanupTime"]
            print(f"✅ Updated cleanup time: {config.cleanup_time}")

        if "dailyRetention" in backup_settings:
            config.daily = backup_settings["dailyRetention"]
            print(f"✅ Updated daily retention: {config.daily}")

        if "weeklyRetention" in backup_settings:
            config.weekly = backup_settings["weeklyRetention"]
            print(f"✅ Updated weekly retention: {config.weekly}")

        if "monthlyRetention" in backup_settings:
            config.monthly = backup_settings["monthlyRetention"]
            print(f"✅ Updated monthly retention: {config.monthly}")

        if "maxSizeGb" in backup_settings:
            config.max_size_gb = backup_settings["maxSizeGb"]
            print(f"✅ Updated max size: {config.max_size_gb} GB")

        if "backupDirectory" in backup_settings:
            config.backup_dir = backup_settings["backupDirectory"]
            print(f"✅ Updated backup directory: {config.backup_dir}")

        if "backupType" in backup_settings:
            config.backup_type = backup_settings["backupType"]
            print(f"✅ Updated backup type: {config.backup_type}")

        if "enableCompression" in backup_settings:
            config.compress = backup_settings["enableCompression"]
            print(f"✅ Updated compression: {config.compress}")

        if "enableVerification" in backup_settings:
            config.verify = backup_settings["enableVerification"]
            print(f"✅ Updated verification: {config.verify}")

        # Update components
        component_mapping = {
            "backupDatabase": "database",
            "backupModels": "models",
            "backupConfig": "config",
            "backupOutputs": "outputs",
            "backupLogs": "logs",
            "backupDockerVolumes": "docker_volumes",
        }

        for ui_key, config_key in component_mapping.items():
            if ui_key in backup_settings:
                setattr(config, config_key, backup_settings[ui_key])
                print(f"✅ Updated {config_key}: {backup_settings[ui_key]}")

        # Validate and save
        errors = config_manager.validate_config()
        if errors:
            print("\n❌ Configuration validation failed:")
            for error in errors:
                print(f"  • {error}")
            return

        if config_manager.save_config():
            print("\n✅ Configuration synced and saved successfully!")
        else:
            print("\n❌ Failed to save configuration")

    except Exception as e:
        print(f"❌ Failed to sync configuration: {e}")


def create_template(output_file: str) -> None:
    """Create a configuration template."""
    print(f"📝 Creating configuration template: {output_file}")

    # Create template from default configuration
    config_manager = BackupConfigManager()
    config = config_manager.get_config()

    # Convert to template format
    template_data = {
        "schedule": {
            "backup_time": "02:00",  # Default values
            "cleanup_time": "03:00",
            "cleanup_day": 0,
        },
        "retention": {"daily": 7, "weekly": 4, "monthly": 3, "max_size_gb": 50},
        "backup": {"directory": "backups", "compress": True, "verify": True, "type": "full"},
        "components": {
            "database": True,
            "models": True,
            "config": True,
            "outputs": True,
            "logs": True,
            "docker_volumes": True,
        },
        "docker_volumes": {"volumes": ["postgres_data", "redis_data"], "stop_containers": True},
        "verification": {
            "checksums": True,
            "test_restore": False,
            "critical_patterns": {
                "models": ["*.pkl", "*.joblib", "*.h5", "*.onnx"],
                "config": ["*.yaml", "*.yml", "*.json"],
                "outputs": ["*.csv", "*.json", "*.txt"],
            },
        },
        "logging": {"log_file": "logs/backup.log", "level": "INFO", "rotate": True, "keep_logs": 30},
        "security": {"encrypt": False, "key_file": "backup.key", "file_permissions": "0644", "dir_permissions": "0755"},
        "performance": {"max_threads": 4, "timeout": 300, "progress": True, "chunk_size": 4096},
        "environments": {
            "development": {
                "retention": {"daily": 3, "weekly": 2, "monthly": 1},
                "backup": {"verify": False},
                "logging": {"level": "DEBUG"},
            },
            "production": {
                "retention": {"daily": 7, "weekly": 4, "monthly": 3},
                "backup": {"verify": True},
                "logging": {"level": "INFO"},
                "security": {"encrypt": True},
            },
        },
    }

    try:
        with open(output_file, "w") as f:
            yaml.dump(template_data, f, default_flow_style=False, indent=2)
        print("✅ Configuration template created successfully!")
    except Exception as e:
        print(f"❌ Failed to create template: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTI Scraper Backup Configuration Manager")
    parser.add_argument("--config-file", help="Configuration file path")
    parser.add_argument("--environment", help="Environment name")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show current configuration")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate configuration")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update configuration")
    update_parser.add_argument("--backup-time", help="Backup time (HH:MM)")
    update_parser.add_argument("--cleanup-time", help="Cleanup time (HH:MM)")
    update_parser.add_argument("--daily", type=int, help="Daily retention count")
    update_parser.add_argument("--weekly", type=int, help="Weekly retention count")
    update_parser.add_argument("--monthly", type=int, help="Monthly retention count")
    update_parser.add_argument("--max-size-gb", type=float, help="Maximum size in GB")
    update_parser.add_argument("--backup-dir", help="Backup directory")
    update_parser.add_argument("--compress", type=bool, help="Enable compression")
    update_parser.add_argument("--verify", type=bool, help="Enable verification")
    update_parser.add_argument("--disable-components", nargs="+", help="Disable components")
    update_parser.add_argument("--enable-components", nargs="+", help="Enable components")
    update_parser.add_argument("--max-threads", type=int, help="Maximum threads")
    update_parser.add_argument("--timeout", type=int, help="Timeout in seconds")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export configuration")
    export_parser.add_argument("output_file", help="Output file path")

    # Template command
    template_parser = subparsers.add_parser("template", help="Create configuration template")
    template_parser.add_argument("output_file", help="Output file path")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync configuration with UI settings")
    sync_parser.add_argument("--ui-settings", help="UI settings JSON file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize configuration manager
    config_manager = BackupConfigManager(args.config_file, args.environment)

    # Execute command
    if args.command == "show":
        show_config(config_manager)
    elif args.command == "validate":
        validate_config(config_manager)
    elif args.command == "update":
        update_config(config_manager, args)
    elif args.command == "export":
        export_config(config_manager, args.output_file)
    elif args.command == "template":
        create_template(args.output_file)
    elif args.command == "sync":
        sync_with_ui_settings(config_manager, args.ui_settings)


if __name__ == "__main__":
    main()
