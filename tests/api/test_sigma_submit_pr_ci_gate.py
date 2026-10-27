"""submit-pr must refuse a batch containing a rule the destination repo's CI would reject."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.source_sigma_import_service import DeliveryDecision
from src.web.routes.sigma_queue import preflight_submit_pr, submit_pr_for_approved_rules

pytestmark = pytest.mark.unit

CLEAN = """title: Clean Windows Rule
id: 11111111-1111-4111-8111-111111111111
status: experimental
description: Detects a test binary launching from a temp directory.
references:
    - https://example.test/report
author: Huntable CTI Studio
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
DUPLICATE_KEY = CLEAN.replace(
    "        Image|endswith: '\\tool.exe'\n",
    "        Image|endswith: '\\tool.exe'\n        Image|endswith: '\\other.exe'\n",
)
UNKNOWN_FIELD = CLEAN + "\nTier: Detection\nRobustness: 3\n"
# A Sigma-valid but unknown modifier: survives normalization, fails the CI parse step.
UNKNOWN_MODIFIER = CLEAN.replace("Image|endswith:", "Image|bogusmodifier:")
UNKNOWN_LOGSOURCE = CLEAN.replace(
    "category: process_creation\n    product: windows", "category: audit\n    product: ibm_instana"
)


def _rule(rule_id: int, rule_yaml: str):
    # Each queued rule carries its own Sigma id: a shared id is itself a publish blocker.
    rule_yaml = rule_yaml.replace("11111111-1111-4111-8111-111111111111", f"{rule_id:08d}-1111-4111-8111-111111111111")
    return SimpleNamespace(
        id=rule_id,
        rule_origin="generated",
        status="approved",
        rule_yaml=rule_yaml,
        rule_metadata={"title": f"Rule {rule_id}"},
        attribution=None,
        review_notes=None,
        article_id=1,
        pr_submitted=False,
        submitted_at=None,
        pr_url=None,
        pr_repository=None,
    )


def _request():
    request = MagicMock()
    request.state.identity = None
    return request


def _run(rules, repo_path: Path, call):
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rules
    pr_service = MagicMock()
    pr_service.repo_path = repo_path
    pr_service.submit_pr.return_value = {"success": True, "pr_url": "https://example/pr/1", "rules_count": len(rules)}
    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue.SigmaPRService", return_value=pr_service),
        patch(
            "src.web.routes.sigma_queue._source_delivery_decision",
            return_value=DeliveryDecision(True, "generated", "generated"),
        ),
        patch("src.web.routes.sigma_queue.AuditService"),
        patch("src.web.routes.sigma_queue._sigma_author_from_db", return_value="Huntable CTI Studio"),
    ):
        db.return_value.get_session.return_value = session
        return call(), pr_service, session


@pytest.mark.parametrize(
    "bad_yaml,check,needle",
    [
        (DUPLICATE_KEY, "duplicate_key", "Image|endswith"),
        (UNKNOWN_MODIFIER, "parse", "bogusmodifier"),
    ],
    ids=["duplicate-key", "unknown-modifier"],
)
def test_ci_failing_rule_blocks_batch_with_per_rule_reason(bad_yaml, check, needle, tmp_path):
    rules = [_rule(1, CLEAN), _rule(2, bad_yaml)]
    with pytest.raises(HTTPException) as exc:
        _run(rules, tmp_path, lambda: submit_pr_for_approved_rules(_request()))
    assert exc.value.status_code == 409
    failures = exc.value.detail["ci_failures"]
    assert [f["id"] for f in failures] == [2], "only the offending rule is reported"
    assert failures[0]["title"] == "Rule 2"
    assert any(f["check"] == check and needle in f["message"] for f in failures[0]["findings"])
    assert "CI" in exc.value.detail["message"]


def test_blocked_batch_has_no_git_side_effects_or_status_change(tmp_path):
    rules = [_rule(1, CLEAN), _rule(2, DUPLICATE_KEY)]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rules
    pr_service = MagicMock()
    pr_service.repo_path = tmp_path
    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue.SigmaPRService", return_value=pr_service),
        patch(
            "src.web.routes.sigma_queue._source_delivery_decision",
            return_value=DeliveryDecision(True, "generated", "generated"),
        ),
        patch("src.web.routes.sigma_queue.AuditService"),
        patch("src.web.routes.sigma_queue._sigma_author_from_db", return_value="Huntable CTI Studio"),
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException):
            submit_pr_for_approved_rules(_request())
    pr_service.submit_pr.assert_not_called()
    # Normalization is persisted before the gate runs (what is checked is what is published),
    # but a CI-blocked batch is neither submitted nor demoted.
    assert all(rule.status == "approved" and not rule.pr_submitted for rule in rules)


def test_clean_batch_reaches_the_pr_service(tmp_path):
    rules = [_rule(1, CLEAN)]
    result, pr_service, _ = _run(rules, tmp_path, lambda: submit_pr_for_approved_rules(_request()))
    assert result["success"] is True
    pr_service.submit_pr.assert_called_once()


def test_gate_follows_destination_repo_config_where_logsource_is_advisory(tmp_path):
    (tmp_path / ".sigma").mkdir()
    (tmp_path / ".sigma" / "validation-blocking.yml").write_text(
        "validators:\n  - dangling_condition\n  - sigmahq_unknown_field\n", encoding="utf-8"
    )
    # The destination's own layout table maps the logsource, so the rule is placeable.
    (tmp_path / ".huntable").mkdir()
    (tmp_path / ".huntable" / "rule-layout.yml").write_text(
        "version: 1\nlogsource_dirs:\n  - {product: ibm_instana, category: audit, dir: cloud/instana}\n",
        encoding="utf-8",
    )
    result, pr_service, _ = _run(
        [_rule(1, UNKNOWN_LOGSOURCE)], tmp_path, lambda: submit_pr_for_approved_rules(_request())
    )
    assert result["success"] is True
    pr_service.submit_pr.assert_called_once()


def test_preflight_reports_failures_without_side_effects(tmp_path):
    rules = [_rule(1, CLEAN), _rule(2, UNKNOWN_MODIFIER)]
    result, pr_service, session = _run(rules, tmp_path, preflight_submit_pr)
    assert result["ready"] is False
    assert result["rules_checked"] == 2
    assert [f["id"] for f in result["ci_failures"]] == [2]
    assert "toolchain_drift" in result
    pr_service.submit_pr.assert_not_called()
    session.commit.assert_not_called()


def test_preflight_ready_when_everything_passes(tmp_path):
    result, _, _ = _run([_rule(1, CLEAN)], tmp_path, preflight_submit_pr)
    assert result["ready"] is True
    assert result["ci_failures"] == []


# --- publish readiness: normalize + persist before the gate, demote what cannot publish ---

NO_REFERENCES = CLEAN.replace("references:\n    - https://example.test/report\n", "")
EMERGING_UNSORTED = CLEAN.replace(
    "    - attack.execution\n", "    - attack.execution\n    - detection.emerging-threats\n"
)


def test_stray_keys_are_stripped_and_persisted_before_the_gate(tmp_path):
    rule = _rule(1, UNKNOWN_FIELD)
    result, pr_service, session = _run([rule], tmp_path, lambda: submit_pr_for_approved_rules(_request()))
    assert result["success"] is True
    assert "Tier" not in rule.rule_yaml and "Robustness" not in rule.rule_yaml
    published = pr_service.submit_pr.call_args.args[0]
    assert published[0]["rule_yaml"] == rule.rule_yaml, "published YAML is byte-identical to the persisted row"
    assert rule.rule_metadata["publish_normalization"]["changes"]
    assert [n["id"] for n in result["normalized"]] == [1]


def test_not_ready_rule_is_demoted_and_rest_of_batch_proceeds(tmp_path):
    ready, missing = _rule(1, CLEAN), _rule(2, NO_REFERENCES)
    result, pr_service, session = _run([ready, missing], tmp_path, lambda: submit_pr_for_approved_rules(_request()))
    assert result["success"] is True
    assert [r["id"] for r in pr_service.submit_pr.call_args.args[0]] == [1]
    assert missing.status == "pending" and not missing.pr_submitted
    assert "Missing required references" in missing.review_notes
    assert missing.rule_metadata["publish_readiness"]["ready"] is False
    assert result["demoted"] == [{"id": 2, "title": "Clean Windows Rule", "reasons": ["Missing required references"]}]
    assert ready.status == "submitted"


def test_unmapped_logsource_is_demoted_not_filed_in_a_catch_all(tmp_path):
    rule = _rule(1, UNKNOWN_LOGSOURCE)
    result, pr_service, _ = _run([rule], tmp_path, lambda: submit_pr_for_approved_rules(_request()))
    assert result["success"] is False
    pr_service.submit_pr.assert_not_called()
    assert rule.status == "pending"
    assert "ibm_instana" in result["demoted"][0]["reasons"][0]


def test_demotion_is_audited(tmp_path):
    rules = [_rule(1, NO_REFERENCES)]
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = rules
    pr_service = MagicMock()
    pr_service.repo_path = tmp_path
    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue.SigmaPRService", return_value=pr_service),
        patch("src.web.routes.sigma_queue.AuditService") as audit,
        patch("src.web.routes.sigma_queue._sigma_author_from_db", return_value="Huntable CTI Studio"),
    ):
        db.return_value.get_session.return_value = session
        submit_pr_for_approved_rules(_request())
    events = [call.args[1] for call in audit.record_mandatory.call_args_list]
    assert [e.action for e in events] == ["sigma_queue.rule_reopened"]
    assert events[0].metadata["reason"] == "publish_readiness"
    session.commit.assert_called()


def test_preflight_lists_demotions_and_unsorted_warning_without_writing(tmp_path):
    missing, unsorted = _rule(1, NO_REFERENCES), _rule(2, EMERGING_UNSORTED)
    result, pr_service, session = _run([missing, unsorted], tmp_path, preflight_submit_pr)
    assert [d["id"] for d in result["demoted"]] == [1]
    assert result["warnings"][0]["id"] == 2
    assert result["warnings"][0]["path"] == "rules-emerging-threats/_unsorted/clean_windows_rule.yml"
    assert "_unsorted" in result["warnings"][0]["warnings"][0]
    assert result["ready"] is True, "the unsorted rule is a warning, not a blocker"
    assert missing.status == "approved" and "references" not in missing.rule_yaml
    session.commit.assert_not_called()
    pr_service.submit_pr.assert_not_called()
