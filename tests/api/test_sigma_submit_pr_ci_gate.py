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
DUPLICATE_KEY = CLEAN.replace(
    "        Image|endswith: '\\tool.exe'\n",
    "        Image|endswith: '\\tool.exe'\n        Image|endswith: '\\other.exe'\n",
)
UNKNOWN_FIELD = CLEAN + "\nTier: Detection\nRobustness: 3\n"
UNKNOWN_LOGSOURCE = CLEAN.replace(
    "category: process_creation\n    product: windows", "category: audit\n    product: ibm_instana"
)


def _rule(rule_id: int, rule_yaml: str):
    return SimpleNamespace(
        id=rule_id,
        rule_origin="generated",
        status="approved",
        rule_yaml=rule_yaml,
        rule_metadata={"title": f"Rule {rule_id}"},
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
    ):
        db.return_value.get_session.return_value = session
        return call(), pr_service, session


@pytest.mark.parametrize(
    "bad_yaml,check,needle",
    [
        (DUPLICATE_KEY, "duplicate_key", "Image|endswith"),
        (UNKNOWN_FIELD, "blocking_validator", "Tier"),
        (UNKNOWN_LOGSOURCE, "blocking_validator", "LogsourceUnknown"),
    ],
    ids=["duplicate-key", "unknown-field", "unknown-logsource"],
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


def test_blocked_batch_has_no_git_or_db_side_effects(tmp_path):
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
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException):
            submit_pr_for_approved_rules(_request())
    pr_service.submit_pr.assert_not_called()
    session.commit.assert_not_called()
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
    result, pr_service, _ = _run(
        [_rule(1, UNKNOWN_LOGSOURCE)], tmp_path, lambda: submit_pr_for_approved_rules(_request())
    )
    assert result["success"] is True
    pr_service.submit_pr.assert_called_once()


def test_preflight_reports_failures_without_side_effects(tmp_path):
    rules = [_rule(1, CLEAN), _rule(2, UNKNOWN_FIELD)]
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
