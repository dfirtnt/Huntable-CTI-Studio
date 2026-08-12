"""Client for the internal, allowlisted maintenance service."""

from __future__ import annotations

import os
from typing import Any

import httpx


class MaintenanceServiceError(RuntimeError):
    """Raised when an internal maintenance operation cannot be completed."""


async def run_backup_operation(operation: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    """Run one of the service's fixed backup operations; never forward a command."""
    base_url = os.getenv("MAINTENANCE_API_URL", "http://maintenance:8002").rstrip("/")
    token = os.getenv("MAINTENANCE_API_TOKEN", "")
    if not token:
        raise MaintenanceServiceError("Maintenance service token is not configured.")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/internal/backup/{operation}",
                json=payload,
                headers={"X-Maintenance-Token": token},
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise MaintenanceServiceError("Maintenance returned an invalid response.")
            return data
    except httpx.HTTPError as exc:
        raise MaintenanceServiceError("Maintenance operation failed.") from exc
