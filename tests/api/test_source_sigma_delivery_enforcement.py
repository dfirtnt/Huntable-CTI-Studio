from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.source_sigma_import_service import DeliveryDecision
from src.web.routes.sigma_queue import (
    BulkActionRequest,
    QueueUpdateRequest,
    approve_queued_rule,
    bulk_action_queued_rules,
    submit_pr_for_approved_rules,
)

pytestmark = pytest.mark.unit


def _request():
    request = MagicMock()
    request.state.identity = None
    return request


def _session_with_rules(rules):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = rules[0] if rules else None
    session.query.return_value.filter.return_value.all.return_value = rules
    return session


def _rule(rule_id: int, *, origin="source_provided", status="local_review_only"):
    return SimpleNamespace(
        id=rule_id,
        rule_origin=origin,
        status=status,
        rule_yaml="title: Test\nlogsource: {product: windows}\ndetection: {condition: selection}\n",
        article_id=1,
        pr_submitted=False,
        submitted_at=None,
        review_notes=None,
        reviewed_by=None,
        reviewed_at=None,
        pr_url=None,
        pr_repository=None,
    )


def _blocked(*_args, **_kwargs):
    return DeliveryDecision(False, "No explicit source license or permission is recorded.", "missing_license")


def test_single_approval_rejects_local_only_source_server_side():
    rule = _rule(1)
    session = _session_with_rules([rule])
    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue._source_delivery_decision", side_effect=_blocked),
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException) as exc:
            approve_queued_rule(_request(), 1, QueueUpdateRequest(status="approved"))
    assert exc.value.status_code == 409
    assert rule.status == "local_review_only"
    session.commit.assert_not_called()


def test_mixed_bulk_approval_fails_before_any_status_mutation():
    generated = _rule(1, origin="generated", status="pending")
    blocked = _rule(2)
    session = _session_with_rules([generated, blocked])

    def decision(rule, *_args):
        if rule.id == 2:
            return _blocked()
        return DeliveryDecision(True, "generated", "generated")

    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue._source_delivery_decision", side_effect=decision),
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException) as exc:
            bulk_action_queued_rules(_request(), BulkActionRequest(ids=[1, 2], action="approve"))
    assert exc.value.status_code == 409
    assert generated.status == "pending"
    assert blocked.status == "local_review_only"
    session.commit.assert_not_called()


def test_mixed_pr_batch_fails_atomically_without_calling_pr_service():
    generated = _rule(1, origin="generated", status="approved")
    blocked = _rule(2, status="approved")
    session = _session_with_rules([generated, blocked])
    pr_service = MagicMock()
    pr_service.repo_path = "/tmp/destination"

    def decision(rule, *_args):
        if rule.id == 2:
            return _blocked()
        return DeliveryDecision(True, "generated", "generated")

    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch("src.web.routes.sigma_queue.SigmaPRService", return_value=pr_service),
        patch("src.web.routes.sigma_queue._source_delivery_decision", side_effect=decision),
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException) as exc:
            submit_pr_for_approved_rules(_request())
    assert exc.value.status_code == 409
    pr_service.submit_pr.assert_not_called()
    session.commit.assert_not_called()


def test_source_yaml_is_immutable_through_approval_payload():
    rule = _rule(3, status="pending")
    session = _session_with_rules([rule])
    with (
        patch("src.web.routes.sigma_queue.DatabaseManager") as db,
        patch(
            "src.web.routes.sigma_queue._source_delivery_decision",
            return_value=DeliveryDecision(True, "allowlisted", "allowlist"),
        ),
    ):
        db.return_value.get_session.return_value = session
        with pytest.raises(HTTPException) as exc:
            approve_queued_rule(
                _request(),
                3,
                QueueUpdateRequest(status="approved", rule_yaml=rule.rule_yaml + "level: high\n"),
            )
    assert exc.value.status_code == 409
    session.commit.assert_not_called()
