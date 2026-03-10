"""Characterization tests for source manager configuration handling."""

import pytest

from src.core.source_manager import SourceConfig, SourceConfigLoader

pytestmark = pytest.mark.unit


def test_source_config_validate_and_roundtrip_dict():
    cfg = SourceConfig()
    assert cfg.validate() is True

    as_dict = cfg.to_dict()
    restored = SourceConfig.from_dict(as_dict)
    assert restored.to_dict() == as_dict


def test_source_config_validate_rejects_invalid_bounds():
    invalid = SourceConfig(min_content_length=500, max_content_length=100)
    assert invalid.validate() is False


def test_parse_config_deduplicates_and_skips_invalid_entries():
    loader = SourceConfigLoader()
    parsed = loader._parse_config(
        {
            "version": "1.0",
            "sources": [
                {"id": "a", "name": "Alpha", "url": "https://alpha.example"},
                {"id": "a", "name": "Dup", "url": "https://dup.example"},  # duplicate identifier
                {"id": "b", "name": "Missing URL"},  # invalid row
            ],
        }
    )

    assert len(parsed) == 1
    assert parsed[0].identifier == "a"
    assert parsed[0].name == "Alpha"


def test_parse_source_legacy_fields_are_mapped_into_config_dict():
    loader = SourceConfigLoader()
    source = loader._parse_source(
        {
            "id": "legacy",
            "name": "Legacy Source",
            "url": "https://legacy.example",
            "scope": {
                "allow": ["https://legacy.example/posts/*"],
                "post_url_regex": ["/posts/"],
            },
            "discovery": {"enabled": True},
            "extract": {"mode": "article"},
            "content_selector": "article main",
        }
    )

    assert source.identifier == "legacy"
    assert source.config.config["allow"] == ["https://legacy.example/posts/*"]
    assert source.config.config["post_url_regex"] == ["/posts/"]
    assert source.config.config["discovery"]["enabled"] is True
    assert source.config.config["extract"]["mode"] == "article"
    assert source.config.config["content_selector"] == "article main"


def test_parse_config_rejects_unsupported_version():
    loader = SourceConfigLoader()
    with pytest.raises(ValueError, match="Unsupported configuration version"):
        loader._parse_config({"version": "9.9", "sources": []})
