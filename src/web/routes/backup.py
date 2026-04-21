"""
Backup management API routes.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from src.services.backup_cron_service import BackupCronService, CronCommandError, CronUnavailableError
from src.utils.backup_config import BackupConfigManager, get_backup_config_manager
from src.utils.input_validation import ValidationError, validate_backup_components, validate_backup_dir, validate_backup_name
from src.web.dependencies import logger

router = APIRouter(prefix="/api/backup", tags=["Backup"])


class BackupCronUpdate(BaseModel):
    """Request model for saving backup config and optionally applying cron."""

    backup_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    cleanup_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    daily: int = Field(ge=0)
    weekly: int = Field(ge=0)
    monthly: int = Field(ge=0)
    max_size_gb: int = Field(gt=0)
    backup_dir: str = "backups"
    backup_type: str = Field(default="full", pattern=r"^(full|database|files)$")
    compress: bool = True
    verify: bool = True
    database: bool = True
    models: bool = True
    config: bool = True
    outputs: bool = True
    logs: bool = True
    docker_volumes: bool = True
    install_crontab: bool = False


def _sync_backup_config(manager: BackupConfigManager, payload: BackupCronUpdate):
    """Apply UI payload to the backup config manager."""
    config = manager.get_config()
    config.backup_time = payload.backup_time
    config.cleanup_time = payload.cleanup_time
    config.daily = payload.daily
    config.weekly = payload.weekly
    config.monthly = payload.monthly
    config.max_size_gb = payload.max_size_gb
    config.backup_dir = payload.backup_dir
    config.backup_type = payload.backup_type
    config.compress = payload.compress
    config.verify = payload.verify
    config.database = payload.database
    config.models = payload.models
    config.config = payload.config
    config.outputs = payload.outputs
    config.logs = payload.logs
    config.docker_volumes = payload.docker_volumes
    return config


def _get_cron_state() -> dict[str, Any]:
    """Return current backup cron state and config."""
    manager = get_backup_config_manager()
    service = BackupCronService()
    return service.get_state(manager.get_config())


@router.post("/create")
async def api_create_backup(request: Request):
    """API endpoint for creating a backup."""
    try:
        payload = await request.json()
        compress = payload.get("compress", True)
        verify = payload.get("verify", True)

        project_root = Path(__file__).parent.parent.parent.parent
        cmd = [sys.executable, str(project_root / "scripts" / "backup_system.py")]

        if not compress:
            cmd.append("--no-compress")
        if not verify:
            cmd.append("--no-verify")

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if result.returncode == 0:
            backup_name = None
            for line in result.stdout.strip().split("\n"):
                if "Creating comprehensive system backup:" in line:
                    backup_name = line.split(":")[-1].strip()
                    break

            return {
                "success": True,
                "backup_name": backup_name or "unknown",
                "message": "Backup created successfully",
            }

        raise HTTPException(status_code=500, detail="Internal server error")

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Backup timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup creation error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/list")
async def api_list_backups():
    """API endpoint for listing backups."""
    try:
        project_root = Path(__file__).parent.parent.parent.parent

        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "prune_backups.py"), "--stats"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="Internal server error")

        backups: list[dict[str, Any]] = []
        lines = result.stdout.split("\n")
        in_backup_list = False

        for index, line in enumerate(lines):
            if "Recent Backups" in line:
                in_backup_list = True
                continue
            if in_backup_list and line.strip() and any(line.strip().startswith(f"{i}.") for i in range(1, 11)):
                parts = line.strip().split(".", 1)
                if len(parts) < 2:
                    continue
                backup_name = parts[1].strip()

                size_mb = 0.0
                for lookahead in range(index + 1, min(index + 4, len(lines))):
                    next_line = lines[lookahead]
                    if "📊" in next_line and "MB" in next_line:
                        for token in next_line.split():
                            try:
                                size_mb = float(token.replace("MB", ""))
                                break
                            except ValueError:
                                continue
                        break

                backups.append({"name": backup_name, "size_mb": size_mb})

        return backups

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="List backups timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup list error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/cron")
async def api_get_backup_cron():
    """Return current CTI-managed backup cron state and all visible cron jobs."""
    try:
        state = _get_cron_state()
        return {"success": True, **state}
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup cron state error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/cron")
async def api_update_backup_cron(payload: BackupCronUpdate):
    """Save backup config and optionally install/update CTI-managed cron jobs."""
    try:
        manager = get_backup_config_manager()
        config = _sync_backup_config(manager, payload)
        errors = manager.validate_config()
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        if not manager.save_config():
            raise HTTPException(status_code=500, detail="Failed to save backup config")

        service = BackupCronService()
        state = service.get_state(config)
        if payload.install_crontab:
            state = service.install_backup_schedule(config)

        return {
            "success": True,
            "config_saved": True,
            "crontab_applied": payload.install_crontab,
            **state,
        }
    except CronUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup cron update error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete("/cron")
async def api_delete_backup_cron():
    """Disable CTI-managed backup cron jobs while preserving other crontab entries."""
    try:
        manager = get_backup_config_manager()
        service = BackupCronService()
        state = service.remove_backup_schedule(manager.get_config())
        return {"success": True, **state}
    except CronUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup cron delete error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/status")
async def api_backup_status():
    """API endpoint for retrieving backup status and summary."""
    try:
        project_root = Path(__file__).parent.parent.parent.parent

        cron_state = _get_cron_state()

        # Get backup statistics
        result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "prune_backups.py"), "--stats"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail="Internal server error")

        total_backups = 0
        total_size_gb = 0.0
        last_backup = None

        lines = result.stdout.split("\n")
        for line in lines:
            if "Total backups:" in line:
                try:
                    total_backups = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    total_backups = 0
            if "Total size:" in line:
                size_str = line.split(":")[1].strip()
                # Try to extract GB value from format like "1168.26 MB (1.14 GB)"
                import re

                # Look for GB value in parentheses first
                gb_match = re.search(r"\(([0-9.]+)\s*GB\)", size_str)
                if gb_match:
                    total_size_gb = float(gb_match.group(1))
                # Otherwise, convert MB to GB
                elif "MB" in size_str:
                    try:
                        mb_match = re.search(r"([0-9.]+)\s*MB", size_str)
                        if mb_match:
                            total_size_gb = float(mb_match.group(1)) / 1024
                        else:
                            # Fallback: try to extract first number
                            total_size_gb = float(size_str.split()[0].replace("MB", "")) / 1024
                    except (ValueError, IndexError):
                        total_size_gb = 0.0
            if "Recent Backups" in line:
                # Find the first backup entry (starts with number and dot, may have leading spaces)
                for next_line in lines[lines.index(line) + 1 :]:
                    stripped = next_line.strip()
                    # Match lines like " 1. backup_name" or "1. backup_name"
                    if stripped and re.match(r"^\d+\.", stripped):
                        parts = stripped.split(".", 1)
                        if len(parts) >= 2:
                            last_backup = parts[1].strip()
                        break

        return {
            "automated": cron_state["automated"],
            "cron_available": cron_state["cron_available"],
            "managed_jobs": cron_state["managed_jobs"],
            "total_backups": total_backups,
            "total_size_gb": total_size_gb,
            "last_backup": last_backup,
        }

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Status check timed out") from exc
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup status error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/restore")
async def api_restore_backup(request: Request):
    """API endpoint for restoring from a backup."""
    try:
        payload = await request.json()
        backup_name = payload.get("backup_name")
        if not backup_name:
            raise HTTPException(status_code=400, detail="backup_name is required")

        backup_dir = payload.get("backup_dir", "backups")
        components = payload.get("components")
        force = payload.get("force", False)
        no_snapshot = payload.get("no_snapshot", False)

        # SECURITY: Validate all user inputs to prevent command injection and path traversal
        try:
            backup_name = validate_backup_name(backup_name, allow_system_prefix=True)
            backup_dir = validate_backup_dir(backup_dir)
            components = validate_backup_components(components)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=f"Invalid input: {e}") from e

        project_root = Path(__file__).parent.parent.parent.parent

        # Determine which restore script to use
        backup_path = Path(backup_name)
        if not backup_path.is_absolute():
            backup_path = Path(backup_dir) / backup_name

        # SECURITY: Verify backup_path is within backup_dir (prevent path traversal)
        try:
            backup_path_resolved = backup_path.resolve()
            backup_dir_resolved = (project_root / backup_dir).resolve()
            backup_path_resolved.relative_to(backup_dir_resolved)
        except (ValueError, OSError) as e:
            raise HTTPException(status_code=400, detail="Invalid backup path") from e

        # Check if it's a system backup directory
        if backup_path.is_dir() and backup_name.startswith("system_backup_"):
            script_path = project_root / "scripts" / "restore_system.py"
            if not script_path.exists():
                raise HTTPException(status_code=500, detail="System restore script not found")

            cmd = [sys.executable, str(script_path), backup_name, "--backup-dir", backup_dir]

            if components:
                cmd.extend(["--components", components])
            # Always pass --force when called from API to skip interactive confirmation
            # (user already confirmed in UI). Note: --force also skips snapshot creation.
            cmd.append("--force")
            # If user explicitly wants to skip snapshot, add --no-snapshot
            # (though --force already prevents snapshot, this is for clarity)
            if no_snapshot:
                cmd.append("--no-snapshot")
        else:
            # Use legacy database restore script
            script_path = project_root / "scripts" / "restore_database.py"
            if not script_path.exists():
                raise HTTPException(status_code=500, detail="Database restore script not found")

            cmd = [sys.executable, str(script_path), str(backup_path)]

            # Always pass --force when called from API to skip interactive confirmation
            cmd.append("--force")
            if no_snapshot:
                cmd.append("--no-snapshot")

        result = subprocess.run(  # nosemgrep
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,  # Restore can take longer
            check=False,
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "Restore completed successfully",
                "output": result.stdout,
            }

        raise HTTPException(status_code=500, detail="Internal server error")

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Restore timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Restore error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# Allowed backup file extensions for restore-from-file
RESTORE_FILE_SUFFIXES = (".sql", ".sql.gz")


@router.post("/restore-from-file")
async def api_restore_from_file(file: UploadFile = File(..., description="Backup file (.sql or .sql.gz)")):
    """Restore database from an uploaded backup file."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix == ".gz":
        # e.g. backup.sql.gz
        base = Path(file.filename or "").stem
        suffix = Path(base).suffix.lower() + ".gz"
    if suffix not in RESTORE_FILE_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(RESTORE_FILE_SUFFIXES)}",
        )

    project_root = Path(__file__).parent.parent.parent.parent
    script_path = project_root / "scripts" / "restore_database_v2.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="Restore script not found")

    tmp_path: Path | None = None
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="restore_") as f:
            f.write(content)
            tmp_path = Path(f.name)

        cmd = [sys.executable, str(script_path), str(tmp_path), "--force"]
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

        if result.returncode == 0:
            return {
                "success": True,
                "message": "Restore from file completed successfully",
                "output": result.stdout,
            }
        raise HTTPException(
            status_code=500,
            detail=result.stderr.strip() or result.stdout.strip() or "Restore failed",
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Restore timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Restore from file error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError as e:
                logger.warning("Could not remove temp restore file %s: %s", tmp_path, e)
