#!/usr/bin/env python3
"""Test the full Assetnote article processing pipeline."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import the actual RSS parser and related components
from src.core.rss_parser import RSSParser
from src.utils.http import HTTPClient
import yaml
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockSource:
    """Mock source object for testing."""
    def __init__(self, config_dict):
        self.identifier = config_dict['id']
        self.name = config_dict['name']
        self.url = config_dict['url']
        self.rss_url = config_dict['rss_url']
        self.id = 1  # Mock database ID

        # Create config object from dict
        class MockConfig:
            def __init__(self, config):
                self._config = config
                for key, value in config.items():
                    setattr(self, key, value)

            def model_dump(self):
                return self._config

            def __contains__(self, key):
                return key in self._config

            def __getitem__(self, key):
                return self._config[key]

            def get(self, key, default=None):
                return self._config.get(key, default)

        self.config = MockConfig(config_dict['config'])

async def test_assetnote_pipeline():
    """Test the full Assetnote RSS processing pipeline."""

    # Load the Assetnote source configuration
    with open('config/sources.yaml', 'r') as f:
        sources_config = yaml.safe_load(f)

    # Find the Assetnote source
    assetnote_config = None
    for source in sources_config['sources']:
        if source['id'] == 'assetnote_research':
            assetnote_config = source
            break

    if not assetnote_config:
        logger.error("Assetnote source not found in configuration")
        return False

    logger.info(f"Found Assetnote configuration: {assetnote_config['name']}")

    # Create mock source
    source = MockSource(assetnote_config)

    # Initialize HTTP client and RSS parser
    async with HTTPClient() as http_client:
        rss_parser = RSSParser(http_client)

        try:
            logger.info("Starting RSS parsing for Assetnote...")

            # Parse the RSS feed
            articles = await rss_parser.parse_feed(source)

            logger.info(f"RSS parsing completed. Found {len(articles)} articles.")

            # Examine the first few articles
            for i, article in enumerate(articles[:3]):
                logger.info(f"\n--- Article {i+1} ---")
                logger.info(f"Title: {article.title}")
                logger.info(f"URL: {article.canonical_url}")
                logger.info(f"Published: {article.published_at}")
                logger.info(f"Content length: {len(article.content)} chars")
                logger.info(f"Content preview: {article.content[:200]}...")

                # Check if article meets quality requirements
                if len(article.content) >= 1000:
                    logger.info("✅ Article meets quality requirements")
                else:
                    logger.warning("❌ Article does not meet quality requirements")

            return len(articles)

        except Exception as e:
            logger.error(f"Error in pipeline test: {e}", exc_info=True)
            return 0

if __name__ == "__main__":
    article_count = asyncio.run(test_assetnote_pipeline())
    print(f"\n🎯 Final result: Processed {article_count} Assetnote articles through full pipeline")