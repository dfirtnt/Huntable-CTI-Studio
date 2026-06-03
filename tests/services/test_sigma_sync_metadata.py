"""Tests for SigmaSyncService.index_metadata() — metadata phase only, no embeddings."""

from pathlib import Path
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


class TestParseRuleFileDateNormalization:
    """parse_rule_file must normalize `date` to a datetime or None — NEVER "".

    Regression: customer-authored rules frequently omit `date:`. The old code
    defaulted a missing date to "" and the conversion guard (`if parsed["date"]`)
    skipped the empty string, leaving "" — which fails the timestamp column on
    insert and (because rules insert in one batch) poisons the whole batch. This
    blocked `sigma index-customer-repo` entirely for any rule set lacking dates.
    """

    from datetime import datetime as _dt
    from pathlib import Path as _Path

    def _service_for(self, tmp_path, date_line: str):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        f = rules_dir / "r.yml"
        f.write_text(
            "title: R\n"
            "id: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n"
            "status: experimental\n"
            "description: d\n"
            f"{date_line}"
            "logsource:\n    category: process_creation\n    product: windows\n"
            "detection:\n    selection:\n        Image|endswith: '\\\\calc.exe'\n    condition: selection\n"
            "level: low\n",
            encoding="utf-8",
        )
        return SigmaSyncService(repo_path=str(tmp_path)), f

    def test_missing_date_is_none_not_empty_string(self, tmp_path):
        """The crash-fix: no `date:` line → None (NOT "", which breaks the insert)."""
        service, f = self._service_for(tmp_path, date_line="")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] is None

    def test_empty_date_is_none(self, tmp_path):
        service, f = self._service_for(tmp_path, date_line="date: ''\n")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] is None

    def test_iso_string_date_parsed(self, tmp_path):
        """Customer/LLM style ISO date as a quoted string → datetime."""
        service, f = self._service_for(tmp_path, date_line="date: '2026-05-29'\n")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] == self._dt(2026, 5, 29)

    def test_sigmahq_slash_date_parsed(self, tmp_path):
        service, f = self._service_for(tmp_path, date_line="date: '2024/01/15'\n")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] == self._dt(2024, 1, 15)

    def test_yaml_native_date_parsed(self, tmp_path):
        """Unquoted `date: 2024-01-15` → PyYAML date object → datetime."""
        service, f = self._service_for(tmp_path, date_line="date: 2024-01-15\n")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] == self._dt(2024, 1, 15)

    def test_unparseable_date_string_falls_back_to_none(self, tmp_path):
        service, f = self._service_for(tmp_path, date_line="date: 'not-a-date'\n")
        parsed = service.parse_rule_file(f)
        assert parsed["date"] is None


class TestFindRuleFilesMultiDir:
    """find_rule_files must scan rules/, rules-emerging-threats/, and rules-threat-hunting/."""

    def _write_rule(self, path: "Path", rule_id: str, title: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"title: {title}\n"
            f"id: {rule_id}\n"
            "status: experimental\n"
            "description: Test rule\n"
            "logsource:\n"
            "    category: process_creation\n"
            "    product: windows\n"
            "detection:\n"
            "    selection:\n"
            "        Image|endswith: '\\\\malware.exe'\n"
            "    condition: selection\n"
            "level: high\n",
            encoding="utf-8",
        )

    def test_scans_all_three_rule_dirs(self, tmp_path):
        self._write_rule(
            tmp_path / "rules" / "windows" / "stable.yml",
            "aaaaaaaa-0000-0000-0000-000000000001",
            "Stable Rule",
        )
        self._write_rule(
            tmp_path / "rules-emerging-threats" / "windows" / "emerging.yml",
            "aaaaaaaa-0000-0000-0000-000000000002",
            "Emerging Threat Rule",
        )
        self._write_rule(
            tmp_path / "rules-threat-hunting" / "windows" / "hunting.yml",
            "aaaaaaaa-0000-0000-0000-000000000003",
            "Threat Hunting Rule",
        )

        svc = SigmaSyncService(repo_path=str(tmp_path))
        files = svc.find_rule_files()

        names = {f.name for f in files}
        assert "stable.yml" in names
        assert "emerging.yml" in names
        assert "hunting.yml" in names
        assert len(files) == 3

    def test_missing_extra_dirs_are_skipped_gracefully(self, tmp_path):
        """Only rules/ present — no error, no crash."""
        self._write_rule(
            tmp_path / "rules" / "windows" / "only.yml",
            "aaaaaaaa-0000-0000-0000-000000000004",
            "Only Rule",
        )

        svc = SigmaSyncService(repo_path=str(tmp_path))
        files = svc.find_rule_files()

        assert len(files) == 1
        assert files[0].name == "only.yml"
