"""Allowlisted backup executor; this is the only runtime granted Docker access."""

from __future__ import annotations

import base64
import hmac
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.utils.input_validation import (
    ValidationError,
    validate_backup_components,
    validate_backup_dir,
    validate_backup_name,
)

app = FastAPI(title="Huntable maintenance")
ROOT = Path("/app")


def _authorize(token: str | None) -> None:
    expected = os.getenv("MAINTENANCE_API_TOKEN", "")
    if not expected or token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


def _run(args: list[str], timeout: int) -> dict[str, object]:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


class CreateRequest(BaseModel):
    compress: bool = True
    verify: bool = True


@app.post("/internal/backup/create")
def create_backup(payload: CreateRequest, x_maintenance_token: str | None = Header(default=None)):
    _authorize(x_maintenance_token)
    args = [sys.executable, str(ROOT / "scripts/backup_system.py")]
    if not payload.compress:
        args.append("--no-compress")
    if not payload.verify:
        args.append("--no-verify")
    return _run(args, 300)


class RestoreRequest(BaseModel):
    backup_name: str
    backup_dir: str
    components: str | None = None
    no_snapshot: bool = False


def _validated_backup_path(backup_name: str, backup_dir: str) -> tuple[str, str, Path]:
    try:
        name = validate_backup_name(backup_name, allow_system_prefix=True)
        directory = validate_backup_dir(backup_dir)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid backup path") from exc
    root = (ROOT / directory).resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid backup path") from exc
    return name, directory, path


@app.post("/internal/backup/restore")
def restore_backup(payload: RestoreRequest, x_maintenance_token: str | None = Header(default=None)):
    _authorize(x_maintenance_token)
    name, directory, path = _validated_backup_path(payload.backup_name, payload.backup_dir)
    try:
        components = validate_backup_components(payload.components)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid components") from exc
    if path.is_dir() and name.startswith("system_backup_"):
        args = [sys.executable, str(ROOT / "scripts/restore_system.py"), name, "--backup-dir", directory]
        if components:
            args.extend(["--components", components])
    else:
        args = [sys.executable, str(ROOT / "scripts/restore_database.py"), str(path)]
    args.append("--force")
    if payload.no_snapshot:
        args.append("--no-snapshot")
    return _run(args, 600)


class RestoreFileRequest(BaseModel):
    content_base64: str
    suffix: str


@app.post("/internal/backup/restore-file")
def restore_file(payload: RestoreFileRequest, x_maintenance_token: str | None = Header(default=None)):
    _authorize(x_maintenance_token)
    if payload.suffix not in {".sql", ".sql.gz"}:
        raise HTTPException(status_code=400, detail="Invalid file type")
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload") from exc
    with tempfile.NamedTemporaryFile(delete=False, suffix=payload.suffix, prefix="restore_") as handle:
        handle.write(content)
        path = Path(handle.name)
    try:
        return _run([sys.executable, str(ROOT / "scripts/restore_database_v2.py"), str(path), "--force"], 600)
    finally:
        path.unlink(missing_ok=True)
