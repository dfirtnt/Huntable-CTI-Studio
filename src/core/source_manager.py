"""Source configuration management system."""

import os
import asyncio
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import yaml
import logging

from src.models.source import Source, SourceCreate, SourceConfig
from dataclasses import dataclass
from src.database.manager import DatabaseManager
from src.utils.http import HTTPClient
from src.core.rss_parser import FeedValidator

logger = logging.getLogger(__name__)


@dataclass
class SourceConfig:
    """Configuration for source management."""
    check_frequency: int = 3600
    lookback_days: int = 180
    min_content_length: int = 100
    max_content_length: int = 50000
    min_title_length: int = 10
    max_title_length: int = 200
    max_age_days: int = 365
    quality_threshold: float = 0.5
    cost_threshold: float = 0.1
    enable_rss: bool = True
    enable_scraping: bool = True
    rate_limit_delay: float = 1.0
    max_retries: int = 3
    timeout: int = 30
    
    def validate(self) -> bool:
        """Validate configuration parameters."""
        return (
            self.check_frequency > 0 and
            self.lookback_days > 0 and
            self.min_content_length > 0 and
            self.max_content_length > self.min_content_length and
            self.min_title_length > 0 and
            self.max_title_length > self.min_title_length and
            self.max_age_days > 0 and
            0.0 <= self.quality_threshold <= 1.0 and
            0.0 <= self.cost_threshold <= 1.0 and
            self.rate_limit_delay > 0 and
            self.max_retries > 0 and
            self.timeout > 0
        )
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            'check_frequency': self.check_frequency,
            'lookback_days': self.lookback_days,
            'min_content_length': self.min_content_length,
            'max_content_length': self.max_content_length,
            'min_title_length': self.min_title_length,
            'max_title_length': self.max_title_length,
            'max_age_days': self.max_age_days,
            'quality_threshold': self.quality_threshold,
            'cost_threshold': self.cost_threshold,
            'enable_rss': self.enable_rss,
            'enable_scraping': self.enable_scraping,
            'rate_limit_delay': self.rate_limit_delay,
            'max_retries': self.max_retries,
            'timeout': self.timeout
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SourceConfig':
        """Create config from dictionary."""
        return cls(**data)


class SourceConfigLoader:
    """Loader for YAML source configurations."""
    
    def __init__(self):
        self.supported_versions = ['1.0']
    
    def load_config(self, file_path: str) -> SourceConfig:
        """Load configuration from file."""
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            return SourceConfig.from_dict(data)
        except FileNotFoundError:
            # Return default config if file doesn't exist
            return SourceConfig()
        except Exception as e:
            logger.error(f"Error loading config from {file_path}: {e}")
            return SourceConfig()
    
    def save_config(self, config: SourceConfig, file_path: str):
        """Save configuration to file."""
        try:
            with open(file_path, 'w') as f:
                yaml.dump(config.to_dict(), f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Error saving config to {file_path}: {e}")
    
    def load_config_from_dict(self, data: Dict) -> SourceConfig:
        """Load configuration from dictionary."""
        return SourceConfig.from_dict(data)
    
    def load_from_file(self, config_path: str) -> List[SourceCreate]:
        """
        Load source configurations from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            List of SourceCreate objects
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config format is invalid
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            return self._parse_config(config_data)
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load configuration: {e}")
    
    def load_from_directory(self, config_dir: str) -> List[SourceCreate]:
        """
        Load source configurations from directory of YAML files.
        
        Args:
            config_dir: Directory containing YAML files
            
        Returns:
            List of SourceCreate objects
        """
        if not os.path.exists(config_dir):
            raise FileNotFoundError(f"Configuration directory not found: {config_dir}")
        
        sources = []
        config_files = Path(config_dir).glob("*.yaml") or Path(config_dir).glob("*.yml")
        
        for config_file in config_files:
            try:
                file_sources = self.load_from_file(str(config_file))
                sources.extend(file_sources)
                logger.info(f"Loaded {len(file_sources)} sources from {config_file.name}")
            except Exception as e:
                logger.error(f"Failed to load {config_file}: {e}")
                continue
        
        return sources
    
    def _parse_config(self, config_data: Dict[str, Any]) -> List[SourceCreate]:
        """Parse configuration data into SourceCreate objects."""
        # Validate config structure
        if not isinstance(config_data, dict):
            raise ValueError("Configuration must be a dictionary")
        
        # Check version
        version = config_data.get('version', '1.0')
        if version not in self.supported_versions:
            raise ValueError(f"Unsupported configuration version: {version}")
        
        # Get sources list
        sources_data = config_data.get('sources', [])
        if not isinstance(sources_data, list):
            raise ValueError("'sources' must be a list")
        
        sources = []
        seen_identifiers = set()
        
        for i, source_data in enumerate(sources_data):
            try:
                source = self._parse_source(source_data)
                
                # Check for duplicate identifiers
                if source.identifier in seen_identifiers:
                    raise ValueError(f"Duplicate source identifier: {source.identifier}")
                
                seen_identifiers.add(source.identifier)
                sources.append(source)
                
            except Exception as e:
                logger.error(f"Failed to parse source {i}: {e}")
                continue
        
        return sources
    
    def _parse_source(self, source_data: Dict[str, Any]) -> SourceCreate:
        """Parse individual source configuration."""
        required_fields = ['id', 'name', 'url']
        
        # Check required fields
        for field in required_fields:
            if field not in source_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Parse basic fields
        identifier = source_data['id']
        name = source_data['name']
        url = source_data['url']
        rss_url = source_data.get('rss_url', '')
        check_frequency = source_data.get('check_frequency', 3600)
        lookback_days = source_data.get('lookback_days', 180)
        active = source_data.get('active', True)
        
        # Parse configuration (prefer unified "config" structure, fall back to legacy fields)
        config_dict = source_data.get('config')

        if config_dict is None:
            config_dict = {}
            scope = source_data.get('scope', {})
            if scope:
                config_dict['allow'] = scope.get('allow', [])
                config_dict['post_url_regex'] = scope.get('post_url_regex', [])

            if 'discovery' in source_data:
                config_dict['discovery'] = source_data['discovery']

            if 'extract' in source_data:
                config_dict['extract'] = source_data['extract']

            if 'content_selector' in source_data:
                config_dict['content_selector'] = source_data['content_selector']

        # Config should be passed as SourceConfig model with inner config dict
        # SourceConfig expects: check_frequency, lookback_days, and inner 'config' dict
        from src.models.source import SourceConfig
        source_config = SourceConfig(
            check_frequency=check_frequency,
            lookback_days=lookback_days,
            config=config_dict or {}
        )
        
        return SourceCreate(
            identifier=identifier,
            name=name,
            url=url,
            rss_url=rss_url if rss_url else None,
            check_frequency=check_frequency,
            lookback_days=lookback_days,
            active=active,
            config=source_config
        )


class SourceManager:
    """Manager for source configurations and database synchronization."""
    
    def __init__(self, database_manager: Optional[DatabaseManager] = None, http_client: Optional[HTTPClient] = None):
        self.db = database_manager
        self.http_client = http_client
        self.config_loader = SourceConfigLoader()
        self.feed_validator = FeedValidator() if http_client else None
        
        # In-memory storage for testing
        self._sources = {}
        self._source_configs = {}
    
    async def load_sources_from_config(
        self,
        config_path: str,
        sync_to_db: bool = True,
        validate_feeds: bool = True,
        remove_missing: bool = True
    ) -> List[Source]:
        """
        Load sources from configuration file and optionally sync to database.
        
        Args:
            config_path: Path to configuration file or directory
            sync_to_db: Whether to synchronize with database
            validate_feeds: Whether to validate RSS feeds
            
        Returns:
            List of Source objects
        """
        logger.info(f"Loading sources from: {config_path}")
        
        # Load configuration
        if os.path.isdir(config_path):
            source_configs = self.config_loader.load_from_directory(config_path)
        else:
            source_configs = self.config_loader.load_from_file(config_path)
        
        logger.info(f"Loaded {len(source_configs)} source configurations")
        
        # Validate feeds if requested
        if validate_feeds:
            source_configs = await self._validate_source_feeds(source_configs)
        
        # Configure robots.txt settings for each source
        await self._configure_robots_settings(source_configs)
        
        # Sync to database if requested
        if sync_to_db:
            return await self._sync_sources_to_db(source_configs, remove_missing=remove_missing)
        else:
            # Convert to Source objects (without IDs)
            sources = [config.to_source() for config in source_configs]
            await self._configure_robots_settings(source_configs)
            return sources
    
    async def _validate_source_feeds(self, source_configs: List[SourceCreate]) -> List[SourceCreate]:
        """Validate RSS feeds for sources that have them."""
        validated_configs = []
        
        for config in source_configs:
            if config.rss_url:
                try:
                    logger.debug(f"Validating RSS feed for {config.identifier}")
                    
                    validation_result = await self.feed_validator.validate_feed(
                        config.rss_url, self.http_client
                    )
                    
                    if validation_result['valid']:
                        logger.info(f"RSS feed valid for {config.identifier}: {validation_result['entry_count']} entries")
                        validated_configs.append(config)
                    else:
                        logger.warning(f"RSS feed invalid for {config.identifier}: {validation_result['errors']}")
                        # Keep source but disable RSS
                        config.rss_url = None
                        validated_configs.append(config)
                        
                except Exception as e:
                    logger.error(f"RSS validation failed for {config.identifier}: {e}")
                    # Keep source but disable RSS
                    config.rss_url = None
                    validated_configs.append(config)
                
                # Rate limiting between validations
                await asyncio.sleep(1)
            else:
                validated_configs.append(config)
        
        return validated_configs
    
    async def _configure_robots_settings(self, source_configs: List[SourceCreate]):
        """Configure robots.txt settings for each source."""
        for config in source_configs:
            if hasattr(config.config, 'robots') and config.config.robots:
                robots_config = config.config.robots
                robots_payload = robots_config.model_dump(exclude_none=True)
                self.http_client.configure_source_robots(config.identifier, robots_payload)
                logger.debug(f"Configured robots.txt settings for {config.identifier}")
    
    async def _sync_sources_to_db(
        self,
        source_configs: List[SourceCreate],
        remove_missing: bool = True
    ) -> List[Source]:
        """Synchronize source configurations with database."""
        logger.info(f"Synchronizing {len(source_configs)} sources to database")

        synced_sources = []

        # Map configs by identifier for quick access
        config_map = {config.identifier: config for config in source_configs}

        # Existing sources from database
        existing_sources = await self.db.list_sources()
        existing_by_identifier = {src.identifier: src for src in existing_sources}

        # Create or update sources present in config
        for identifier, config in config_map.items():
            try:
                existing_source = existing_by_identifier.get(identifier)

                if existing_source:
                    from src.models.source import SourceUpdate

                    updated_source = await self.db.update_source(existing_source.id, SourceUpdate(
                        name=config.name,
                        url=config.url,
                        rss_url=config.rss_url,
                        check_frequency=config.check_frequency,
                        lookback_days=config.lookback_days,
                        active=config.active,
                        config=config.config.model_dump(exclude_none=True) if config.config else {}
                    ))
                    if updated_source:
                        synced_sources.append(updated_source)
                        logger.info(f"Updated source: {identifier}")

                else:
                    new_source = await self.db.create_source(config)
                    if new_source:
                        synced_sources.append(new_source)
                        logger.info(f"Created source: {identifier}")

            except Exception as e:
                logger.error(f"Failed to sync source {identifier}: {e}")
                continue

        # Remove sources missing from configuration
        if remove_missing:
            config_identifiers = set(config_map.keys())
            for existing in existing_sources:
                if existing.identifier not in config_identifiers:
                    try:
                        await self.db.delete_source(existing.id)
                        logger.info(f"Removed source not in config: {existing.identifier}")
                    except Exception as e:
                        logger.error(f"Failed to remove source {existing.identifier}: {e}")

        logger.info(f"Synchronized {len(synced_sources)} sources to database")
        return synced_sources
    
    def get_sources_due_for_check(self, force_all: bool = False) -> List[Source]:
        """Get sources that are due for checking."""
        from ..models.source import SourceFilter
        
        if force_all:
            filter_params = SourceFilter(active=True)
        else:
            # Get sources that haven't been checked recently
            filter_params = SourceFilter(active=True)
        
        sources = self.db.list_sources(filter_params)
        
        if force_all:
            return sources
        else:
            return [source for source in sources if source.should_check()]
    
    def auto_discover_sources(self, base_url: str) -> Dict[str, Any]:
        """
        Auto-discover potential sources from a base URL.
        
        Args:
            base_url: Base URL to discover from
            
        Returns:
            Dictionary with discovery results
        """
        # This is a placeholder for future implementation
        # Could include:
        # - RSS feed discovery via <link> tags
        # - Sitemap.xml parsing
        # - Common blog/news URL patterns
        # - Security vendor pattern recognition
        
        return {
            'base_url': base_url,
            'discovered_feeds': [],
            'potential_sources': [],
            'errors': ['Auto-discovery not yet implemented']
        }
    
    def export_sources_config(
        self,
        output_path: str,
        source_ids: Optional[List[int]] = None,
        include_inactive: bool = False
    ) -> bool:
        """
        Export sources to YAML configuration file.
        
        Args:
            output_path: Output file path
            source_ids: Optional list of specific source IDs to export
            include_inactive: Whether to include inactive sources
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from models.source import SourceFilter
            
            # Get sources to export
            if source_ids:
                sources = [self.db.get_source(sid) for sid in source_ids if self.db.get_source(sid)]
            else:
                filter_params = SourceFilter(active=True) if not include_inactive else None
                sources = self.db.list_sources(filter_params)
            
            if not sources:
                logger.warning("No sources to export")
                return False
            
            # Build configuration structure
            config_data = {
                'version': '1.0',
                'sources': []
            }
            
            for source in sources:
                source_config = {
                    'id': source.identifier,
                    'name': source.name,
                    'url': source.url,
                    'check_frequency': source.check_frequency,
                    'active': source.active
                }
                
                # Add RSS URL if present
                if source.rss_url:
                    source_config['rss_url'] = source.rss_url
                
                # Add configuration sections if present
                if source.config.allow:
                    source_config.setdefault('scope', {})['allow'] = source.config.allow
                
                if source.config.post_url_regex:
                    source_config.setdefault('scope', {})['post_url_regex'] = source.config.post_url_regex
                
                if source.config.discovery:
                    source_config['discovery'] = source.config.discovery
                
                if source.config.extract:
                    source_config['extract'] = source.config.extract
                
                if source.config.content_selector:
                    source_config['content_selector'] = source.config.content_selector
                
                config_data['sources'].append(source_config)
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
            
            logger.info(f"Exported {len(sources)} sources to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export sources config: {e}")
            return False
    
    def validate_source_config(self, config_path: str) -> Dict[str, Any]:
        """
        Validate source configuration file without loading to database.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Dictionary with validation results
        """
        result = {
            'valid': False,
            'sources_count': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            # Load and parse configuration
            if os.path.isdir(config_path):
                source_configs = self.config_loader.load_from_directory(config_path)
            else:
                source_configs = self.config_loader.load_from_file(config_path)
            
            result['sources_count'] = len(source_configs)
            
            # Validate each source
            identifiers = set()
            for i, config in enumerate(source_configs):
                # Check for duplicate identifiers
                if config.identifier in identifiers:
                    result['errors'].append(f"Duplicate identifier '{config.identifier}' at source {i}")
                else:
                    identifiers.add(config.identifier)
                
                # Validate check frequency
                if config.check_frequency < 60:
                    result['warnings'].append(f"Source '{config.identifier}': Check frequency {config.check_frequency}s is very aggressive")
                
                # Validate RSS URL if present
                if config.rss_url:
                    if not config.rss_url.startswith(('http://', 'https://')):
                        result['errors'].append(f"Source '{config.identifier}': Invalid RSS URL format")
            
            # Set valid if no errors
            result['valid'] = len(result['errors']) == 0
            
        except Exception as e:
            result['errors'].append(f"Configuration loading failed: {e}")
        
        return result
    
    def add_source(self, source_data: Dict) -> 'Source':
        """Add a new source."""
        if not self.validate_source_data(source_data):
            raise ValueError("Invalid source data")
        
        identifier = source_data['identifier']
        if identifier in self._sources:
            raise ValueError(f"Source with identifier '{identifier}' already exists")
        
        from datetime import datetime
        now = datetime.now()
        
        # Create source object with all required fields
        source = Source(
            id=len(self._sources) + 1,
            identifier=identifier,
            name=source_data['name'],
            url=source_data['url'],
            rss_url=source_data.get('rss_url'),
            check_frequency=source_data.get('check_frequency', 3600),
            lookback_days=source_data.get('lookback_days', 180),
            active=source_data.get('active', True),
            config=source_data.get('config', {}),
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now
        )
        
        self._sources[identifier] = source
        return source
    
    def get_source(self, identifier: str) -> Optional['Source']:
        """Get source by identifier."""
        return self._sources.get(identifier)
    
    def update_source(self, identifier: str, update_data: Dict) -> Optional['Source']:
        """Update source."""
        if identifier not in self._sources:
            raise ValueError(f"Source '{identifier}' not found")
        
        source = self._sources[identifier]
        
        # Update fields
        for key, value in update_data.items():
            if hasattr(source, key):
                setattr(source, key, value)
        
        return source
    
    def remove_source(self, identifier: str) -> bool:
        """Remove source."""
        if identifier in self._sources:
            del self._sources[identifier]
            return True
        return False
    
    def list_sources(self, active_only: bool = False) -> List['Source']:
        """List all sources."""
        sources = list(self._sources.values())
        if active_only:
            sources = [s for s in sources if s.active]
        return sources
    
    def get_source_config(self, identifier: str) -> Optional[SourceConfig]:
        """Get source configuration."""
        return self._source_configs.get(identifier)
    
    def update_source_config(self, identifier: str, config: SourceConfig) -> bool:
        """Update source configuration."""
        if identifier not in self._sources:
            return False
        
        self._source_configs[identifier] = config
        return True
    
    def validate_source_data(self, source_data: Dict) -> bool:
        """Validate source data."""
        required_fields = ['identifier', 'name', 'url']
        for field in required_fields:
            if field not in source_data:
                return False
        
        # Validate URL
        if not self.validate_url(source_data['url']):
            return False
        
        # Validate RSS URL if present
        if 'rss_url' in source_data and source_data['rss_url']:
            if not self.validate_rss_url(source_data['rss_url']):
                return False
        
        return True
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format."""
        if not url:
            return False
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            return False
        
        # Check for invalid protocols
        invalid_protocols = ['ftp://', 'javascript:', 'data:', 'file:']
        for protocol in invalid_protocols:
            if url.startswith(protocol):
                return False
        
        return True
    
    def validate_rss_url(self, url: str) -> bool:
        """Validate RSS URL format."""
        if not self.validate_url(url):
            return False
        
        # Check for common RSS/Atom patterns
        rss_patterns = ['/feed', '/rss', '/atom', '.xml', '.rss']
        return any(pattern in url.lower() for pattern in rss_patterns)
    
    def get_statistics(self) -> Dict:
        """Get source statistics."""
        total_sources = len(self._sources)
        active_sources = len([s for s in self._sources.values() if s.active])
        inactive_sources = total_sources - active_sources
        
        return {
            'total_sources': total_sources,
            'active_sources': active_sources,
            'inactive_sources': inactive_sources
        }
    
    def export_sources(self) -> List[Dict]:
        """Export sources to dictionary list."""
        return [source.__dict__ for source in self._sources.values()]
    
    def import_sources(self, sources_data: List[Dict]) -> bool:
        """Import sources from dictionary list."""
        try:
            for source_data in sources_data:
                if not self.validate_source_data(source_data):
                    raise ValueError(f"Invalid source data: {source_data}")
                
                identifier = source_data['identifier']
                if identifier in self._sources:
                    raise ValueError(f"Source with identifier '{identifier}' already exists")
                
                self.add_source(source_data)
            
            return True
        except ValueError as e:
            # Re-raise ValueError for validation errors
            raise e
        except Exception as e:
            logger.error(f"Error importing sources: {e}")
            return False
