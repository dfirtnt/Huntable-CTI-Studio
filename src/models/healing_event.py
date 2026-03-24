"""Pydantic models for healing event audit trail."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealingEventCreate(BaseModel):
    """Data for recording a healing event."""

    source_id: int
    round_number: int
    diagnosis: str
    actions_proposed: list[dict[str, Any]]
    actions_applied: list[dict[str, Any]]
    validation_success: bool | None = None
    error_message: str | None = None


class HealingEvent(BaseModel):
    """Complete healing event model."""

    id: int
    source_id: int
    round_number: int
    diagnosis: str
    actions_proposed: list[dict[str, Any]]
    actions_applied: list[dict[str, Any]]
    validation_success: bool | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
