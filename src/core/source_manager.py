"""Source configuration management system."""

import os
import asyncio
from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import yaml
import logging

from src.models.source import Source, SourceCreate, SourceConfig
from src.database.manager import DatabaseManager
from src.utils.http import HTTPClient
from core.rss_parser import FeedValidator

logger = logging.getLogger(__name__)


class SourceConfigLoader:
    """Loader for YAML source configurations."""
    
    def __init__(self):
        self.supported_versions = ['1.0']
    
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
        active = source_data.get('active', True)
        
        # Parse configuration
        config_dict = {}
        
        # Scope configuration
        if 'scope' in source_data:
            scope = source_data['scope']
            config_dict['allow'] = scope.get('allow', [])
            config_dict['post_url_regex'] = scope.get('post_url_regex', [])
        
        # Discovery configuration
        if 'discovery' in source_data:
            config_dict['discovery'] = source_data['discovery']
        
        # Extraction configuration
        if 'extract' in source_data:
            config_dict['extract'] = source_data['extract']
        
        # Legacy content selector
        if 'content_selector' in source_data:
            config_dict['content_selector'] = source_data['content_selector']
        
        config = SourceConfig.parse_obj(config_dict)
        
        return SourceCreate(
            identifier=identifier,
            name=name,
            url=url,
            rss_url=rss_url if rss_url else None,
            check_frequency=check_frequency,
            active=active,
            config=config
        )


class SourceManager:
    """Manager for source configurations and database synchronization."""
    
    def __init__(self, database_manager: DatabaseManager, http_client: HTTPClient):
        self.db = database_manager
        self.http_client = http_client
        self.config_loader = SourceConfigLoader()
        self.feed_validator = FeedValidator()
    
    async def load_sources_from_config(
        self,
        config_path: str,
        sync_to_db: bool = True,
        validate_feeds: bool = True
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
        
        # Sync to database if requested
        if sync_to_db:
            return await self._sync_sources_to_db(source_configs)
        else:
            # Convert to Source objects (without IDs)
            return [config.to_source() for config in source_configs]
    
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
                        config.tier = max(2, config.tier)  # Downgrade to at least tier 2
                        validated_configs.append(config)
                        
                except Exception as e:
                    logger.error(f"RSS validation failed for {config.identifier}: {e}")
                    # Keep source but disable RSS
                    config.rss_url = None
                    config.tier = max(2, config.tier)
                    validated_configs.append(config)
                
                # Rate limiting between validations
                await asyncio.sleep(1)
            else:
                validated_configs.append(config)
        
        return validated_configs
    
    async def _sync_sources_to_db(self, source_configs: List[SourceCreate]) -> List[Source]:
        """Synchronize source configurations with database."""
        logger.info(f"Synchronizing {len(source_configs)} sources to database")
        
        synced_sources = []
        
        for config in source_configs:
            try:
                # Check if source already exists
                existing_source = self.db.get_source_by_identifier(config.identifier)
                
                if existing_source:
                    # Update existing source
                    from models.source import SourceUpdate
                    
                    update_data = SourceUpdate(
                        name=config.name,
                        url=config.url,
                        rss_url=config.rss_url,
                        tier=config.tier,
                        weight=config.weight,
                        check_frequency=config.check_frequency,
                        active=config.active,
                        config=config.config
                    )
                    
                    updated_source = self.db.update_source(existing_source.id, update_data)
                    if updated_source:
                        synced_sources.append(updated_source)
                        logger.info(f"Updated source: {config.identifier}")
                    
                else:
                    # Create new source
                    new_source = self.db.create_source(config)
                    synced_sources.append(new_source)
                    logger.info(f"Created source: {config.identifier}")
                    
            except Exception as e:
                logger.error(f"Failed to sync source {config.identifier}: {e}")
                continue
        
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
                    'tier': source.tier,
                    'weight': source.weight,
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
                
                # Validate tier
                if config.tier not in [1, 2, 3]:
                    result['warnings'].append(f"Source '{config.identifier}': Invalid tier {config.tier}")
                
                # Validate weight
                if not 0.0 <= config.weight <= 2.0:
                    result['warnings'].append(f"Source '{config.identifier}': Weight {config.weight} outside recommended range (0.0-2.0)")
                
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
