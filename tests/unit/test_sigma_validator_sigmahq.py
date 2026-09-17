"""The in-app validator enforces the rules repository's blocking SigmaHQ validator set.

Before 2026-09-03 ``validate_sigma_rule`` ran pySigma parsing plus the Huntable policy
pass only. A rule using a field name that exists in no SigmaHQ logsource (``url``,
``ServerName``), ``service: sysmon`` without an EventID, or an unknown logsource parsed
cleanly, was approved in the queue, and then failed the blocking CI in
Huntable-SIGMA-Rules. These tests pin that the same validator set now runs here, that its
config file names only installed validators, and that the pipeline's own grounding keys
never trip it.
"""

from __future__ import annotations

import pytest
import yaml

from src.services import sigma_validator as sv
from src.services.sigma_validator import (
    SIGMA_GROUNDING_METADATA_FIELDS,
    SIGMAHQ_BLOCKING_CONFIG_PATH,
    validate_sigma_rule,
)

pytestmark = pytest.mark.unit

CLEAN_RULE = """title: PowerShell Download Cradle Executing Remote Script via IEX
id: 5f3c9a7e-1b2d-4c8e-9f0a-6d7e8b9c0a1b
status: experimental
description: Detects PowerShell retrieving a remote script and executing it in memory.
references:
  - https://example.com/report
author: Huntable CTI Studio
date: 2026-09-03
tags:
  - attack.execution
  - attack.t1059.001
logsource:
  category: process_creation
  product: windows
detection:
  selection_img:
    - Image|endswith: '\\powershell.exe'
    - OriginalFileName: 'PowerShell.EXE'
  selection_cli:
    CommandLine|contains|all:
      - 'DownloadString('
      - 'IEX'
  condition: all of selection_*
falsepositives:
  - Administrative scripts that bootstrap tooling from an internal repository
level: high
"""


def _with(rule: str, **replacements: str) -> str:
    out = rule
    for old, new in replacements.items():
        assert old in out, old
        out = out.replace(old, new)
    return out


def test_config_names_only_installed_validators():
    config = yaml.safe_load(SIGMAHQ_BLOCKING_CONFIG_PATH.read_text(encoding="utf-8"))
    validator, reason = sv._load_sigmahq_blocking_validator()
    assert validator is not None, reason
    assert validator is not sv._load_sigmahq_blocking_validator()[0], "must be a fresh instance per call"
    assert config["validators"], "blocking set must not be empty"
    assert "sigmahq_invalid_fieldname" in config["validators"]
    assert "sigmahq_sysmon_missing_eventid" in config["validators"]


def test_clean_rule_passes_with_empty_sigmahq_issue_list():
    result = validate_sigma_rule(CLEAN_RULE)
    assert result.is_valid, result.errors
    assert result.metadata["sigmahq"] == {"available": True, "reason": None, "issues": []}


def test_non_sigmahq_field_names_fail():
    rule = _with(
        CLEAN_RULE,
        **{"category: process_creation": "category: network_connection"},
    ).replace(
        "  selection_img:\n    - Image|endswith: '\\powershell.exe'\n    - OriginalFileName: 'PowerShell.EXE'\n"
        "  selection_cli:\n    CommandLine|contains|all:\n      - 'DownloadString('\n      - 'IEX'\n"
        "  condition: all of selection_*\n",
        "  selection:\n    url|contains: '/upload'\n    ServerName: null\n  condition: selection\n",
    )
    result = validate_sigma_rule(rule)
    assert result.metadata["pysigma"]["valid"] is True
    assert not result.is_valid
    flagged = {issue["details"].get("field") for issue in result.metadata["sigmahq"]["issues"]}
    assert {"url", "ServerName"} <= flagged
    assert any(err.startswith("SigmaHQ SigmahqInvalidFieldnameIssue") and "url" in err for err in result.errors)


def test_sysmon_service_without_eventid_fails():
    rule = """title: Sysmon Service Rule Without EventID
id: 5f3c9a7e-1b2d-4c8e-9f0a-6d7e8b9c0a1c
status: experimental
description: Detects a thing via the sysmon service logsource.
logsource:
  service: sysmon
  product: windows
detection:
  selection:
    Image|endswith: '\\x.exe'
  condition: selection
falsepositives:
  - Unknown administrative tooling
level: medium
"""
    result = validate_sigma_rule(rule)
    assert not result.is_valid
    assert any("SigmahqSysmonMissingEventid" in err for err in result.errors)


def test_unknown_logsource_fails():
    rule = _with(CLEAN_RULE, **{"category: process_creation": "category: proxy"})
    result = validate_sigma_rule(rule)
    assert not result.is_valid
    assert any("SigmahqLogsourceUnknown" in err for err in result.errors)


def test_same_rule_validated_twice_is_not_a_duplicate():
    assert validate_sigma_rule(CLEAN_RULE).is_valid
    second = validate_sigma_rule(CLEAN_RULE)
    assert second.is_valid, second.errors


def test_list_of_maps_selection_is_accepted_by_policy_layer():
    # The generation prompt's own example uses `selection_img:` as a list of maps.
    result = validate_sigma_rule(CLEAN_RULE)
    assert not any("Invalid search identifier" in err for err in result.errors)


def test_pipeline_grounding_keys_are_exempt():
    extra = "".join(f"{key}: placeholder\n" for key in sorted(SIGMA_GROUNDING_METADATA_FIELDS))
    result = validate_sigma_rule(CLEAN_RULE + extra)
    assert result.is_valid, result.errors
    assert result.metadata["sigmahq"]["issues"] == []


def test_foreign_custom_key_still_fails_next_to_pipeline_keys():
    result = validate_sigma_rule(CLEAN_RULE + "observables_used: [0]\nsiem_priority: 3\n")
    assert not result.is_valid
    unknown = [i for i in result.metadata["sigmahq"]["issues"] if i["issue"] == "SigmahqUnknownFieldIssue"]
    assert unknown and unknown[0]["details"]["fieldname"] == ["siem_priority"]


def test_layer_degrades_loudly_when_plugin_missing(monkeypatch):
    monkeypatch.setattr(sv, "PYSIGMA_VALIDATION_AVAILABLE", False)
    sv._load_sigmahq_blocking_config.cache_clear()
    try:
        result = validate_sigma_rule(CLEAN_RULE)
        assert result.is_valid
        assert result.metadata["sigmahq"]["available"] is False
        assert "unavailable" in result.metadata["sigmahq"]["reason"]
    finally:
        sv._load_sigmahq_blocking_config.cache_clear()


def test_canonical_sigma_rule_dict_strips_pipeline_keys_and_orders_fields():
    from src.services.sigma_validator import canonical_sigma_rule_dict

    rule = {
        "title": "T",
        "description": "Detects x",
        "id": "5f3c9a7e-1b2d-4c8e-9f0a-6d7e8b9c0a1b",
        "tags": ["attack.execution"],
        "level": "medium",
        "status": "experimental",
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {"selection": {"Image|endswith": "\\x.exe"}, "condition": "selection"},
        "generation_phase": "generation",
        "observables_used": [0],
        "observable_attribution": "grounded",
        "author": "Huntable CTI Studio",
        "date": "2026-09-03",
        "references": ["https://example.com"],
        "falsepositives": ["Admin tooling"],
        "custom_extra": "kept but last",
    }
    out = canonical_sigma_rule_dict(rule)
    assert list(out) == [
        "title",
        "id",
        "status",
        "description",
        "references",
        "author",
        "date",
        "tags",
        "logsource",
        "detection",
        "falsepositives",
        "level",
        "custom_extra",
    ]
    assert "generation_phase" not in out and "observables_used" not in out
