"""The rules repository's CI layout check and the one-time layout migration.

``scripts/sigma_repo_ci/check_rule_layout.py`` is vendored into Huntable-SIGMA-Rules and
cannot import CTI Studio, so these tests pin its slug and directory logic to the
publisher's: a rule CTI Studio places must pass the repository's CI.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from src.services.sigma_publish_layout import BUNDLED_LAYOUT, load_rule_layout, logsource_dir, slugify_title

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


check = _load("check_rule_layout", "scripts/sigma_repo_ci/check_rule_layout.py")
migrate = _load("migrate_sigma_repo_layout", "scripts/migrate_sigma_repo_layout.py")

TITLES = [
    "AMSI Bypass via Suspicious amsi.dll Load from Non-Standard Path",
    "Bloody Wolf: NetSupport RAT Persistence via Registry Run Key (T1547.001)",
    "Instana API Enumeration via Stolen JWT from Non-Management-Platform Source (ARPA Observability Harvester)",
    "PowerShell New-Item creating directory in C:\\Temp",
    "Caf\u00e9 \u2014 Suspicious Run",
    "XWorm V5.6 Operator Configuration Registry Key Write",
    "",
]


@pytest.mark.parametrize("title", TITLES)
def test_ci_slug_matches_publisher_slug(title):
    assert check.slugify_title(title) == slugify_title(title)


def test_ci_logsource_lookup_matches_publisher_for_every_table_row():
    app_layout = load_rule_layout(None)
    data = yaml.safe_load(BUNDLED_LAYOUT.read_text(encoding="utf-8"))
    for entry in data["logsource_dirs"]:
        logsource = {k: entry[k] for k in ("product", "category", "service") if k in entry}
        assert check.logsource_dir(logsource, _ci_layout()) == logsource_dir(logsource, app_layout)


def _ci_layout():
    data = yaml.safe_load(BUNDLED_LAYOUT.read_text(encoding="utf-8"))
    return {
        "generic_root": data["generic_root"],
        "emerging_threats_root": data["emerging_threats_root"],
        "dirs": {
            (check._norm(e.get("product")), check._norm(e.get("category")), check._norm(e.get("service"))): e["dir"]
            for e in data["logsource_dirs"]
        },
    }


RULE = """title: Suspicious Child Of Word
id: 4b5e9c2a-0000-4000-8000-000000000001
status: experimental
description: Detects a test.
references:
    - https://example.test/report
author: Huntable CTI Studio
date: 2026-10-01
tags:
    - attack.execution
logsource:
    product: windows
    category: process_creation
detection:
    selection:
        Image|endswith: '\\\\cmd.exe'
    condition: selection
falsepositives:
    - Unknown
level: high
"""


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / ".huntable").mkdir(parents=True, exist_ok=True)
    shutil.copy(BUNDLED_LAYOUT, tmp_path / ".huntable" / "rule-layout.yml")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _errors(repo: Path) -> list[str]:
    layout = check.load_layout(repo)
    paths = sorted(
        p for top in ("rules", "rules-emerging-threats") if (repo / top).is_dir() for p in (repo / top).rglob("*.yml")
    )
    return [e for p in paths for e in check.check_rule(p, repo, layout)]


def test_ci_accepts_a_correctly_placed_generic_rule(tmp_path):
    repo = _repo(tmp_path, {"rules/windows/process_creation/suspicious_child_of_word.yml": RULE})
    assert _errors(repo) == []
    assert check.main(["x", str(repo)]) == 0


def test_ci_accepts_collision_suffix_and_emerging_threat_family(tmp_path):
    emerging = RULE.replace("    - attack.execution\n", "    - attack.execution\n    - detection.emerging-threats\n")
    repo = _repo(
        tmp_path,
        {
            "rules/windows/process_creation/suspicious_child_of_word_4b5e9c2a.yml": RULE,
            "rules-emerging-threats/xworm/suspicious_child_of_word.yml": emerging,
            "rules-emerging-threats/_unsorted/suspicious_child_of_word.yml": emerging,
        },
    )
    assert _errors(repo) == []


@pytest.mark.parametrize(
    "rel,text,needle",
    [
        ("rules/windows/suspicious_child_of_word.yml", RULE, "should be in rules/windows/process_creation/"),
        ("rules/windows/process_creation/wrong_name.yml", RULE, "filename should be suspicious_child_of_word.yml"),
        (
            "rules/windows/process_creation/suspicious_child_of_word.yml",
            RULE.replace("date: 2026-10-01", "date: 2026/10/01"),
            "is not YYYY-MM-DD",
        ),
        (
            "rules/windows/process_creation/suspicious_child_of_word.yml",
            RULE.replace("attack.execution", "attack.defense_evasion"),
            "attack.<tactic-with-hyphens>",
        ),
        (
            "rules/windows/process_creation/suspicious_child_of_word.yml",
            RULE.replace("attack.execution", "bogus.tag"),
            "unknown namespace",
        ),
        (
            "rules/windows/process_creation/suspicious_child_of_word.yml",
            RULE.replace("references:\n    - https://example.test/report\n", ""),
            "missing required references",
        ),
        (
            "rules/windows/process_creation/suspicious_child_of_word.yml",
            RULE.replace("category: process_creation", "category: nothing_maps"),
            "has no directory",
        ),
        (
            "rules-emerging-threats/Bad_Family/suspicious_child_of_word.yml",
            RULE.replace("    - attack.execution\n", "    - detection.emerging-threats\n"),
            "belong in rules-emerging-threats/<family>/",
        ),
    ],
)
def test_ci_rejects_layout_and_metadata_violations(tmp_path, rel, text, needle):
    repo = _repo(tmp_path, {rel: text})
    assert any(needle in error for error in _errors(repo)), _errors(repo)


def test_ci_keeps_stp_tags(tmp_path):
    text = RULE.replace("    - attack.execution\n", "    - attack.execution\n    - stp.2\n")
    repo = _repo(tmp_path, {"rules/windows/process_creation/suspicious_child_of_word.yml": text})
    assert _errors(repo) == []


# --- migration ---


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def legacy_repo(tmp_path):
    repo = tmp_path / "rules-repo"
    files = {
        "rules/windows/suspicious_child_of_word.yml": RULE.replace(
            "author: Huntable CTI Studio", "author: Huntable"
        ).replace("date: 2026-10-01", "date: 2026/10/01")
        + "name: leftover\n",
        "rules/windows/xworm_run_key.yml": RULE.replace("Suspicious Child Of Word", "XWorm Run Key")
        .replace("4b5e9c2a-0000-4000-8000-000000000001", "5c6f0d3b-0000-4000-8000-000000000002")
        .replace("author: Huntable CTI Studio", "author: The Hunters Ledger")
        .replace("    - attack.execution\n", "    - attack.persistence\n    - detection.emerging-threats\n"),
        "rules/windows/odd_emerging.yml": RULE.replace("Suspicious Child Of Word", "Odd Emerging Thing")
        .replace("4b5e9c2a-0000-4000-8000-000000000001", "6d7a1e4c-0000-4000-8000-000000000003")
        .replace("    - attack.execution\n", "    - attack.execution\n    - detection.emerging-threats\n"),
        "rules/linux/.gitkeep": "",
    }
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "test@example.test")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "legacy layout")
    return repo


def test_migration_dry_run_plans_moves_unsorted_and_metadata_without_writing(legacy_repo):
    before = _git(legacy_repo, "status", "--porcelain")
    plans, layout = migrate.build_plan(
        legacy_repo, author="Huntable CTI Studio", today=date(2026, 10, 17), provenance={}
    )
    by_old = {str(p.old): p for p in plans}
    assert str(by_old["rules/windows/suspicious_child_of_word.yml"].new) == (
        "rules/windows/process_creation/suspicious_child_of_word.yml"
    )
    assert str(by_old["rules/windows/xworm_run_key.yml"].new) == "rules-emerging-threats/xworm/xworm_run_key.yml"
    unsorted = by_old["rules/windows/odd_emerging.yml"]
    assert str(unsorted.new) == "rules-emerging-threats/_unsorted/odd_emerging_thing.yml"
    generic = by_old["rules/windows/suspicious_child_of_word.yml"]
    assert any("author" in c for c in generic.changes) and any("'name'" in c for c in generic.changes)
    # Publisher author (no queue row, non-internal author) is kept.
    assert not any("author" in c for c in by_old["rules/windows/xworm_run_key.yml"].changes)
    report = migrate.render_report(plans, layout, legacy_repo)
    assert "## `_unsorted` emerging-threat rules (1)" in report
    assert "| filename collisions (id suffix applied) | 0 |" in report
    assert _git(legacy_repo, "status", "--porcelain") == before


def test_migration_apply_makes_a_rename_only_commit_then_a_metadata_commit(legacy_repo):
    plans, layout = migrate.build_plan(
        legacy_repo, author="Huntable CTI Studio", today=date(2026, 10, 17), provenance={}
    )
    migrate.apply_plan(legacy_repo, plans, "chore/layout", layout)

    assert _git(legacy_repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "chore/layout"
    subjects = _git(legacy_repo, "log", "--format=%s", "-3").splitlines()
    assert subjects[:2] == [
        "chore(rules): normalize rule metadata",
        "chore(rules): move rules into the SigmaHQ-style layout",
    ]
    moves = _git(legacy_repo, "show", "-M", "--summary", "--format=", "HEAD~1")
    assert moves.count("(100%)") == 3, moves
    assert "delete mode 100644 rules/linux/.gitkeep" in moves
    numstat = _git(legacy_repo, "show", "-M", "--numstat", "--format=", "HEAD~1")
    assert all(line.startswith("0\t0\t") for line in numstat.splitlines() if line), numstat

    moved = legacy_repo / "rules/windows/process_creation/suspicious_child_of_word.yml"
    loaded = yaml.safe_load(moved.read_text(encoding="utf-8"))
    assert loaded["author"] == "Huntable CTI Studio" and "name" not in loaded
    assert loaded["detection"] == yaml.safe_load(RULE)["detection"]
    assert not (legacy_repo / "rules/linux").exists()


def test_migration_apply_refuses_a_dirty_tree(legacy_repo):
    (legacy_repo / "stray.txt").write_text("x", encoding="utf-8")
    plans, layout = migrate.build_plan(
        legacy_repo, author="Huntable CTI Studio", today=date(2026, 10, 17), provenance={}
    )
    with pytest.raises(SystemExit, match="uncommitted"):
        migrate.apply_plan(legacy_repo, plans, "chore/layout", layout)


def test_migration_blocks_on_unmapped_logsource(legacy_repo):
    bad = legacy_repo / "rules/windows/unmapped.yml"
    bad.write_text(
        RULE.replace("4b5e9c2a-0000-4000-8000-000000000001", "7e8b2f5d-0000-4000-8000-000000000004")
        .replace("Suspicious Child Of Word", "Unmapped Rule")
        .replace("category: process_creation", "category: nothing_maps"),
        encoding="utf-8",
    )
    plans, layout = migrate.build_plan(
        legacy_repo, author="Huntable CTI Studio", today=date(2026, 10, 17), provenance={}
    )
    assert any(p.errors for p in plans)
    with pytest.raises(SystemExit, match="blocking errors"):
        migrate.apply_plan(legacy_repo, plans, "chore/layout", layout)
