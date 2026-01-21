"""
Backup management API routes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from src.web.dependencies import logger

router = APIRouter(prefix="/api/backup", tags=["Backup"])


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

        raise HTTPException(status_code=500, detail=f"Backup failed: {result.stderr}")

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Backup timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup creation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
            raise HTTPException(
                status_code=500, detail=f"Failed to list backups: {result.stderr}"
            )

        backups: List[Dict[str, Any]] = []
        lines = result.stdout.split("\n")
        in_backup_list = False

        for index, line in enumerate(lines):
            if "Recent Backups" in line:
                in_backup_list = True
                continue
            if in_backup_list and line.strip() and any(
                line.strip().startswith(f"{i}.") for i in range(1, 11)
            ):
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
async def api_backup_status():
    """API endpoint for retrieving backup status and summary."""
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
            raise HTTPException(
                status_code=500, detail=f"Failed to get backup status: {result.stderr}"
            )

        automated = False
        total_backups = 0
        total_size_gb = 0.0
        last_backup = None

        lines = result.stdout.split("\n")
        for line in lines:
            if "Automated backups" in line:
                automated = "enabled" in line.lower()
            if "Total backups" in line:
                try:
                    total_backups = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    total_backups = 0
            if "Total backup size" in line:
                size_str = line.split(":")[1].strip()
                if "GB" in size_str and "(" in size_str:
                    import re

                    match = re.search(r"\(([0-9.]+)\\s*GB\\)", size_str)
                    if match:
                        total_size_gb = float(match.group(1))
                elif "MB" in size_str:
                    try:
                        total_size_gb = float(size_str.split()[0].replace("MB", "")) / 1024
                    except ValueError:
                        total_size_gb = 0.0
            if "Recent Backups" in line:
                for next_line in lines[lines.index(line) + 1 :]:
                    if next_line.strip() and next_line.strip().startswith("1."):
                        parts = next_line.strip().split(".", 1)
                        if len(parts) >= 2:
                            last_backup = parts[1].strip()
                        break

        return {
            "automated": automated,
            "total_backups": total_backups,
            "total_size_gb": total_size_gb,
            "last_backup": last_backup,
        }

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Status check timed out") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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

        project_root = Path(__file__).parent.parent.parent.parent
        
        # Determine which restore script to use
        backup_path = Path(backup_name)
        if not backup_path.is_absolute():
            backup_path = Path(backup_dir) / backup_name
        
        # Check if it's a system backup directory
        if backup_path.is_dir() and backup_name.startswith('system_backup_'):
            script_path = project_root / 'scripts' / 'restore_system.py'
            if not script_path.exists():
                raise HTTPException(status_code=500, detail="System restore script not found")
            
            cmd = [sys.executable, str(script_path), backup_name, '--backup-dir', backup_dir]
            
            if components:
                cmd.extend(['--components', components])
            # Always pass --force when called from API to skip interactive confirmation
            # (user already confirmed in UI). Note: --force also skips snapshot creation.
            cmd.append('--force')
            # If user explicitly wants to skip snapshot, add --no-snapshot
            # (though --force already prevents snapshot, this is for clarity)
            if no_snapshot:
                cmd.append('--no-snapshot')
        else:
            # Use legacy database restore script
            script_path = project_root / 'scripts' / 'restore_database.py'
            if not script_path.exists():
                raise HTTPException(status_code=500, detail="Database restore script not found")
            
            cmd = [sys.executable, str(script_path), str(backup_path)]
            
            # Always pass --force when called from API to skip interactive confirmation
            cmd.append('--force')
            if no_snapshot:
                cmd.append('--no-snapshot')

        result = subprocess.run(
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

        raise HTTPException(
            status_code=500, detail=f"Restore failed: {result.stderr or result.stdout}"
        )

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="Restore timed out") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Restore error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

