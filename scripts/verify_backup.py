#!/usr/bin/env python3
"""
Backup Integrity Verification Script for CTI Scraper

This script verifies backup integrity:
- Validate backup structure and metadata
- Check file checksums
- Test restore to temporary database
- Report missing or corrupted components

Features:
- Comprehensive integrity checks
- Checksum validation
- Database restore testing
- Component validation
- Detailed reporting
"""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "database": "cti_scraper",
    "user": "cti_user",
    "password": "cti_password",
}


def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        raise RuntimeError(f"Could not calculate checksum for {file_path}: {e}") from e


def get_docker_exec_cmd(container_name: str, command: str) -> list:
    """Generate docker exec command for running commands in container."""
    return ["docker", "exec", container_name, "bash", "-c", command]


def check_docker_container(container_name: str) -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return container_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def validate_backup_structure(backup_path: Path) -> dict[str, Any]:
    """Validate backup directory structure."""
    print("🔍 Validating backup structure...")

    validation_result = {"valid": True, "errors": [], "warnings": [], "backup_type": "unknown", "version": "1.0"}

    if not backup_path.exists():
        validation_result["valid"] = False
        validation_result["errors"].append(f"Backup path does not exist: {backup_path}")
        return validation_result

    if not backup_path.is_dir():
        # Legacy single-file backup
        if backup_path.is_file() and backup_path.name.startswith("cti_scraper_backup_"):
            validation_result["backup_type"] = "legacy_database"
            validation_result["version"] = "1.0"
            return validation_result
        validation_result["valid"] = False
        validation_result["errors"].append(f"Backup path is not a directory or recognized file: {backup_path}")
        return validation_result

    # System backup (v2.0)
    if backup_path.name.startswith("system_backup_"):
        validation_result["backup_type"] = "system"

        # Check for metadata file
        metadata_file = backup_path / "metadata.json"
        if not metadata_file.exists():
            validation_result["valid"] = False
            validation_result["errors"].append("No metadata.json file found")
            return validation_result

        try:
            with open(metadata_file) as f:
                metadata = json.load(f)

            validation_result["version"] = metadata.get("version", "2.0")
            validation_result["metadata"] = metadata

            # Check for expected components
            components = metadata.get("components", {})
            expected_components = ["database", "models", "config", "outputs"]

            for component in expected_components:
                if component not in components:
                    validation_result["warnings"].append(f"Component '{component}' not found in backup")

            # Check component directories exist
            for component_name in components.keys():
                if component_name.startswith("docker_volume_"):
                    # Docker volume backups are files, not directories
                    volume_name = component_name.replace("docker_volume_", "")
                    volume_files = list(backup_path.glob(f"{volume_name}_*.tar.gz"))
                    if not volume_files:
                        validation_result["warnings"].append(f"No backup file found for volume {volume_name}")
                else:
                    # Regular directory components
                    component_dir = backup_path / component_name
                    if not component_dir.exists():
                        validation_result["warnings"].append(f"Component directory '{component_name}' not found")

        except Exception as e:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Invalid metadata file: {e}")

    else:
        validation_result["valid"] = False
        validation_result["errors"].append(f"Unknown backup type: {backup_path.name}")

    return validation_result


def validate_file_checksums(backup_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate file checksums against metadata."""
    print("🔍 Validating file checksums...")

    checksum_result = {"valid": True, "errors": [], "warnings": [], "files_checked": 0, "files_valid": 0}

    components = metadata.get("components", {})

    for component_name, component_data in components.items():
        if not isinstance(component_data, dict):
            continue

        # Check database backup checksum
        if component_name == "database" and "checksum" in component_data:
            db_filename = component_data.get("filename", "")
            if db_filename:
                db_file = backup_path / db_filename
                if db_file.exists():
                    try:
                        actual_checksum = calculate_checksum(db_file)
                        expected_checksum = component_data["checksum"]

                        checksum_result["files_checked"] += 1

                        if actual_checksum == expected_checksum:
                            checksum_result["files_valid"] += 1
                        else:
                            checksum_result["valid"] = False
                            checksum_result["errors"].append(
                                f"Database backup checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
                            )
                    except Exception as e:
                        checksum_result["valid"] = False
                        checksum_result["errors"].append(f"Could not verify database checksum: {e}")
                else:
                    checksum_result["warnings"].append(f"Database backup file not found: {db_filename}")

        # Check Docker volume backup checksums
        elif component_name.startswith("docker_volume_") and "checksum" in component_data:
            volume_filename = component_data.get("filename", "")
            if volume_filename:
                volume_file = backup_path / volume_filename
                if volume_file.exists():
                    try:
                        actual_checksum = calculate_checksum(volume_file)
                        expected_checksum = component_data["checksum"]

                        checksum_result["files_checked"] += 1

                        if actual_checksum == expected_checksum:
                            checksum_result["files_valid"] += 1
                        else:
                            checksum_result["valid"] = False
                            checksum_result["errors"].append(
                                f"Volume {component_name} checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
                            )
                    except Exception as e:
                        checksum_result["valid"] = False
                        checksum_result["errors"].append(f"Could not verify {component_name} checksum: {e}")
                else:
                    checksum_result["warnings"].append(f"Volume backup file not found: {volume_filename}")

    return checksum_result


def test_database_restore(backup_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Test database restore to temporary database."""
    print("🔍 Testing database restore...")

    restore_result = {"valid": True, "errors": [], "warnings": [], "test_database": None}

    # Check if PostgreSQL container is running
    if not check_docker_container("cti_postgres"):
        restore_result["valid"] = False
        restore_result["errors"].append("PostgreSQL container 'cti_postgres' is not running")
        return restore_result

    # Get database backup info
    db_info = metadata.get("components", {}).get("database", {})
    if not db_info:
        restore_result["warnings"].append("No database backup found in metadata")
        return restore_result

    db_filename = db_info.get("filename", "")
    if not db_filename:
        restore_result["warnings"].append("No database backup filename in metadata")
        return restore_result

    db_backup_file = backup_path / db_filename
    if not db_backup_file.exists():
        restore_result["valid"] = False
        restore_result["errors"].append(f"Database backup file not found: {db_backup_file}")
        return restore_result

    # Create temporary test database
    test_db_name = f"cti_scraper_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    restore_result["test_database"] = test_db_name

    try:
        # Create test database
        create_cmd = get_docker_exec_cmd(
            "cti_postgres", f"psql -U {DB_CONFIG['user']} -c 'CREATE DATABASE {test_db_name};'"
        )
        subprocess.run(create_cmd, check=True, capture_output=True)

        # Create temporary file for SQL content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as temp_file:
            temp_path = temp_file.name

            # Extract SQL content
            if db_filename.endswith(".gz"):
                with gzip.open(db_backup_file, "rt") as f_in:
                    shutil.copyfileobj(f_in, temp_file)
            else:
                with open(db_backup_file) as f_in:
                    shutil.copyfileobj(f_in, temp_file)

        # Copy SQL file to container
        copy_cmd = ["docker", "cp", temp_path, "cti_postgres:/tmp/test_restore.sql"]
        subprocess.run(copy_cmd, check=True)

        # Restore to test database
        restore_cmd = get_docker_exec_cmd(
            "cti_postgres", f"psql -U {DB_CONFIG['user']} -d {test_db_name} -f /tmp/test_restore.sql"
        )

        result = subprocess.run(restore_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            restore_result["valid"] = False
            restore_result["errors"].append(f"Database restore test failed: {result.stderr}")
        else:
            # Verify restore by checking table count
            verify_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f"psql -U {DB_CONFIG['user']} -d {test_db_name} -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" -t",
            )
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True, check=True)
            table_count = verify_result.stdout.strip()

            if int(table_count) > 0:
                restore_result["warnings"].append(f"Database restore test successful: {table_count} tables restored")
            else:
                restore_result["warnings"].append("Database restore test completed but no tables found")

        # Clean up
        os.unlink(temp_path)
        cleanup_cmd = get_docker_exec_cmd("cti_postgres", "rm -f /tmp/test_restore.sql")
        subprocess.run(cleanup_cmd)

    except subprocess.CalledProcessError as e:
        restore_result["valid"] = False
        restore_result["errors"].append(f"Database restore test failed: {e}")
    except Exception as e:
        restore_result["valid"] = False
        restore_result["errors"].append(f"Unexpected error during database restore test: {e}")
    finally:
        # Clean up test database
        try:
            if restore_result["test_database"]:
                drop_cmd = get_docker_exec_cmd(
                    "cti_postgres",
                    f"psql -U {DB_CONFIG['user']} -c 'DROP DATABASE IF EXISTS {restore_result['test_database']};'",
                )
                subprocess.run(drop_cmd, capture_output=True)
        except (subprocess.SubprocessError, KeyError):
            pass

    return restore_result


def validate_critical_files(backup_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate critical files exist and are readable."""
    print("🔍 Validating critical files...")

    validation_result = {"valid": True, "errors": [], "warnings": [], "files_checked": 0, "files_valid": 0}

    # Critical file patterns
    critical_patterns = {
        "models": ["*.pkl", "*.joblib", "*.h5", "*.onnx"],
        "config": ["*.yaml", "*.yml", "*.json"],
        "outputs": ["*.csv", "*.json", "*.txt"],
    }

    components = metadata.get("components", {})

    for component_name, patterns in critical_patterns.items():
        if component_name in components:
            component_dir = backup_path / component_name
            if component_dir.exists():
                for pattern in patterns:
                    matching_files = list(component_dir.glob(pattern))
                    validation_result["files_checked"] += len(matching_files)

                    for file_path in matching_files:
                        if file_path.is_file() and file_path.stat().st_size > 0:
                            validation_result["files_valid"] += 1
                        else:
                            validation_result["warnings"].append(f"Invalid or empty file: {file_path}")
            else:
                validation_result["warnings"].append(f"Component directory not found: {component_name}")

    return validation_result


def verify_backup(backup_name: str, backup_dir: str = "backups", test_restore: bool = False) -> dict[str, Any]:
    """Verify backup integrity."""

    # Parse backup name
    if backup_name.startswith("system_backup_"):
        backup_path = Path(backup_dir) / backup_name
    else:
        backup_path = Path(backup_name)
        if not backup_path.is_absolute():
            backup_path = Path(backup_dir) / backup_name

    print(f"🔍 Verifying backup: {backup_path}")

    verification_result = {
        "backup_path": str(backup_path),
        "backup_name": backup_path.name,
        "overall_valid": True,
        "timestamp": datetime.now().isoformat(),
        "tests": {},
    }

    try:
        # 1. Validate backup structure
        structure_result = validate_backup_structure(backup_path)
        verification_result["tests"]["structure"] = structure_result

        if not structure_result["valid"]:
            verification_result["overall_valid"] = False
            return verification_result

        # 2. Validate file checksums (if metadata available)
        if structure_result.get("metadata"):
            metadata = structure_result["metadata"]
            checksum_result = validate_file_checksums(backup_path, metadata)
            verification_result["tests"]["checksums"] = checksum_result

            if not checksum_result["valid"]:
                verification_result["overall_valid"] = False

        # 3. Test database restore (if requested and database backup exists)
        if test_restore and structure_result.get("metadata"):
            metadata = structure_result["metadata"]
            if "database" in metadata.get("components", {}):
                restore_result = test_database_restore(backup_path, metadata)
                verification_result["tests"]["database_restore"] = restore_result

                if not restore_result["valid"]:
                    verification_result["overall_valid"] = False

        # 4. Validate critical files
        if structure_result.get("metadata"):
            metadata = structure_result["metadata"]
            files_result = validate_critical_files(backup_path, metadata)
            verification_result["tests"]["critical_files"] = files_result

    except Exception as e:
        verification_result["overall_valid"] = False
        verification_result["error"] = str(e)

    return verification_result


def print_verification_report(result: dict[str, Any]) -> None:
    """Print detailed verification report."""
    print("\n" + "=" * 80)
    print("📋 BACKUP VERIFICATION REPORT")
    print("=" * 80)

    print(f"Backup: {result['backup_name']}")
    print(f"Path: {result['backup_path']}")
    print(f"Timestamp: {result['timestamp']}")
    print(f"Overall Status: {'✅ VALID' if result['overall_valid'] else '❌ INVALID'}")

    # Structure validation
    if "structure" in result["tests"]:
        structure = result["tests"]["structure"]
        print(f"\n🏗️  Structure Validation: {'✅ PASS' if structure['valid'] else '❌ FAIL'}")
        print(f"   Backup Type: {structure['backup_type']}")
        print(f"   Version: {structure['version']}")

        if structure["errors"]:
            print("   Errors:")
            for error in structure["errors"]:
                print(f"     ❌ {error}")

        if structure["warnings"]:
            print("   Warnings:")
            for warning in structure["warnings"]:
                print(f"     ⚠️  {warning}")

    # Checksum validation
    if "checksums" in result["tests"]:
        checksums = result["tests"]["checksums"]
        print(f"\n🔐 Checksum Validation: {'✅ PASS' if checksums['valid'] else '❌ FAIL'}")
        print(f"   Files Checked: {checksums['files_checked']}")
        print(f"   Files Valid: {checksums['files_valid']}")

        if checksums["errors"]:
            print("   Errors:")
            for error in checksums["errors"]:
                print(f"     ❌ {error}")

        if checksums["warnings"]:
            print("   Warnings:")
            for warning in checksums["warnings"]:
                print(f"     ⚠️  {warning}")

    # Database restore test
    if "database_restore" in result["tests"]:
        restore = result["tests"]["database_restore"]
        print(f"\n🗄️  Database Restore Test: {'✅ PASS' if restore['valid'] else '❌ FAIL'}")

        if restore["errors"]:
            print("   Errors:")
            for error in restore["errors"]:
                print(f"     ❌ {error}")

        if restore["warnings"]:
            print("   Warnings:")
            for warning in restore["warnings"]:
                print(f"     ⚠️  {warning}")

    # Critical files validation
    if "critical_files" in result["tests"]:
        files = result["tests"]["critical_files"]
        print(f"\n📁 Critical Files Validation: {'✅ PASS' if files['valid'] else '❌ FAIL'}")
        print(f"   Files Checked: {files['files_checked']}")
        print(f"   Files Valid: {files['files_valid']}")

        if files["errors"]:
            print("   Errors:")
            for error in files["errors"]:
                print(f"     ❌ {error}")

        if files["warnings"]:
            print("   Warnings:")
            for warning in files["warnings"]:
                print(f"     ⚠️  {warning}")

    # Overall summary
    print("\n📊 SUMMARY")
    print("-" * 40)

    if result["overall_valid"]:
        print("✅ Backup is valid and ready for restore")
    else:
        print("❌ Backup has issues that should be addressed before restore")

    if "error" in result:
        print(f"❌ Verification failed: {result['error']}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTI Scraper Backup Integrity Verification")
    parser.add_argument("backup_name", nargs="?", help="Backup name or path to verify")
    parser.add_argument("--backup-dir", default="backups", help="Backup directory (default: backups)")
    parser.add_argument("--test-restore", action="store_true", help="Test database restore to temporary database")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    if not args.backup_name:
        print("❌ Please specify a backup name to verify.")
        sys.exit(1)

    # Verify backup
    result = verify_backup(backup_name=args.backup_name, backup_dir=args.backup_dir, test_restore=args.test_restore)

    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_verification_report(result)

    # Exit with error if backup is invalid
    if not result["overall_valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
