"""Tests for scripts/check_paired_surfaces.py.

The script is a pull_request CI gate. Its contract is:

- ``find_violations(changed_files, labels)`` is pure: one message per pair
  whose trigger changed without a satisfier and without its escape label.
- ``main`` exits 0 with no violations, 1 with violations, 2 if git fails.

These tests pin the two documented pairs, both escape labels, and that
unrelated changes never trip the gate. All are pure unit tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_paired_surfaces.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_paired_surfaces", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_script_module()


# --- models.py <-> migration ------------------------------------------------


def test_models_without_migration_is_violation(mod):
    out = mod.find_violations(["src/database/models.py", "src/services/foo.py"])
    assert len(out) == 1
    assert "scripts/migrate_*.py" in out[0]


def test_models_with_migration_passes(mod):
    assert mod.find_violations(["src/database/models.py", "scripts/migrate_add_widget.py"]) == []


def test_models_with_escape_label_passes(mod):
    assert mod.find_violations(["src/database/models.py"], labels=[mod.LABEL_NO_MIGRATION]) == []


def test_migration_alone_is_fine(mod):
    assert mod.find_violations(["scripts/migrate_add_widget.py"]) == []


# --- prompts / schema <-> presets -------------------------------------------


def test_prompt_without_preset_is_violation(mod):
    out = mod.find_violations(["src/prompts/sigma_agent.md"])
    assert len(out) == 1
    assert "config/presets/" in out[0]


def test_nested_prompt_without_preset_is_violation(mod):
    assert len(mod.find_violations(["src/prompts/extractors/cmdline.md"])) == 1


def test_schema_without_preset_is_violation(mod):
    assert len(mod.find_violations(["src/config/workflow_config_schema.py"])) == 1


def test_prompt_with_preset_passes(mod):
    changed = ["src/prompts/sigma_agent.md", "config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-5.json"]
    assert mod.find_violations(changed) == []


def test_prompt_with_escape_label_passes(mod):
    assert mod.find_violations(["src/prompts/sigma_agent.md"], labels=[mod.LABEL_NO_PRESET_SYNC]) == []


def test_preset_alone_is_fine(mod):
    assert mod.find_violations(["config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-5.json"]) == []


# --- independence / hygiene --------------------------------------------------


def test_both_pairs_can_fail_together(mod):
    out = mod.find_violations(["src/database/models.py", "src/prompts/sigma_agent.md"])
    assert len(out) == 2


def test_escape_label_is_pair_specific(mod):
    out = mod.find_violations(
        ["src/database/models.py", "src/prompts/sigma_agent.md"],
        labels=[mod.LABEL_NO_MIGRATION],
    )
    assert len(out) == 1
    assert "config/presets/" in out[0]


def test_unrelated_changes_never_trip(mod):
    changed = ["README.md", "src/web/routes/sigma_queue.py", "tests/unit/test_x.py", ".github/workflows/lint.yml"]
    assert mod.find_violations(changed) == []


def test_labels_are_whitespace_tolerant(mod):
    assert mod.find_violations(["src/database/models.py"], labels=[" no-migration-needed ", ""]) == []


def test_empty_changeset_passes(mod):
    assert mod.find_violations([]) == []


# --- CLI ---------------------------------------------------------------------


def test_main_exit_codes(mod, monkeypatch):
    monkeypatch.setattr(mod, "changed_files_between", lambda base, head: ["src/database/models.py"])
    assert mod.main(["--base", "origin/x"]) == 1
    assert mod.main(["--base", "origin/x", "--labels", mod.LABEL_NO_MIGRATION]) == 0

    monkeypatch.setattr(mod, "changed_files_between", lambda base, head: ["README.md"])
    assert mod.main(["--base", "origin/x"]) == 0


def test_main_git_failure_exits_2(mod, monkeypatch):
    import subprocess

    def boom(base, head):
        raise subprocess.CalledProcessError(128, ["git"], stderr="fatal: bad revision")

    monkeypatch.setattr(mod, "changed_files_between", boom)
    assert mod.main(["--base", "origin/nope"]) == 2
