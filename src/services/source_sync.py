"""Source synchronization service.

Loads YAML definitions and synchronizes the database accordingly.
"""

import logging
from pathlib import Path

from src.core.source_manager import SourceConfigLoader
from src.database.async_manager import AsyncDatabaseManager
from src.models.source import Source, SourceCreate, SourceUpdate

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
        source_configs: list[SourceCreate],
        remove_missing: bool,
    ) -> list[Source]:
        existing_sources = await self.db_manager.list_sources()
        existing_by_identifier = {src.identifier: src for src in existing_sources}

        synced_sources: list[Source] = []

        for config in source_configs:
            identifier = config.identifier
            existing = existing_by_identifier.get(identifier)

            if existing:
                # Extract config: SourceConfig model has inner 'config' dict
                if hasattr(config.config, "config"):
                    # SourceConfig Pydantic model: extract inner config dict
                    config_dict = config.config.config if isinstance(config.config.config, dict) else {}
                elif isinstance(config.config, dict):
                    # Already a dict
                    config_dict = config.config
                else:
                    config_dict = {}

                # SourceUpdate.config expects a SourceConfig model, not a dict
                # Create SourceConfig with the inner config dict properly set
                # Use check_frequency and lookback_days from the SourceCreate's config model
                from src.models.source import SourceConfig

                check_freq = config.config.check_frequency if hasattr(config.config, "check_frequency") else 3600
                lookback = config.config.lookback_days if hasattr(config.config, "lookback_days") else 180
                source_config_model = SourceConfig(
                    check_frequency=check_freq, lookback_days=lookback, config=config_dict
                )

                update_data = SourceUpdate(
                    name=config.name,
                    url=config.url,
                    rss_url=config.rss_url,
                    active=config.active,
                    config=source_config_model,
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
    """
    Synchronous wrapper for sync_sources.

    WARNING: Do not call this from within a running event loop.
    Use sync_sources() directly with await in async contexts.
    """
    from src.utils.async_tools import run_sync

    return run_sync(sync_sources(config_path, db_manager))
