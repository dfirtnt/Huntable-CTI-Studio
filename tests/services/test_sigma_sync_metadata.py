"""Tests for SigmaSyncService.index_metadata() — metadata phase only, no embeddings."""

from unittest.mock import MagicMock

import pytest

from src.services.sigma_sync_service import SigmaSyncService


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
