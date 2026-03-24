"""Periodic coordinator that scans for sources needing AI healing and dispatches tasks."""

import logging

from sqlalchemy import select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import SourceTable
from src.services.source_healing_config import SourceHealingConfig

logger = logging.getLogger(__name__)


async def scan_and_trigger_healing() -> None:
    """Find all sources above the failure threshold and dispatch healing tasks.

    Called by the check_sources_for_healing Celery beat task on a configurable
    schedule. For each qualifying source (active, above threshold, not exhausted),
    dispatches a single heal_source task. The service handles multi-round retries
    internally.
    """
    config = SourceHealingConfig.load()

    if not config.enabled:
        logger.debug("[AutoHeal] Auto-healing is disabled, skipping scan")
        return

    db = AsyncDatabaseManager()
    try:
        async with db.get_session() as session:
            result = await session.execute(
                select(SourceTable).where(
                    SourceTable.consecutive_failures >= config.threshold,
                    SourceTable.active == True,  # noqa: E712
                    SourceTable.healing_exhausted == False,  # noqa: E712
                )
            )
            sources = result.scalars().all()
    except Exception:
        logger.exception("[AutoHeal] Failed to query sources for healing scan")
        return

    if not sources:
        logger.debug("[AutoHeal] No sources above threshold (%d), nothing to heal", config.threshold)
        return

    logger.info(
        "[AutoHeal] Found %d source(s) with consecutive_failures >= %d",
        len(sources), config.threshold,
    )

    from src.worker.celery_app import heal_source

    for source in sources:
        logger.info(
            "[AutoHeal] Dispatching heal task for source '%s' (id=%s), failures=%d",
            source.name, source.id, source.consecutive_failures,
        )
        try:
            heal_source.delay(source.id)
        except Exception:
            logger.exception("[AutoHeal] Failed to dispatch heal task for source %s", source.id)
