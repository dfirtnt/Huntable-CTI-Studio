"""Integration test: metadata-only indexing + capability reporting + RAG degradation."""

from unittest.mock import MagicMock

import pytest

from src.services.capability_service import CapabilityService
from src.services.sigma_sync_service import SigmaSyncService


@pytest.fixture
def sigma_repo(tmp_path):
    rules_dir = tmp_path / "rules" / "windows"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "test_rule.yml"
    rule_file.write_text(
        """
title: Test Process Execution
id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
status: test
description: Test rule for integration testing
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'suspicious.exe'
    condition: selection
level: high
tags:
    - attack.execution
"""
    )
    return tmp_path


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.all.return_value = []
    session.no_autoflush = MagicMock()
    session.no_autoflush.__enter__ = MagicMock(return_value=None)
    session.no_autoflush.__exit__ = MagicMock(return_value=False)
    return session


class TestDecoupledIndexingIntegration:
    def test_metadata_indexing_then_capability_check(self, sigma_repo, mock_db_session):
        """Full flow: index metadata -> check capabilities -> verify sigma_retrieval disabled."""
        added_objects = []
        mock_db_session.add.side_effect = lambda obj: added_objects.append(obj)

        # Phase 1: Index metadata only
        sync_service = SigmaSyncService(repo_path=str(sigma_repo))
        result = sync_service.index_metadata(mock_db_session)

        assert result["metadata_indexed"] == 1
        assert len(added_objects) == 1
        rule = added_objects[0]
        assert rule.embedding is None  # No embedding generated
        assert rule.title == "Test Process Execution"

        # Phase 2: Check capabilities — sigma_retrieval should be disabled (no embeddings)
        cap_service = CapabilityService(sigma_repo_path=str(sigma_repo))

        # Mock DB to reflect post-metadata-index state: rules exist but no embeddings
        mock_db_session.query.return_value.filter.return_value.count.return_value = 0
        caps = cap_service.compute_capabilities(db_session=mock_db_session)

        assert caps["sigma_retrieval"]["enabled"] is False
        assert "action" in caps["sigma_retrieval"]
        assert caps["sigma_metadata_indexing"]["enabled"] is True
