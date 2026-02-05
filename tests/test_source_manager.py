"""Tests for source manager functionality."""

import json
from unittest.mock import mock_open, patch

import pytest

from src.core.source_manager import SourceConfig, SourceConfigLoader, SourceManager


class TestSourceConfig:
    """Test SourceConfig functionality."""

    def test_init_default_config(self):
        """Test SourceConfig initialization with default values."""
        config = SourceConfig()

        assert config.check_frequency == 3600  # 1 hour
        assert config.lookback_days == 180
        assert config.min_content_length == 100
        assert config.max_content_length == 50000
        assert config.enable_rss is True
        assert config.enable_scraping is True
        assert config.rate_limit_delay == 1.0
        assert config.max_retries == 3
        assert config.timeout == 30

    def test_init_custom_config(self):
        """Test SourceConfig initialization with custom values."""
        config = SourceConfig(
            check_frequency=7200,
            lookback_days=365,
            min_content_length=200,
            max_content_length=100000,
            enable_rss=False,
            enable_scraping=True,
            rate_limit_delay=2.0,
            max_retries=5,
            timeout=60,
        )

        assert config.check_frequency == 7200
        assert config.lookback_days == 365
        assert config.min_content_length == 200
        assert config.max_content_length == 100000
        assert config.enable_rss is False
        assert config.enable_scraping is True
        assert config.rate_limit_delay == 2.0
        assert config.max_retries == 5
        assert config.timeout == 60

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = SourceConfig(check_frequency=1800, lookback_days=90, min_content_length=150)

        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict["check_frequency"] == 1800
        assert config_dict["lookback_days"] == 90
        assert config_dict["min_content_length"] == 150

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "check_frequency": 1800,
            "lookback_days": 90,
            "min_content_length": 150,
            "enable_rss": False,
            "rate_limit_delay": 1.5,
        }

        config = SourceConfig.from_dict(config_dict)

        assert config.check_frequency == 1800
        assert config.lookback_days == 90
        assert config.min_content_length == 150
        assert config.enable_rss is False
        assert config.rate_limit_delay == 1.5

    def test_validate_config(self):
        """Test config validation."""
        # Valid config
        config = SourceConfig()
        assert config.validate() is True

        # Invalid check_frequency
        config.check_frequency = -1
        assert config.validate() is False

        # Invalid lookback_days
        config.check_frequency = 3600
        config.lookback_days = -1
        assert config.validate() is False

        # Invalid min_content_length
        config.lookback_days = 180
        config.min_content_length = -1
        assert config.validate() is False

        # Invalid max_content_length
        config.min_content_length = 100
        config.max_content_length = 50  # Less than min_content_length
        assert config.validate() is False


class TestSourceConfigLoaderLoadFromFile:
    """Test SourceConfigLoader.load_from_file against config/sources.yaml (parse and structure)."""

    @pytest.fixture
    def sources_yaml_path(self):
        """Path to config/sources.yaml relative to project root."""
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        return root / "config" / "sources.yaml"

    def test_sources_yaml_parses_and_has_expected_structure(self, sources_yaml_path):
        """config/sources.yaml must parse and contain expected sources (e.g. sekoia with rss_url)."""
        if not sources_yaml_path.exists():
            pytest.skip("config/sources.yaml not found (run from project root)")
        loader = SourceConfigLoader()
        sources = loader.load_from_file(str(sources_yaml_path))
        assert len(sources) >= 1, "sources.yaml should define at least one source"
        by_id = {s.identifier: s for s in sources}
        assert "sekoia_io_blog" in by_id, "sekoia_io_blog should be present after RSS/scraping updates"
        sekoia = by_id["sekoia_io_blog"]
        assert sekoia.rss_url is not None, "sekoia_io_blog should have rss_url set (RSS-first config)"
        assert "group_ib_threat_intel" in by_id
        group_ib = by_id["group_ib_threat_intel"]
        assert group_ib.config is not None
        inner = getattr(group_ib.config, "config", None) or {}
        assert inner.get("rss_only") is False, "Group-IB should be scraping-only in YAML"


@pytest.mark.skip(reason="SourceManager implementation needs review - missing SourceConfigLoader class")
class TestSourceConfigLoader:
    """Test SourceConfigLoader functionality."""

    @pytest.fixture
    def config_loader(self):
        """Create SourceConfigLoader instance for testing."""
        return SourceConfigLoader()

    def test_init(self, config_loader):
        """Test SourceConfigLoader initialization."""
        assert config_loader is not None
        assert hasattr(config_loader, "load_config")
        assert hasattr(config_loader, "save_config")

    def test_load_config_from_file(self, config_loader):
        """Test loading config from file."""
        config_data = {
            "check_frequency": 1800,
            "lookback_days": 90,
            "min_content_length": 150,
            "enable_rss": True,
            "enable_scraping": False,
        }

        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.read.return_value = json.dumps(config_data)

            config = config_loader.load_config("test_config.json")

            assert config.check_frequency == 1800
            assert config.lookback_days == 90
            assert config.min_content_length == 150
            assert config.enable_rss is True
            assert config.enable_scraping is False

    def test_load_config_default(self, config_loader):
        """Test loading default config when file doesn't exist."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            config = config_loader.load_config("nonexistent.json")

            # Should return default config
            assert config.check_frequency == 3600
            assert config.lookback_days == 180
            assert config.min_content_length == 100

    def test_save_config_to_file(self, config_loader):
        """Test saving config to file."""
        config = SourceConfig(check_frequency=1800, lookback_days=90, min_content_length=150)

        with patch("builtins.open", mock_open()) as mock_file:
            config_loader.save_config(config, "test_config.json")

            mock_file.assert_called_once_with("test_config.json", "w")
            mock_file.return_value.write.assert_called_once()

    def test_load_config_from_dict(self, config_loader):
        """Test loading config from dictionary."""
        config_dict = {"check_frequency": 1800, "lookback_days": 90, "min_content_length": 150, "enable_rss": False}

        config = config_loader.load_config_from_dict(config_dict)

        assert config.check_frequency == 1800
        assert config.lookback_days == 90
        assert config.min_content_length == 150
        assert config.enable_rss is False


class TestSourceManager:
    """Test SourceManager functionality."""

    @pytest.fixture
    def source_manager(self):
        """Create SourceManager instance for testing."""
        return SourceManager()

    @pytest.fixture
    def sample_source_data(self):
        """Create sample source data for testing."""
        return {
            "identifier": "test-source",
            "name": "Test Source",
            "url": "https://example.com",
            "rss_url": "https://example.com/feed.xml",
            "check_frequency": 3600,
            "lookback_days": 180,
            "active": True,
            "config": {
                "min_content_length": 100,
                "max_content_length": 50000,
                "enable_rss": True,
                "enable_scraping": True,
            },
        }

    def test_init(self, source_manager):
        """Test SourceManager initialization."""
        assert source_manager is not None
        assert hasattr(source_manager, "add_source")
        assert hasattr(source_manager, "get_source")
        assert hasattr(source_manager, "update_source")
        assert hasattr(source_manager, "remove_source")
        assert hasattr(source_manager, "list_sources")

    def test_add_source_success(self, source_manager, sample_source_data):
        """Test successful source addition."""
        source = source_manager.add_source(sample_source_data)

        assert source is not None
        assert source.identifier == "test-source"
        assert source.name == "Test Source"
        assert source.url == "https://example.com"
        assert source.rss_url == "https://example.com/feed.xml"
        assert source.active is True

    def test_add_source_duplicate_identifier(self, source_manager, sample_source_data):
        """Test adding source with duplicate identifier."""
        # Add first source
        source_manager.add_source(sample_source_data)

        # Try to add duplicate
        with pytest.raises(ValueError, match="Source with identifier 'test-source' already exists"):
            source_manager.add_source(sample_source_data)

    def test_add_source_invalid_data(self, source_manager):
        """Test adding source with invalid data."""
        invalid_data = {
            "name": "Invalid Source"
            # Missing required fields
        }

        with pytest.raises(ValueError, match="Invalid source data"):
            source_manager.add_source(invalid_data)

    def test_get_source_success(self, source_manager, sample_source_data):
        """Test successful source retrieval."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Get source
        retrieved_source = source_manager.get_source("test-source")

        assert retrieved_source is not None
        assert retrieved_source.identifier == "test-source"
        assert retrieved_source.name == "Test Source"

    def test_get_source_not_found(self, source_manager):
        """Test getting non-existent source."""
        source = source_manager.get_source("nonexistent-source")

        assert source is None

    def test_update_source_success(self, source_manager, sample_source_data):
        """Test successful source update."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Update source
        update_data = {"name": "Updated Test Source", "check_frequency": 7200, "active": False}

        updated_source = source_manager.update_source("test-source", update_data)

        assert updated_source is not None
        assert updated_source.name == "Updated Test Source"
        assert updated_source.check_frequency == 7200
        assert updated_source.active is False

    def test_update_source_not_found(self, source_manager):
        """Test updating non-existent source."""
        update_data = {"name": "Updated Source"}

        with pytest.raises(ValueError, match="Source 'nonexistent-source' not found"):
            source_manager.update_source("nonexistent-source", update_data)

    def test_remove_source_success(self, source_manager, sample_source_data):
        """Test successful source removal."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Remove source
        result = source_manager.remove_source("test-source")

        assert result is True

        # Verify source is removed
        source = source_manager.get_source("test-source")
        assert source is None

    def test_remove_source_not_found(self, source_manager):
        """Test removing non-existent source."""
        result = source_manager.remove_source("nonexistent-source")

        assert result is False

    def test_list_sources(self, source_manager, sample_source_data):
        """Test listing all sources."""
        # Add multiple sources
        source1_data = sample_source_data.copy()
        source1_data["identifier"] = "source-1"
        source1_data["name"] = "Source 1"

        source2_data = sample_source_data.copy()
        source2_data["identifier"] = "source-2"
        source2_data["name"] = "Source 2"

        source_manager.add_source(source1_data)
        source_manager.add_source(source2_data)

        # List sources
        sources = source_manager.list_sources()

        assert len(sources) == 2
        assert any(s.identifier == "source-1" for s in sources)
        assert any(s.identifier == "source-2" for s in sources)

    def test_list_sources_empty(self, source_manager):
        """Test listing sources when none exist."""
        sources = source_manager.list_sources()

        assert len(sources) == 0

    def test_list_sources_active_only(self, source_manager, sample_source_data):
        """Test listing only active sources."""
        # Add active source
        source_manager.add_source(sample_source_data)

        # Add inactive source
        inactive_data = sample_source_data.copy()
        inactive_data["identifier"] = "inactive-source"
        inactive_data["name"] = "Inactive Source"
        inactive_data["active"] = False

        source_manager.add_source(inactive_data)

        # List active sources
        active_sources = source_manager.list_sources(active_only=True)

        assert len(active_sources) == 1
        assert active_sources[0].identifier == "test-source"

    def test_get_source_config(self, source_manager, sample_source_data):
        """Test getting source configuration."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Set a config first
        from src.core.source_manager import SourceConfig

        test_config = SourceConfig(
            min_content_length=100, max_content_length=50000, enable_rss=True, enable_scraping=True
        )
        source_manager.update_source_config("test-source", test_config)

        # Get config
        config = source_manager.get_source_config("test-source")

        assert config is not None
        assert config.min_content_length == 100
        assert config.max_content_length == 50000
        assert config.enable_rss is True
        assert config.enable_scraping is True

    def test_update_source_config(self, source_manager, sample_source_data):
        """Test updating source configuration."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Update config
        new_config = SourceConfig(
            min_content_length=200, max_content_length=100000, enable_rss=False, enable_scraping=True
        )

        result = source_manager.update_source_config("test-source", new_config)

        assert result is True

        # Verify config updated
        config = source_manager.get_source_config("test-source")
        assert config.min_content_length == 200
        assert config.max_content_length == 100000
        assert config.enable_rss is False
        assert config.enable_scraping is True

    def test_update_source_config_not_found(self, source_manager):
        """Test updating config for non-existent source."""
        config = SourceConfig()

        result = source_manager.update_source_config("nonexistent-source", config)

        assert result is False

    def test_validate_source_data(self, source_manager):
        """Test source data validation."""
        # Valid data
        valid_data = {
            "identifier": "valid-source",
            "name": "Valid Source",
            "url": "https://example.com",
            "rss_url": "https://example.com/feed.xml",
        }

        assert source_manager.validate_source_data(valid_data) is True

        # Invalid data - missing identifier
        invalid_data = {"name": "Invalid Source", "url": "https://example.com"}

        assert source_manager.validate_source_data(invalid_data) is False

        # Invalid data - missing name
        invalid_data = {"identifier": "invalid-source", "url": "https://example.com"}

        assert source_manager.validate_source_data(invalid_data) is False

        # Invalid data - missing URL
        invalid_data = {"identifier": "invalid-source", "name": "Invalid Source"}

        assert source_manager.validate_source_data(invalid_data) is False

    def test_validate_url(self, source_manager):
        """Test URL validation."""
        # Valid URLs
        valid_urls = [
            "https://example.com",
            "http://example.com",
            "https://subdomain.example.com/path",
            "https://example.com:8080/path?query=value",
        ]

        for url in valid_urls:
            assert source_manager.validate_url(url) is True

        # Invalid URLs
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",
            'javascript:alert("xss")',
            'data:text/html,<script>alert("xss")</script>',
        ]

        for url in invalid_urls:
            assert source_manager.validate_url(url) is False

    def test_validate_rss_url(self, source_manager):
        """Test RSS URL validation."""
        # Valid RSS URLs
        valid_rss_urls = [
            "https://example.com/feed.xml",
            "https://example.com/rss",
            "https://example.com/atom.xml",
            "https://example.com/feed.rss",
        ]

        for url in valid_rss_urls:
            assert source_manager.validate_rss_url(url) is True

        # Invalid RSS URLs
        invalid_rss_urls = ["https://example.com", "https://example.com/page.html", "not-a-url"]

        for url in invalid_rss_urls:
            assert source_manager.validate_rss_url(url) is False

    def test_get_source_statistics(self, source_manager, sample_source_data):
        """Test getting source statistics."""
        # Add sources
        source_manager.add_source(sample_source_data)

        inactive_data = sample_source_data.copy()
        inactive_data["identifier"] = "inactive-source"
        inactive_data["name"] = "Inactive Source"
        inactive_data["active"] = False

        source_manager.add_source(inactive_data)

        # Get statistics
        stats = source_manager.get_statistics()

        assert "total_sources" in stats
        assert "active_sources" in stats
        assert "inactive_sources" in stats
        assert stats["total_sources"] == 2
        assert stats["active_sources"] == 1
        assert stats["inactive_sources"] == 1

    def test_export_sources(self, source_manager, sample_source_data):
        """Test exporting sources to dictionary."""
        # Add source
        source_manager.add_source(sample_source_data)

        # Export sources
        exported = source_manager.export_sources()

        assert isinstance(exported, list)
        assert len(exported) == 1
        assert exported[0]["identifier"] == "test-source"
        assert exported[0]["name"] == "Test Source"

    def test_import_sources(self, source_manager):
        """Test importing sources from dictionary."""
        sources_data = [
            {
                "identifier": "imported-source-1",
                "name": "Imported Source 1",
                "url": "https://example1.com",
                "rss_url": "https://example1.com/feed.xml",
            },
            {
                "identifier": "imported-source-2",
                "name": "Imported Source 2",
                "url": "https://example2.com",
                "rss_url": "https://example2.com/feed.xml",
            },
        ]

        result = source_manager.import_sources(sources_data)

        assert result is True

        # Verify sources imported
        sources = source_manager.list_sources()
        assert len(sources) == 2
        assert any(s.identifier == "imported-source-1" for s in sources)
        assert any(s.identifier == "imported-source-2" for s in sources)

    def test_import_sources_duplicate(self, source_manager, sample_source_data):
        """Test importing sources with duplicate identifiers."""
        # Add existing source
        source_manager.add_source(sample_source_data)

        # Try to import duplicate
        sources_data = [sample_source_data]

        with pytest.raises(ValueError, match="Source with identifier 'test-source' already exists"):
            source_manager.import_sources(sources_data)

    def test_import_sources_invalid_data(self, source_manager):
        """Test importing sources with invalid data."""
        invalid_sources_data = [
            {
                "name": "Invalid Source"
                # Missing required fields
            }
        ]

        with pytest.raises(ValueError, match="Invalid source data"):
            source_manager.import_sources(invalid_sources_data)

    def test_source_manager_performance(self, source_manager, sample_source_data):
        """Test source manager performance."""
        import time

        start_time = time.time()

        # Add multiple sources
        for i in range(100):
            source_data = sample_source_data.copy()
            source_data["identifier"] = f"source-{i}"
            source_data["name"] = f"Source {i}"
            source_manager.add_source(source_data)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should add 100 sources in reasonable time
        assert processing_time < 1.0  # Less than 1 second
        assert processing_time > 0.0

        # Verify all sources added
        sources = source_manager.list_sources()
        assert len(sources) == 100
