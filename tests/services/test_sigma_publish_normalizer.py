"""Publish metadata normalization: author, dates, tags, stray keys, required fields."""

from __future__ import annotations

from datetime import date

import pytest
import yaml

from src.services.sigma_publish_normalizer import (
    normalize_rule_yaml,
    normalize_tag,
    normalize_tags,
    resolve_canonical_author,
)

pytestmark = pytest.mark.unit

AUTHOR = "Huntable CTI Studio"
TODAY = date(2026, 10, 17)

BASE = """title: Suspicious Child Of Word
id: 4b5e9c2a-0000-4000-8000-000000000001
status: experimental
description: Detects a test.
references:
    - https://example.test/report
author: Huntable CTI Studio
date: 2026-10-01
tags:
    - attack.execution
    - attack.t1204.002
logsource:
    product: windows
    category: process_creation
detection:
    selection:
        ParentImage|endswith: '\\winword.exe'
        Image|endswith:
            - '\\cmd.exe'
            - '\\powershell.exe'
    condition: selection
falsepositives:
    - Unknown
level: high
"""


def _norm(text, **kwargs):
    kwargs.setdefault("canonical_author", AUTHOR)
    kwargs.setdefault("today", TODAY)
    return normalize_rule_yaml(text, **kwargs)


def _block(text: str, key: str) -> str:
    """The exact source lines of one top-level key block."""
    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{key}:"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i][:1] not in (" ", "\n", "#")), len(lines))
    return "".join(lines[start:end])


def test_clean_rule_is_returned_byte_identical():
    result = _norm(BASE)
    assert result.rule_yaml == BASE
    assert not result.changes and result.ready


def test_generated_rule_author_variants_become_the_configured_author():
    for variant in ("Huntable CTI Studio User", "Huntable", "Cybersecurity Detection Engineer"):
        result = _norm(BASE.replace("author: Huntable CTI Studio", f"author: {variant}"))
        assert yaml.safe_load(result.rule_yaml)["author"] == AUTHOR
        assert any("author" in change for change in result.changes)


def test_generated_rule_missing_author_is_filled():
    result = _norm(BASE.replace("author: Huntable CTI Studio\n", ""))
    assert yaml.safe_load(result.rule_yaml)["author"] == AUTHOR
    # Inserted in SigmaHQ field order, after references and before date.
    keys = list(yaml.safe_load(result.rule_yaml))
    assert keys.index("references") < keys.index("author") < keys.index("date")


def test_publisher_author_is_never_overwritten():
    text = BASE.replace("author: Huntable CTI Studio", "author: The Hunters Ledger")
    result = _norm(text, origin="source_provided", attribution="Someone Else")
    assert result.rule_yaml == text
    assert not any("author" in change for change in result.changes)


def test_publisher_missing_author_is_filled_from_attribution_only():
    text = BASE.replace("author: Huntable CTI Studio\n", "")
    result = _norm(text, origin="source_provided", attribution="The Hunters Ledger")
    assert yaml.safe_load(result.rule_yaml)["author"] == "The Hunters Ledger"
    missing = _norm(text, origin="source_provided", attribution=None)
    assert "Publisher rule has no author and no recorded attribution" in missing.problems


@pytest.mark.parametrize(
    "line,expected",
    [("date: 2024/01/15", "2024-01-15"), ("date: '2026/09/06'", "2026-09-06")],
)
def test_slash_dates_become_iso(line, expected):
    result = _norm(BASE.replace("date: 2026-10-01", line))
    assert f"date: {expected}\n" in result.rule_yaml


def test_missing_date_becomes_today():
    result = _norm(BASE.replace("date: 2026-10-01\n", ""))
    assert "date: 2026-10-17\n" in result.rule_yaml


def test_quoted_iso_date_is_left_alone():
    text = BASE.replace("date: 2026-10-01", "date: '2026-10-01'")
    assert _norm(text).rule_yaml == text


def test_unparseable_date_is_a_problem():
    result = _norm(BASE.replace("date: 2026-10-01", "date: last tuesday"))
    assert any("not a YYYY-MM-DD date" in p for p in result.problems)


def test_modified_is_dropped_on_first_publish_of_a_generated_rule():
    text = BASE.replace("date: 2026-10-01\n", "date: 2026-10-01\nmodified: 2026-10-05\n")
    assert "modified" not in yaml.safe_load(_norm(text).rule_yaml)


def test_modified_equal_to_date_is_dropped_even_in_migration():
    text = BASE.replace("date: 2026-10-01\n", "date: 2024/01/15\nmodified: 2024/01/15\n")
    result = _norm(text, first_publish=False)
    assert "modified" not in yaml.safe_load(result.rule_yaml)


def test_later_modified_is_kept_in_migration_and_on_untouched_publisher_rules():
    text = BASE.replace("date: 2026-10-01\n", "date: 2026-10-01\nmodified: 2026-10-09\n")
    migrated = _norm(text.replace("2026-10-09", "2026/10/09"), first_publish=False)
    assert yaml.safe_load(migrated.rule_yaml)["modified"] == date(2026, 10, 9)
    publisher = text.replace("author: Huntable CTI Studio", "author: x")
    assert _norm(publisher, origin="source_provided").rule_yaml == publisher


def test_publisher_modified_reformat_counts_as_a_change_and_takes_the_edit_date():
    text = BASE.replace("author: Huntable CTI Studio", "author: x").replace(
        "date: 2026-10-01\n", "date: 2026-10-01\nmodified: 2026/10/09\n"
    )
    result = _norm(text, origin="source_provided", edit_date=date(2026, 10, 20))
    assert yaml.safe_load(result.rule_yaml)["modified"] == date(2026, 10, 20)


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("attack.defense_evasion", "attack.defense-evasion"),
        ("attack.command_and_control", "attack.command-and-control"),
        ("ATTACK.T1059.001", "attack.t1059.001"),
        ("attack.g0016", "attack.g0016"),
        ("attack.s0154", "attack.s0154"),
        ("stp.2", "stp.2"),
        ("stp.3a", "stp.3a"),
        ("cve.2026.20817", "cve.2026-20817"),
        ("cve.2026-20817", "cve.2026-20817"),
        ("detection.emerging-threats", "detection.emerging-threats"),
        ("tlp.clear", "tlp.clear"),
        ("car.2016-04-005", "car.2016-04-005"),
        ("d3fend.d3-pm", "d3fend.d3-pm"),
        ("mitre.t1059", None),
        ("huntable.reviewed", None),
        ("notag", None),
        ("attack.", None),
        (42, None),
    ],
)
def test_normalize_tag(tag, expected):
    assert normalize_tag(tag) == expected


def test_normalize_tags_dedupes_and_reports():
    tags, notes = normalize_tags(["attack.defense_evasion", "attack.defense-evasion", "stp.2", "bogus.x"])
    assert tags == ["attack.defense-evasion", "stp.2"]
    assert any("dropped unknown" in n for n in notes)
    assert any("duplicate" in n for n in notes)


def test_tag_fixes_keep_file_sequence_indent_and_stp():
    text = BASE.replace("    - attack.execution\n", "    - attack.defense_evasion\n    - stp.2\n    - junk.tag\n")
    result = _norm(text)
    assert "    - attack.defense-evasion\n    - stp.2\n    - attack.t1204.002\n" in result.rule_yaml
    assert "junk.tag" not in result.rule_yaml


@pytest.mark.parametrize("key", ["name", "generation_phase", "observables_used", "Tier"])
def test_non_published_keys_are_stripped(key):
    text = BASE.replace("status: experimental\n", f"status: experimental\n{key}: something\n")
    result = _norm(text)
    assert key not in yaml.safe_load(result.rule_yaml)
    assert result.rule_yaml == BASE


@pytest.mark.parametrize("key", ["references", "falsepositives", "tags"])
def test_missing_required_list_is_a_problem(key):
    loaded = yaml.safe_load(BASE)
    loaded.pop(key)
    result = _norm(yaml.safe_dump(loaded, sort_keys=False))
    assert f"Missing required {key}" in result.problems
    assert not result.ready


def test_tags_that_all_drop_leave_the_rule_not_ready():
    result = _norm(BASE.replace("    - attack.execution\n    - attack.t1204.002\n", "    - bogus.one\n"))
    assert "Missing required tags" in result.problems


def test_logsource_service_without_category_is_kept():
    text = BASE.replace(
        "    product: windows\n    category: process_creation\n", "    product: windows\n    service: security\n"
    )
    result = _norm(text)
    assert yaml.safe_load(result.rule_yaml)["logsource"] == {"product": "windows", "service": "security"}


def test_protected_blocks_keep_their_exact_bytes():
    messy = (
        BASE.replace("author: Huntable CTI Studio", "author: Huntable")
        .replace("date: 2026-10-01", "date: 2026/10/01")
        .replace("    - attack.execution\n", "    - attack.defense_evasion\n")
        + "name: leftover\n"
    )
    result = _norm(messy)
    assert result.changes
    for key in ("title", "id", "logsource", "detection"):
        assert _block(result.rule_yaml, key) == _block(BASE, key)


def test_multi_document_yaml_is_a_problem_and_unchanged():
    text = BASE + "---\n" + BASE
    result = _norm(text)
    assert result.rule_yaml == text
    assert result.problems == ["Expected exactly one Sigma rule mapping in the YAML"]


def test_flow_style_top_level_is_not_block_edited():
    text = "{title: x, id: y, author: Huntable, logsource: {product: windows}, detection: {condition: s}}\n"
    result = _norm(text)
    assert result.rule_yaml == text
    assert any("normalize by hand" in p for p in result.problems)


def test_normalization_is_idempotent():
    messy = BASE.replace("author: Huntable CTI Studio", "author: Huntable").replace(
        "date: 2026-10-01", "date: 2026/10/01"
    )
    once = _norm(messy).rule_yaml
    twice = _norm(once)
    assert twice.rule_yaml == once and not twice.changes


def test_resolve_canonical_author_prefers_setting():
    from unittest.mock import MagicMock

    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    assert resolve_canonical_author(session) == AUTHOR
    assert resolve_canonical_author(None) == AUTHOR
    row = MagicMock()
    row.value = "  Detection Team  "
    session.query.return_value.filter.return_value.first.return_value = row
    assert resolve_canonical_author(session) == "Detection Team"


def test_changed_publisher_rule_is_marked_modified():
    text = BASE.replace("author: Huntable CTI Studio", "author: The Hunters Ledger") + "name: leftover\n"
    result = _norm(text, origin="source_provided", attribution="x", edit_date=date(2026, 10, 20))
    loaded = yaml.safe_load(result.rule_yaml)
    assert loaded["modified"] == date(2026, 10, 20)
    assert loaded["author"] == "The Hunters Ledger"
    assert "name" not in loaded
    keys = list(loaded)
    assert keys.index("date") < keys.index("modified") < keys.index("tags")


def test_unchanged_publisher_rule_gets_no_modified():
    text = BASE.replace("author: Huntable CTI Studio", "author: The Hunters Ledger")
    assert "modified" not in yaml.safe_load(_norm(text, origin="source_provided").rule_yaml)


def test_generated_rule_changes_do_not_add_modified():
    result = _norm(BASE.replace("author: Huntable CTI Studio", "author: Huntable"))
    assert "modified" not in yaml.safe_load(result.rule_yaml)


def test_missing_final_newline_is_added_without_marking_a_publisher_change():
    text = BASE.replace("author: Huntable CTI Studio", "author: x").rstrip("\n")
    result = _norm(text, origin="source_provided")
    assert result.rule_yaml == text + "\n"
    assert result.changes == ["added the missing final newline"]
    assert "modified" not in yaml.safe_load(result.rule_yaml)


def test_block_edit_output_always_ends_with_newline():
    text = BASE.replace("author: Huntable CTI Studio", "author: Huntable").rstrip("\n")
    assert _norm(text).rule_yaml.endswith("level: high\n")
