from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrate_source_sigma_queue.py"
TEST_SCHEMA_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "init_test_schema.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("migrate_source_sigma_queue", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_generated_and_creates_partial_unique_guards():
    module = _load_script()
    sql = module.MIGRATION_SQL
    assert "UPDATE sigma_rule_queue SET rule_origin = 'generated'" in sql
    assert "ALTER COLUMN rule_origin SET NOT NULL" in sql
    assert "uq_sigma_queue_source_url_rule_id" in sql
    assert "uq_sigma_queue_source_content_sha256" in sql
    assert "WHERE rule_origin = 'source_provided'" in sql


def test_test_database_bootstrap_applies_source_queue_migration():
    source = TEST_SCHEMA_SCRIPT.read_text(encoding="utf-8")
    assert "from scripts.migrate_source_sigma_queue import run_migration" in source
    assert "migrate_source_sigma_queue(db_url, apply=True)" in source
