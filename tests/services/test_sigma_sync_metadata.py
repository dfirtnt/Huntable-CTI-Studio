"""Tests for SigmaSyncService.index_metadata() — metadata phase only, no embeddings."""

from unittest.mock import MagicMock

import pytest

from src.services.sigma_sync_service import SigmaSyncService

pytestmark = pytest.mark.unit


@pytest.fixture
def sigma_repo(tmp_path):
    """Create a minimal sigma repo with one rule file."""
    rules_dir = tmp_path / "rules" / "windows"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "test_rule.yml"
    rule_file.write_text(
        """
title: Test Suspicious Process
id: 12345678-1234-1234-1234-123456789abc
status: test
description: Detects test suspicious process execution
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test.exe'
    condition: selection
level: medium
tags:
    - attack.execution
    - attack.t1059
"""
    )
    return tmp_path


@pytest.fixture
def sync_service(sigma_repo):
    return SigmaSyncService(repo_path=str(sigma_repo))


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.all.return_value = []
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


class TestIndexMetadata:
    def test_indexes_metadata_without_embedding_dependency(self, sync_service, mock_db_session):
        """index_metadata must succeed without any embedding service."""
        result = sync_service.index_metadata(mock_db_session)

        assert result["metadata_indexed"] >= 1
        assert "errors" in result
        # Verify db_session.add was called (rule was persisted)
        assert mock_db_session.add.called

    def test_metadata_result_has_expected_keys(self, sync_service, mock_db_session):
        result = sync_service.index_metadata(mock_db_session)

        assert "metadata_indexed" in result
        assert "skipped" in result
        assert "errors" in result

    def test_metadata_computes_canonical_fields(self, sync_service, mock_db_session):
        """index_metadata should compute canonical novelty fields."""
        added_objects = []
        mock_db_session.add.side_effect = lambda obj: added_objects.append(obj)

        sync_service.index_metadata(mock_db_session)

        assert len(added_objects) >= 1
        rule = added_objects[0]
        assert rule.canonical_json is not None
        assert rule.exact_hash is not None
        assert rule.embedding is None

    def test_metadata_skips_existing_rules(self, sync_service, mock_db_session):
        """Should skip rules already in DB when force_reindex=False."""
        mock_db_session.query.return_value.all.return_value = [("12345678-1234-1234-1234-123456789abc",)]

        result = sync_service.index_metadata(mock_db_session, force_reindex=False)
        assert result["skipped"] >= 1
        assert result["metadata_indexed"] == 0

    def test_metadata_reindexes_with_force(self, sync_service, mock_db_session):
        """force_reindex=True should update existing rules."""
        existing_rule = MagicMock()
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = existing_rule
        mock_db_session.query.return_value.all.return_value = [("12345678-1234-1234-1234-123456789abc",)]

        result = sync_service.index_metadata(mock_db_session, force_reindex=True)
        assert result["metadata_indexed"] >= 1

    def test_metadata_stores_raw_yaml_on_new_rule(self, sync_service, mock_db_session):
        """index_metadata must persist raw_yaml on newly created SigmaRuleTable rows."""
        added_objects = []
        mock_db_session.add.side_effect = lambda obj: added_objects.append(obj)

        sync_service.index_metadata(mock_db_session)

        assert len(added_objects) >= 1
        rule = added_objects[0]
        assert rule.raw_yaml is not None
        assert len(rule.raw_yaml) > 0
        # Verify it's valid YAML text (contains the rule title)
        assert "Test Suspicious Process" in rule.raw_yaml

    def test_metadata_raw_yaml_matches_file_on_disk(self, sync_service, sigma_repo):
        """raw_yaml stored on the parsed object should equal the source file content."""
        rule_file = sigma_repo / "rules" / "windows" / "test_rule.yml"
        expected_text = rule_file.read_text(encoding="utf-8")

        parsed = sync_service.parse_rule_file(rule_file)

        assert parsed is not None
        assert parsed["raw_yaml"] == expected_text


class TestParseRuleFileRawYaml:
    """Focused tests for parse_rule_file raw_yaml capture."""

    @pytest.fixture
    def rule_file(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        f = rules_dir / "sample.yml"
        f.write_text(
            "title: Sample\n"
            "id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n"
            "status: experimental\n"
            "description: A sample rule\n"
            "logsource:\n"
            "    category: process_creation\n"
            "    product: windows\n"
            "detection:\n"
            "    selection:\n"
            "        Image|endswith: '\\\\calc.exe'\n"
            "    condition: selection\n"
            "level: low\n",
            encoding="utf-8",
        )
        return f, tmp_path

    @pytest.fixture
    def service(self, rule_file):
        _, repo_path = rule_file
        return SigmaSyncService(repo_path=str(repo_path))

    def test_parse_rule_file_includes_raw_yaml_key(self, rule_file, service):
        f, _ = rule_file
        parsed = service.parse_rule_file(f)
        assert parsed is not None
        assert "raw_yaml" in parsed

    def test_parse_rule_file_raw_yaml_is_original_text(self, rule_file, service):
        f, _ = rule_file
        expected = f.read_text(encoding="utf-8")
        parsed = service.parse_rule_file(f)
        assert parsed["raw_yaml"] == expected

    def test_parse_rule_file_raw_yaml_nonempty(self, rule_file, service):
        f, _ = rule_file
        parsed = service.parse_rule_file(f)
        assert parsed["raw_yaml"].strip() != ""
