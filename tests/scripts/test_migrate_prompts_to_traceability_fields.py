"""Tests for scripts/migrate_prompts_to_traceability_fields.py.

The script itself is a one-shot operator tool. SQL correctness was verified
end-to-end via `--dry-run` against a real Postgres instance with 1,134 history
rows. These tests guard the pure-logic surface that is most likely to regress:

- Idempotency detection (`_needs_migration`): a re-run must be a no-op on rows
  that were already migrated, and must fire on rows still using the deprecated
  field names.
- Contract between `MIGRATED_AGENTS` and `src/prompts/`: every agent declared
  as migrated must have a readable, JSON-valid prompt file on disk. If someone
  adds a new agent to the tuple but forgets the prompt file, this test fails
  fast at the test layer rather than mid-migration in production.
- Prompt file contents are on the new contract (no deprecated field names).
  Overlaps with the broader traceability contract test but provides a clear
  failure message for the specific agents this script is authoritative for.

These are unit tests — no DB, no network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_prompts_to_traceability_fields.py"
PROMPT_DIR = REPO_ROOT / "src" / "prompts"


def _load_script_module():
    """Import the migration script as a module without executing main()."""
    spec = importlib.util.spec_from_file_location("migrate_prompts_to_traceability_fields", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


# ============================================================================
# Idempotency: _needs_migration
# ============================================================================


class TestNeedsMigration:
    """Re-running the script on an already-migrated row must be a no-op."""

    def test_none_returns_false(self, script):
        assert script._needs_migration(None) is False

    def test_empty_string_returns_false(self, script):
        assert script._needs_migration("") is False

    def test_already_migrated_content_returns_false(self, script):
        current = json.dumps(
            {
                "role": "stub",
                "json_example": {
                    "value": "x",
                    "source_evidence": "y",
                    "extraction_justification": "z",
                    "confidence_score": 0.9,
                },
            }
        )
        assert script._needs_migration(current) is False

    def test_legacy_raw_text_snippet_returns_true(self, script):
        stale = json.dumps({"json_example": {"raw_text_snippet": "..."}})
        assert script._needs_migration(stale) is True

    def test_legacy_confidence_level_returns_true(self, script):
        stale = json.dumps({"json_example": {"confidence_level": "high"}})
        assert script._needs_migration(stale) is True

    def test_both_legacy_fields_returns_true(self, script):
        stale = "raw_text_snippet and confidence_level together"
        assert script._needs_migration(stale) is True


# ============================================================================
# MIGRATED_AGENTS <-> src/prompts/ contract
# ============================================================================


class TestMigratedAgentsHavePromptFiles:
    """Every agent in MIGRATED_AGENTS must have a readable JSON prompt file."""

    def test_migrated_agents_tuple_is_nonempty(self, script):
        assert script.MIGRATED_AGENTS, "MIGRATED_AGENTS must not be empty"

    def test_every_migrated_agent_has_a_prompt_file(self, script):
        for agent in script.MIGRATED_AGENTS:
            path = PROMPT_DIR / agent
            assert path.exists(), (
                f"MIGRATED_AGENTS references {agent!r} but src/prompts/{agent} "
                f"is missing. The migration would fail at _load_prompt_text()."
            )

    def test_every_migrated_agent_prompt_is_valid_json(self, script):
        for agent in script.MIGRATED_AGENTS:
            text = script._load_prompt_text(agent)
            # _load_prompt_text already validates; double-check here so a
            # broken file surfaces with an agent-specific failure message.
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                pytest.fail(f"src/prompts/{agent} is not valid JSON: {exc}")

    def test_every_migrated_prompt_is_on_new_contract(self, script):
        """After migration runs, re-running must be a no-op — which requires
        the source files themselves to be clean of deprecated field names."""
        for agent in script.MIGRATED_AGENTS:
            text = script._load_prompt_text(agent)
            for field in script.DEPRECATED_FIELDS:
                assert field not in text, (
                    f"src/prompts/{agent} still contains deprecated field "
                    f"{field!r}. Migration would not be idempotent: re-running "
                    f"would keep rewriting this row indefinitely."
                )


# ============================================================================
# _load_prompt_text error paths
# ============================================================================


class TestLoadPromptText:
    def test_missing_file_raises_file_not_found(self, script):
        with pytest.raises(FileNotFoundError):
            script._load_prompt_text("ThisAgentDoesNotExist__")

    def test_invalid_json_raises_value_error(self, script, tmp_path, monkeypatch):
        """If a prompt file becomes malformed, we must fail fast before DB writes."""
        bogus = tmp_path / "BogusAgent"
        bogus.write_text("not { valid json", encoding="utf-8")
        monkeypatch.setattr(script, "PROMPT_DIR", tmp_path)
        with pytest.raises(ValueError, match="not valid JSON"):
            script._load_prompt_text("BogusAgent")


# ============================================================================
# DATABASE_URL resolution
# ============================================================================


class TestResolveDatabaseUrl:
    def test_returns_none_when_unset(self, script, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert script._resolve_database_url() is None

    def test_strips_asyncpg_driver_suffix(self, script, monkeypatch):
        """Script uses sync SQLAlchemy; the asyncpg suffix must be rewritten."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/db")
        assert script._resolve_database_url() == "postgresql://u:p@h:5432/db"

    def test_leaves_plain_postgres_url_intact(self, script, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
        assert script._resolve_database_url() == "postgresql://u:p@h:5432/db"
