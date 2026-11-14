from __future__ import annotations

from pathlib import Path

import pytest

from src.services.sigma_ci_parity import (
    check_rule_ci_parity,
    destination_blocking_config,
    toolchain_drift,
)

pytestmark = pytest.mark.unit

CLEAN_RULE = """title: Clean Windows Rule
id: 11111111-1111-4111-8111-111111111111
status: experimental
description: Detects a test binary launching from a temp directory.
author: Publisher
date: 2026-09-28
tags:
    - attack.execution
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        Image|endswith: '\\tool.exe'
    condition: selection
falsepositives:
    - Unknown
level: high
"""


def _kinds(findings):
    return {finding.check for finding in findings}


def test_clean_rule_has_no_findings():
    assert check_rule_ci_parity(CLEAN_RULE) == []


def test_duplicate_yaml_key_is_flagged_with_the_key_name():
    rule = CLEAN_RULE.replace(
        "        Image|endswith: '\\tool.exe'\n",
        "        Image|endswith: '\\tool.exe'\n        Image|endswith: '\\other.exe'\n",
    )
    findings = check_rule_ci_parity(rule)
    duplicates = [f for f in findings if f.check == "duplicate_key"]
    assert len(duplicates) == 1
    assert "Image|endswith" in duplicates[0].message
    assert "line" in duplicates[0].message


def test_trailing_article_annotations_are_flagged_as_unknown_fields():
    rule = CLEAN_RULE + "\nTier: Detection\nRobustness: 3\n"
    findings = check_rule_ci_parity(rule)
    unknown = [f for f in findings if f.check == "blocking_validator" and "UnknownField" in f.message]
    assert unknown, [f.message for f in findings]
    assert "Tier" in unknown[0].message and "Robustness" in unknown[0].message


def test_grounding_metadata_is_not_exempt_because_the_yaml_is_published_verbatim():
    findings = check_rule_ci_parity(CLEAN_RULE + "observables_used: [a]\n")
    assert any("observables_used" in f.message for f in findings)


UNKNOWN_LOGSOURCE_RULE = CLEAN_RULE.replace(
    "    category: process_creation\n    product: windows\n",
    "    category: audit\n    product: ibm_instana\n",
)


def test_unknown_logsource_is_flagged_under_the_bundled_blocking_config():
    findings = check_rule_ci_parity(UNKNOWN_LOGSOURCE_RULE)
    assert any("LogsourceUnknown" in f.message for f in findings), [f.message for f in findings]


def test_logsource_finding_is_compact_and_omits_unset_fields():
    [finding] = [f for f in check_rule_ci_parity(UNKNOWN_LOGSOURCE_RULE) if "LogsourceUnknown" in f.message]
    assert "logsource={category=audit, product=ibm_instana}" in finding.message
    assert "None" not in finding.message


def test_unknown_logsource_follows_the_destination_repos_config(tmp_path: Path):
    config = tmp_path / "validation-blocking.yml"
    config.write_text("validators:\n  - dangling_condition\n  - sigmahq_unknown_field\n", encoding="utf-8")
    assert check_rule_ci_parity(UNKNOWN_LOGSOURCE_RULE, config_path=config) == []


def test_unparseable_condition_is_a_parse_finding():
    rule = CLEAN_RULE.replace("condition: selection", "condition: selection and and")
    assert "parse" in _kinds(check_rule_ci_parity(rule))


def test_invalid_yaml_is_a_parse_finding_not_an_exception():
    findings = check_rule_ci_parity("title: x\nlogsource: [\n")
    assert _kinds(findings) == {"parse"}


def test_destination_config_prefers_repo_file_and_falls_back_to_bundled(tmp_path: Path):
    bundled = destination_blocking_config(tmp_path)
    assert bundled.name == "sigma_validation_blocking.yml"
    (tmp_path / ".sigma").mkdir()
    repo_config = tmp_path / ".sigma" / "validation-blocking.yml"
    repo_config.write_text("validators:\n  - dangling_condition\n", encoding="utf-8")
    assert destination_blocking_config(tmp_path) == repo_config


def test_toolchain_drift_reports_only_mismatched_pins(tmp_path: Path):
    (tmp_path / "requirements-ci.txt").write_text(
        f"# comment\npysigma==0.0.1\nPyYAML=={_installed('PyYAML')}\nnot-installed-package==1.0\n",
        encoding="utf-8",
    )
    drift = toolchain_drift(tmp_path)
    names = {item["package"].lower() for item in drift}
    assert "pysigma" in names
    assert "pyyaml" not in names
    assert "not-installed-package" not in names


def test_toolchain_drift_is_empty_without_a_requirements_file(tmp_path: Path):
    assert toolchain_drift(tmp_path) == []


def _installed(name: str) -> str:
    from importlib.metadata import version

    return version(name)
