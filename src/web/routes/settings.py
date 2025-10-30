"""
API endpoints for managing application settings.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.database.async_manager import async_db_manager
from src.database.models import AppSettingsTable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingUpdate(BaseModel):
    """Request model for updating a setting."""
    key: str
    value: Optional[str] = None


class SettingsBulkUpdate(BaseModel):
    """Request model for bulk update."""
    settings: Dict[str, Optional[str]]


@router.get("")
async def get_all_settings():
    """Get all application settings."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(AppSettingsTable))
            settings = result.scalars().all()

            return {
                "success": True,
                "settings": {
                    setting.key: setting.value
                    for setting in settings
                }
            }

    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}")
async def get_setting(key: str):
    """Get a specific setting by key."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == key)
            )
            setting = result.scalar_one_or_none()

            if not setting:
                return {
                    "success": True,
                    "key": key,
                    "value": None,
                    "exists": False
                }

            return {
                "success": True,
                "key": setting.key,
                "value": setting.value,
                "description": setting.description,
                "category": setting.category,
                "exists": True
            }

    except Exception as e:
        logger.error(f"Error fetching setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_setting(update: SettingUpdate):
    """Update or create a setting."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select
            from datetime import datetime

            # Check if setting exists
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == update.key)
            )
            setting = result.scalar_one_or_none()

            if setting:
                # Update existing setting
                setting.value = update.value
                setting.updated_at = datetime.now()
                logger.info(f"Updated setting: {update.key} = {update.value}")
            else:
                # Create new setting
                setting = AppSettingsTable(
                    key=update.key,
                    value=update.value,
                    category='user'  # User-created settings
                )
                session.add(setting)
                logger.info(f"Created new setting: {update.key} = {update.value}")

            await session.commit()

            return {
                "success": True,
                "key": update.key,
                "value": update.value,
                "message": "Setting updated successfully"
            }

    except Exception as e:
        logger.error(f"Error updating setting {update.key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk")
async def update_settings_bulk(update: SettingsBulkUpdate):
    """Update multiple settings at once."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select
            from datetime import datetime

            updated_keys = []
            errors = []

            for key, value in update.settings.items():
                try:
                    # Check if setting exists
                    result = await session.execute(
                        select(AppSettingsTable).where(AppSettingsTable.key == key)
                    )
                    setting = result.scalar_one_or_none()

                    if setting:
                        # Update existing
                        setting.value = value
                        setting.updated_at = datetime.now()
                    else:
                        # Create new
                        setting = AppSettingsTable(
                            key=key,
                            value=value,
                            category='user'
                        )
                        session.add(setting)

                    updated_keys.append(key)

                except Exception as e:
                    logger.error(f"Error updating setting {key}: {e}")
                    errors.append(f"{key}: {str(e)}")

            await session.commit()

            logger.info(f"Bulk update completed: {len(updated_keys)} settings updated")

            return {
                "success": len(errors) == 0,
                "updated_keys": updated_keys,
                "errors": errors,
                "message": f"Updated {len(updated_keys)} settings"
            }

    except Exception as e:
        logger.error(f"Error in bulk update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{key}")
async def delete_setting(key: str):
    """Delete a setting (revert to environment variable)."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select, delete

            # Check if setting exists
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == key)
            )
            setting = result.scalar_one_or_none()

            if not setting:
                raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

            # Delete the setting
            await session.execute(
                delete(AppSettingsTable).where(AppSettingsTable.key == key)
            )
            await session.commit()

            logger.info(f"Deleted setting: {key}")

            return {
                "success": True,
                "key": key,
                "message": "Setting deleted successfully (will revert to environment variable)"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting setting {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
