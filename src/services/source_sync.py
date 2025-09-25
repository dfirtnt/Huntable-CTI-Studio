"""Source synchronization service.

Loads YAML definitions and synchronizes the database accordingly.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from src.core.source_manager import SourceConfigLoader
from src.models.source import Source, SourceCreate, SourceUpdate
from src.database.async_manager import AsyncDatabaseManager

logger = logging.getLogger(__name__)


class SourceSyncService:
    """Synchronize sources from YAML configuration into the database."""

    def __init__(
        self,
        config_path: Path,
        db_manager: AsyncDatabaseManager,
    ) -> None:
        self.config_path = config_path
        self.db_manager = db_manager
        self.loader = SourceConfigLoader()

    async def sync(self, validate_feeds: bool = False, remove_missing: bool = True) -> int:
        """Run synchronization and return number of synced sources."""

        source_configs = self.loader.load_from_file(str(self.config_path))
        logger.info("Loaded %d source configs", len(source_configs))

        synced_sources = await self._sync_to_db(source_configs, remove_missing)

        logger.info("Synchronization complete: %d sources", len(synced_sources))
        return len(synced_sources)

    async def _sync_to_db(
        self,
        source_configs: List[SourceCreate],
        remove_missing: bool,
    ) -> List[Source]:
        existing_sources = await self.db_manager.list_sources()
        existing_by_identifier = {src.identifier: src for src in existing_sources}

        synced_sources: List[Source] = []

        for config in source_configs:
            identifier = config.identifier
            existing = existing_by_identifier.get(identifier)

            if existing:
                update_data = SourceUpdate(
                    name=config.name,
                    url=config.url,
                    rss_url=config.rss_url,
                    check_frequency=config.check_frequency,
                    lookback_days=config.lookback_days,
                    active=config.active,
                    tier=config.tier,
                    weight=config.weight,
                    config=config.config,
                )

                synced = await self.db_manager.update_source(existing.id, update_data)
                if synced:
                    synced_sources.append(synced)
                else:
                    synced_sources.append(existing)
            else:
                synced = await self.db_manager.create_source(config)
                if synced:
                    synced_sources.append(synced)

        if remove_missing:
            valid_identifiers = {cfg.identifier for cfg in source_configs}
            for existing in existing_sources:
                if existing.identifier not in valid_identifiers:
                    await self.db_manager.delete_source(existing.id)

        return synced_sources


async def sync_sources(config_path: str, db_manager: AsyncDatabaseManager) -> int:
    service = SourceSyncService(Path(config_path), db_manager)
    return await service.sync()


def sync_sources_blocking(config_path: str, db_manager: AsyncDatabaseManager) -> int:
    return asyncio.run(sync_sources(config_path, db_manager))

