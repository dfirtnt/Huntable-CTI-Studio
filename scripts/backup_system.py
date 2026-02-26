#!/usr/bin/env python3
"""
Comprehensive System Backup Script for CTI Scraper

This script creates complete system backups including:
- Database (PostgreSQL dump)
- ML models and training data
- Configuration files
- Docker volumes
- Generated content and outputs

Features:
- Parallel backup execution
- Integrity checksums (SHA256)
- Component validation
- Size reporting
- Respects .gitignore patterns
- Configurable via YAML configuration
"""

import concurrent.futures
import fnmatch
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

try:
    from utils.backup_config import get_backup_config, get_backup_config_manager
except ImportError:
    # Fallback if config module not available
    def get_backup_config():
        return None

    def get_backup_config_manager():
        return None


# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "database": "cti_scraper",
    "user": "cti_user",
    "password": "cti_password",
}

# Docker volume names (matching docker-compose.yml)
# Note: Docker volume backup disabled in containerized environment for security
DOCKER_VOLUMES = []

# Critical file patterns to validate
CRITICAL_PATTERNS = {
    "models": ["*.pkl", "*.joblib", "*.h5", "*.onnx"],
    "config": ["*.yaml", "*.yml", "*.json"],
    "outputs": ["*.csv", "*.json", "*.txt"],
}


def get_docker_exec_cmd(container_name: str, command: str) -> list:
    """Generate docker exec command for running commands in container."""
    return ["docker", "exec", container_name, "bash", "-c", command]


def check_docker_container(container_name: str) -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={container_name}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return container_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def check_docker_volume(volume_name: str) -> bool:
    """Check if Docker volume exists."""
    try:
        result = subprocess.run(
            [
                "docker",
                "volume",
                "ls",
                "--filter",
                f"name={volume_name}",
                "--format",
                "{{.Name}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return volume_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Warning: Could not calculate checksum for {file_path}: {e}")
        return ""


def get_gitignore_patterns() -> list[str]:
    """Read .gitignore patterns."""
    gitignore_path = Path(".gitignore")
    patterns = []

    if gitignore_path.exists():
        try:
            with open(gitignore_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception as e:
            print(f"Warning: Could not read .gitignore: {e}")

    return patterns


def should_ignore_path(path: Path, ignore_patterns: list[str]) -> bool:
    """Check if path should be ignored based on .gitignore patterns."""
    path_str = str(path)

    for pattern in ignore_patterns:
        # Handle directory patterns
        if pattern.endswith("/"):
            if fnmatch.fnmatch(path_str, pattern.rstrip("/")) or fnmatch.fnmatch(path_str, pattern + "*"):
                return True
        # Handle file patterns
        elif fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(path_str, pattern):
            return True

    return False


def validate_critical_files(directory: Path, patterns: list[str]) -> tuple[list[Path], list[str]]:
    """Validate critical files exist and are readable."""
    valid_files = []
    errors = []

    if not directory.exists():
        return valid_files, [f"Directory does not exist: {directory}"]

    for pattern in patterns:
        matching_files = list(directory.glob(pattern))
        if not matching_files:
            errors.append(f"No files found matching pattern '{pattern}' in {directory}")
        else:
            for file_path in matching_files:
                if file_path.is_file() and file_path.stat().st_size > 0:
                    valid_files.append(file_path)
                else:
                    errors.append(f"Invalid or empty file: {file_path}")

    return valid_files, errors


def backup_database(backup_dir: Path, compress: bool = True) -> dict[str, Any]:
    """Backup PostgreSQL database using existing backup_database_v3.py logic."""
    print("🗄️  Backing up database...")

    # Import and use existing database backup logic
    try:
        # Add scripts directory to path to import backup_database_v3
        scripts_path = Path(__file__).parent
        sys.path.insert(0, str(scripts_path))

        # Import the existing backup function
        from backup_database_v3 import create_backup, get_database_stats

        # Use existing backup logic with specified backup directory
        backup_result = create_backup(str(backup_dir))

        if not backup_result or not backup_result.get("success"):
            # Preserve original error if available
            error_msg = "Database backup failed using existing backup logic"
            if backup_result and "error" in backup_result:
                error_msg = f"{error_msg}: {backup_result['error']}"
            raise RuntimeError(error_msg)

        # Get backup info from the result
        backup_filename = backup_result["metadata"]["backup_filename"]
        source_path = Path(backup_result["backup_path"])
        dest_path = backup_dir / backup_filename

        # Validate backup file exists and is not empty before moving
        if not source_path.exists():
            raise RuntimeError(f"Database backup file not found at {source_path}")

        file_size = source_path.stat().st_size
        if file_size == 0:
            # Clean up empty backup file
            if source_path.exists():
                source_path.unlink()
            raise RuntimeError(f"Database backup file is empty at {source_path}")

        # Verify backup contains valid SQL content
        try:
            with open(source_path) as f:
                first_line = f.readline().strip()
                content_sample = f.read(1000)

            if not (
                first_line.startswith("-- PostgreSQL database dump")
                or first_line.startswith("--")
                or "CREATE" in content_sample
                or "COPY" in content_sample
                or "INSERT" in content_sample
            ):
                # Clean up invalid backup file
                if source_path.exists():
                    source_path.unlink()
                raise RuntimeError("Database backup file does not contain valid SQL content")
        except Exception as e:
            # Clean up on validation error
            if source_path.exists():
                source_path.unlink()
            raise RuntimeError(f"Error validating database backup content: {e}") from e

        # File has been validated, safe to move
        shutil.move(str(source_path), str(dest_path))
        backup_filepath = dest_path

        # Also move metadata file if it exists
        source_metadata = Path(backup_result["metadata_path"])
        if source_metadata.exists():
            metadata_filename = backup_filename.replace(".sql", ".json")
            dest_metadata = backup_dir / metadata_filename
            shutil.move(str(source_metadata), str(dest_metadata))

        # Get database size for metadata
        stats = get_database_stats()
        db_size = "Unknown"
        if stats:
            db_size = f"{stats['articles']} articles, {stats['sources']} sources"

        # Compress if requested
        if compress:
            compressed_filename = f"{backup_filename}.gz"
            compressed_filepath = backup_dir / compressed_filename

            with open(backup_filepath, "rb") as f_in, gzip.open(compressed_filepath, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            backup_filepath.unlink()
            backup_filepath = compressed_filepath
            backup_filename = compressed_filename

        # Calculate checksum
        checksum = calculate_checksum(backup_filepath)
        file_size = backup_filepath.stat().st_size

        return {
            "filename": backup_filename,
            "filepath": str(backup_filepath),
            "size_mb": file_size / (1024 * 1024),
            "checksum": checksum,
            "database_size": db_size,
            "compressed": compress,
        }

    except Exception as e:
        # Clean up partial backup if it exists
        if "backup_filepath" in locals() and backup_filepath.exists():
            backup_filepath.unlink()
        # Preserve original error message instead of nesting
        if "Database backup failed" in str(e):
            raise  # Re-raise to avoid double-wrapping
        raise RuntimeError(f"Database backup failed: {e}") from e


def backup_directory(
    source_dir: Path,
    backup_dir: Path,
    component_name: str,
    ignore_patterns: list[str],
    respect_gitignore: bool = True,
    always_include_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Backup a directory with optional .gitignore respect."""
    print(f"📁 Backing up {component_name}...")

    if not source_dir.exists():
        return {
            "component": component_name,
            "source_dir": str(source_dir),
            "backup_dir": str(backup_dir),
            "files": 0,
            "size_mb": 0.0,
            "errors": [f"Source directory does not exist: {source_dir}"],
        }

    backup_component_dir = backup_dir / component_name
    backup_component_dir.mkdir(exist_ok=True)

    files_copied = 0
    total_size = 0
    errors = []
    always_include_paths = always_include_paths or []

    def is_always_included(path: Path) -> bool:
        for include_root in always_include_paths:
            try:
                path.relative_to(include_root)
                return True
            except ValueError:
                continue
        return False

    try:
        # Walk through source directory
        for root, dirs, files in os.walk(source_dir):
            root_path = Path(root)

            # Filter out ignored directories (if respecting .gitignore)
            if respect_gitignore:
                dirs[:] = [
                    d
                    for d in dirs
                    if is_always_included(root_path / d) or not should_ignore_path(root_path / d, ignore_patterns)
                ]

            for file in files:
                file_path = root_path / file

                # Skip ignored files (if respecting .gitignore)
                if (
                    respect_gitignore
                    and not is_always_included(file_path)
                    and should_ignore_path(file_path, ignore_patterns)
                ):
                    continue

                # Calculate relative path for backup
                rel_path = file_path.relative_to(source_dir)
                backup_file_path = backup_component_dir / rel_path

                # Create parent directories
                backup_file_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    # Copy file
                    shutil.copy2(file_path, backup_file_path)
                    files_copied += 1
                    total_size += file_path.stat().st_size

                except Exception as e:
                    errors.append(f"Failed to copy {file_path}: {e}")

        return {
            "component": component_name,
            "source_dir": str(source_dir),
            "backup_dir": str(backup_component_dir),
            "files": files_copied,
            "size_mb": total_size / (1024 * 1024),
            "errors": errors,
        }

    except Exception as e:
        return {
            "component": component_name,
            "source_dir": str(source_dir),
            "backup_dir": str(backup_component_dir),
            "files": files_copied,
            "size_mb": total_size / (1024 * 1024),
            "errors": errors + [f"Directory backup failed: {e}"],
        }


def backup_docker_volume(volume_name: str, backup_dir: Path) -> dict[str, Any]:
    """Backup a Docker volume to tar.gz."""
    print(f"🐳 Backing up Docker volume: {volume_name}")

    if not check_docker_volume(volume_name):
        return {
            "volume": volume_name,
            "filename": None,
            "size_mb": 0.0,
            "errors": [f"Docker volume '{volume_name}' does not exist"],
        }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{volume_name}_{timestamp}.tar.gz"
    backup_filepath = backup_dir / backup_filename

    try:
        # Create volume backup using docker run
        backup_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/data",
            "-v",
            f"{backup_dir.absolute()}:/backup",
            "alpine",
            "tar",
            "czf",
            f"/backup/{backup_filename}",
            "-C",
            "/data",
            ".",
        ]

        subprocess.run(backup_cmd, capture_output=True, text=True, check=True)

        if not backup_filepath.exists():
            raise RuntimeError("Volume backup file was not created")

        # Calculate checksum and size
        checksum = calculate_checksum(backup_filepath)
        file_size = backup_filepath.stat().st_size

        return {
            "volume": volume_name,
            "filename": backup_filename,
            "filepath": str(backup_filepath),
            "size_mb": file_size / (1024 * 1024),
            "checksum": checksum,
            "errors": [],
        }

    except subprocess.CalledProcessError as e:
        # Clean up partial backup
        if backup_filepath.exists():
            backup_filepath.unlink()
        return {
            "volume": volume_name,
            "filename": None,
            "size_mb": 0.0,
            "errors": [f"Volume backup failed: {e.stderr}"],
        }
    except Exception as e:
        return {
            "volume": volume_name,
            "filename": None,
            "size_mb": 0.0,
            "errors": [f"Volume backup failed: {e}"],
        }


def create_system_backup(
    backup_dir: str | None = None,
    compress: bool | None = None,
    verify: bool | None = None,
) -> str:
    """Create a comprehensive system backup."""

    # Load configuration
    config = get_backup_config()
    if config:
        backup_dir = backup_dir or config.backup_dir
        compress = compress if compress is not None else config.compress
        verify = verify if verify is not None else config.verify
    else:
        backup_dir = backup_dir or "backups"
        compress = compress if compress is not None else True
        verify = verify if verify is not None else True

    # Create backup directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"system_backup_{timestamp}"
    backup_path = Path(backup_dir) / backup_name
    backup_path.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Creating comprehensive system backup: {backup_name}")
    print(f"📁 Backup location: {backup_path}")

    # Get ignore patterns
    ignore_patterns = get_gitignore_patterns()

    # Initialize results
    backup_results = {
        "timestamp": datetime.now().isoformat(),
        "version": "2.0",
        "backup_name": backup_name,
        "backup_path": str(backup_path),
        "components": {},
    }

    # Define backup components based on configuration
    if config:
        components = {
            "models": config.models,
            "config": config.config,
            "outputs": config.outputs,
            "logs": config.logs,
        }
        backup_components = [(name, Path(name)) for name, enabled in components.items() if enabled]
    else:
        backup_components = [
            ("models", Path("models")),
            ("config", Path("config")),
            ("outputs", Path("outputs")),
            ("logs", Path("logs")),
        ]

    try:
        # Start parallel backup execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # Submit database backup (separate process)
            db_future = executor.submit(backup_database, backup_path, compress)

            # Submit directory backups
            dir_futures = {}
            for component_name, source_dir in backup_components:
                # Models should be backed up even if in .gitignore
                respect_gitignore = component_name != "models"
                # Private workflow presets are intentionally gitignored but should be included in backups.
                always_include_paths = []
                if component_name == "config":
                    always_include_paths.append(source_dir / "presets" / "private")
                future = executor.submit(
                    backup_directory,
                    source_dir,
                    backup_path,
                    component_name,
                    ignore_patterns,
                    respect_gitignore,
                    always_include_paths,
                )
                dir_futures[component_name] = future

            # Submit Docker volume backups
            volume_futures = {}
            volumes_to_backup = config.volume_list if config and config.docker_volumes else DOCKER_VOLUMES
            for volume_name in volumes_to_backup:
                future = executor.submit(backup_docker_volume, volume_name, backup_path)
                volume_futures[volume_name] = future

            # Collect results
            print("⏳ Waiting for backup components to complete...")

            # Database backup
            try:
                db_result = db_future.result(timeout=300)  # 5 minute timeout
                backup_results["components"]["database"] = db_result
                print(f"✅ Database backup completed: {db_result['size_mb']:.2f} MB")
            except Exception as e:
                backup_results["components"]["database"] = {"errors": [f"Database backup failed: {e}"]}
                print(f"❌ Database backup failed: {e}")

            # Directory backups
            for component_name, future in dir_futures.items():
                try:
                    result = future.result(timeout=120)  # 2 minute timeout
                    backup_results["components"][component_name] = result
                    if result["errors"]:
                        print(f"⚠️  {component_name} backup completed with errors: {len(result['errors'])} errors")
                    else:
                        print(
                            f"✅ {component_name} backup completed: {result['files']} files, {result['size_mb']:.2f} MB"
                        )
                except Exception as e:
                    backup_results["components"][component_name] = {"errors": [f"{component_name} backup failed: {e}"]}
                    print(f"❌ {component_name} backup failed: {e}")

            # Docker volume backups
            for volume_name, future in volume_futures.items():
                try:
                    result = future.result(timeout=300)  # 5 minute timeout
                    backup_results["components"][f"docker_volume_{volume_name}"] = result
                    if result["errors"]:
                        print(f"⚠️  {volume_name} volume backup completed with errors: {result['errors']}")
                    else:
                        print(f"✅ {volume_name} volume backup completed: {result['size_mb']:.2f} MB")
                except Exception as e:
                    backup_results["components"][f"docker_volume_{volume_name}"] = {
                        "errors": [f"{volume_name} volume backup failed: {e}"]
                    }
                    print(f"❌ {volume_name} volume backup failed: {e}")

        # Validate critical files if requested
        if verify:
            print("🔍 Validating critical files...")
            validation_errors = []

            # Use configured critical patterns or defaults
            critical_patterns = config.critical_patterns if config else CRITICAL_PATTERNS

            for component, patterns in critical_patterns.items():
                if component in backup_results["components"]:
                    component_path = Path(backup_results["components"][component].get("backup_dir", ""))
                    if component_path.exists():
                        valid_files, errors = validate_critical_files(component_path, patterns)
                        if errors:
                            validation_errors.extend([f"{component}: {error}" for error in errors])

            if validation_errors:
                backup_results["validation_errors"] = validation_errors
                print(f"⚠️  Validation completed with {len(validation_errors)} warnings")
            else:
                print("✅ All critical files validated successfully")

        # Create metadata file
        metadata_filepath = backup_path / "metadata.json"
        with open(metadata_filepath, "w") as f:
            json.dump(backup_results, f, indent=2)

        # Calculate total backup size
        total_size = 0
        for component_data in backup_results["components"].values():
            if isinstance(component_data, dict) and "size_mb" in component_data:
                total_size += component_data["size_mb"]

        backup_results["total_size_mb"] = total_size

        print("\n🎉 System backup completed successfully!")
        print(f"   📁 Location: {backup_path}")
        print(f"   📊 Total size: {total_size:.2f} MB")
        print(f"   📋 Metadata: {metadata_filepath}")

        return str(backup_path)

    except Exception as e:
        print(f"❌ System backup failed: {e}")
        # Clean up partial backup
        if backup_path.exists():
            shutil.rmtree(backup_path)
        raise


def list_system_backups(backup_dir: str = "backups") -> None:
    """List available system backups."""
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        print("📁 No backup directory found.")
        return

    # Find system backup directories
    system_backups = [d for d in backup_path.iterdir() if d.is_dir() and d.name.startswith("system_backup_")]

    if not system_backups:
        print("📁 No system backups found.")
        return

    print("📋 Available system backups:")
    print("-" * 100)

    for backup_dir in sorted(system_backups, reverse=True):
        metadata_file = backup_dir / "metadata.json"

        print(f"📄 {backup_dir.name}")

        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)

                timestamp = metadata.get("timestamp", "Unknown")
                total_size = metadata.get("total_size_mb", 0)
                components = metadata.get("components", {})

                print(f"   📅 Created: {timestamp}")
                print(f"   📊 Total size: {total_size:.2f} MB")
                print(f"   🧩 Components: {len(components)}")

                # Show component summary
                for comp_name, comp_data in components.items():
                    if isinstance(comp_data, dict):
                        if "size_mb" in comp_data:
                            print(f"      • {comp_name}: {comp_data['size_mb']:.2f} MB")
                        elif "errors" in comp_data:
                            print(f"      • {comp_name}: ❌ Failed")

            except Exception as e:
                print(f"   ⚠️  Could not read metadata: {e}")
        else:
            print("   ⚠️  No metadata file found")

        print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CTI Scraper Comprehensive System Backup Tool")
    parser.add_argument("--backup-dir", default="backups", help="Backup directory (default: backups)")
    parser.add_argument("--no-compress", action="store_true", help="Skip compression")
    parser.add_argument("--no-verify", action="store_true", help="Skip file validation")
    parser.add_argument("--list", action="store_true", help="List available system backups")

    args = parser.parse_args()

    if args.list:
        list_system_backups(args.backup_dir)
    else:
        create_system_backup(
            backup_dir=args.backup_dir,
            compress=not args.no_compress,
            verify=not args.no_verify,
        )


if __name__ == "__main__":
    main()
