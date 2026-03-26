"""Periodic coordinator that scans for sources needing AI healing and dispatches tasks."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import SourceTable
from src.services.source_healing_config import SourceHealingConfig

logger = logging.getLogger(__name__)

# Don't heal sources that succeeded recently — short failure streaks after
# a recent success are likely transient (container restart, network blip),
# not config problems that the healing LLM should rewrite.
_RECENT_SUCCESS_GRACE_PERIOD = timedelta(hours=24)


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

    now = datetime.now()
    for source in sources:
        # Skip sources with a recent last_success — they likely have a transient
        # issue (container restart, dependency unavailable) not a config problem.
        if source.last_success and (now - source.last_success) < _RECENT_SUCCESS_GRACE_PERIOD:
            logger.info(
                "[AutoHeal] Skipping source '%s' (id=%s) — last success %s is within %s grace period",
                source.name, source.id, source.last_success, _RECENT_SUCCESS_GRACE_PERIOD,
            )
            continue

        logger.info(
            "[AutoHeal] Dispatching heal task for source '%s' (id=%s), failures=%d",
            source.name, source.id, source.consecutive_failures,
        )
        try:
            heal_source.delay(source.id)
        except Exception:
            logger.exception("[AutoHeal] Failed to dispatch heal task for source %s", source.id)
