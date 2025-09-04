"""CLI context and configuration management."""

import os
from typing import Optional
from pathlib import Path

from database.manager import DatabaseManager
from core.source_manager import SourceManager
from utils.http import HTTPClient


class CLIContext:
    """Global CLI context for managing shared resources."""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://cti_user:cti_password_2024@postgres:5432/cti_scraper')
        self.config_file = os.getenv('SOURCES_CONFIG', 'config/sources.yaml')
        self.debug = False
        self.db_manager: Optional[DatabaseManager] = None
        self.http_client: Optional[HTTPClient] = None
        self.source_manager: Optional[SourceManager] = None


async def get_managers(ctx: CLIContext):
    """Initialize and return manager instances."""
    if not ctx.db_manager:
        ctx.db_manager = DatabaseManager(ctx.database_url)
    
    if not ctx.http_client:
        ctx.http_client = HTTPClient()
    
    if not ctx.source_manager:
        ctx.source_manager = SourceManager(ctx.db_manager, ctx.http_client)
    
    return ctx.db_manager, ctx.http_client, ctx.source_manager


def setup_logging(debug: bool = False):
    """Setup logging configuration."""
    import logging
    
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
