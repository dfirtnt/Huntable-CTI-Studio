"""Queued Sigma rules keep their submitted YAML and are not scored against themselves.

Reported on queue rows #962 and #984 (since reset away): after their PR merged and
the customer repository synced, each scored 1.0 against its own ``cust-<id>`` copy,
hiding real duplicates. Their ``rule_yaml`` had also been rewritten days after
``submitted_at`` -- the queue's Validate and Similar Rules buttons re-save the modal
text whenever it differs from the stored YAML -- and ``rule_metadata.title`` no
longer matched the YAML title.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.services.sigma_novelty_service import SigmaNoveltyService, customer_copy_rule_id
from src.web.routes import sigma_queue
from src.web.routes.sigma_queue import (
    QueueUpdateRequest,
    RuleYamlUpdateRequest,
    _apply_rule_yaml,
    approve_queued_rule,
    get_similar_rules_for_queued_rule,
    reject_queued_rule,
    update_rule_yaml,
)

pytestmark = pytest.mark.unit

ORIGINAL_YAML = """title: Original Title
id: 5b1f5c1e-0000-4000-8000-000000000001
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    Image|endswith: '\\\\wscript.exe'
  condition: selection
"""
EDITED_YAML = ORIGINAL_YAML.replace("Original Title", "Edited Title")


def _queued_row(*, submitted: bool = False, pr_flag_only: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        rule_yaml=ORIGINAL_YAML,
        rule_metadata={"title": "Original Title", "canonical_class": "windows.process_creation"},
        pr_submitted=submitted or pr_flag_only,
        submitted_at=datetime(2026, 6, 2) if submitted else None,
        status="submitted" if submitted else "pending",
        review_notes=None,
        reviewed_at=None,
        reviewed_by=None,
        pr_url=None,
        pr_repository=None,
    )


# --- the write guard and title sync -------------------------------------------------


def test_unsubmitted_edit_replaces_yaml_and_syncs_the_header_title():
    row = _queued_row()

    _apply_rule_yaml(row, EDITED_YAML)

    assert row.rule_yaml == EDITED_YAML
    assert row.rule_metadata["title"] == "Edited Title"
    assert row.rule_metadata["canonical_class"] == "windows.process_creation", "other metadata must survive"


def test_unparseable_edit_is_stored_but_leaves_the_title_alone():
    row = _queued_row()

    _apply_rule_yaml(row, "title: [unclosed")

    assert row.rule_yaml == "title: [unclosed"
    assert row.rule_metadata["title"] == "Original Title"


@pytest.mark.parametrize("state", ["submitted", "pr_flag_only"])
def test_submitted_rule_yaml_cannot_be_rewritten(state):
    row = _queued_row(submitted=state == "submitted", pr_flag_only=state == "pr_flag_only")

    with pytest.raises(HTTPException) as exc:
        _apply_rule_yaml(row, EDITED_YAML)

    assert exc.value.status_code == 409
    assert row.rule_yaml == ORIGINAL_YAML
    assert row.rule_metadata["title"] == "Original Title"


def test_resaving_identical_yaml_on_a_submitted_rule_is_a_no_op():
    row = _queued_row(submitted=True)

    _apply_rule_yaml(row, ORIGINAL_YAML)

    assert row.rule_yaml == ORIGINAL_YAML


# --- every route that writes YAML goes through the guard --------------------------------


@pytest.fixture
def routed_row(monkeypatch):
    """Point the queue routes at one in-memory row; capture commits and audit writes."""
    row = _queued_row(submitted=True)
    session = Mock()
    session.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(sigma_queue, "DatabaseManager", lambda: SimpleNamespace(get_session=lambda: session))
    monkeypatch.setattr(sigma_queue, "_sigma_author_from_db", lambda _session: "reviewer")
    audit = Mock()
    monkeypatch.setattr(sigma_queue.AuditService, "record_mandatory", audit)
    return row, session, audit


def _request(json_body=None):
    async def _json():
        return json_body

    return SimpleNamespace(json=_json, query_params={}, state=SimpleNamespace(identity=None), client=None, headers={})


def test_put_yaml_on_a_submitted_rule_returns_409_without_committing(routed_row):
    row, session, audit = routed_row

    with pytest.raises(HTTPException) as exc:
        update_rule_yaml(_request(), 42, RuleYamlUpdateRequest(rule_yaml=EDITED_YAML))

    assert exc.value.status_code == 409
    assert row.rule_yaml == ORIGINAL_YAML
    session.commit.assert_not_called()
    audit.assert_not_called()


def test_approve_with_yaml_on_a_submitted_rule_returns_409_without_committing(routed_row):
    row, session, _audit = routed_row

    with pytest.raises(HTTPException) as exc:
        approve_queued_rule(_request(), 42, QueueUpdateRequest(rule_yaml=EDITED_YAML))

    assert exc.value.status_code == 409
    assert row.rule_yaml == ORIGINAL_YAML
    session.commit.assert_not_called()


def test_reject_with_yaml_on_a_submitted_rule_returns_409_without_committing(routed_row):
    """The reject body is parsed inside a broad fallback; the 409 must not be swallowed by it."""
    row, session, _audit = routed_row

    with pytest.raises(HTTPException) as exc:
        asyncio.run(reject_queued_rule(_request({"rule_yaml": EDITED_YAML, "review_notes": "x"}), 42))

    assert exc.value.status_code == 409
    assert row.rule_yaml == ORIGINAL_YAML
    assert row.status == "submitted"
    session.commit.assert_not_called()


# --- self-match exclusion -----------------------------------------------------------------


def test_customer_copy_rule_id_follows_the_sync_prefix():
    assert customer_copy_rule_id({"id": "abc-123"}) == "cust-abc-123"
    assert customer_copy_rule_id({"id": "  abc-123 "}) == "cust-abc-123"
    assert customer_copy_rule_id({"id": None}) is None
    assert customer_copy_rule_id({"id": "  "}) is None
    assert customer_copy_rule_id({"title": "no id"}) is None


def test_assess_novelty_asks_retrieval_to_skip_the_rules_own_customer_copy():
    service = SigmaNoveltyService(db_session=Mock())
    service.retrieve_candidates = Mock(return_value=[])

    service.assess_novelty(
        {
            "id": "5b1f5c1e-0000-4000-8000-000000000001",
            "title": "t",
            "logsource": {"category": "process_creation", "product": "windows"},
            "detection": {"selection": {"Image|endswith": "\\wscript.exe"}, "condition": "selection"},
        }
    )

    assert (
        service.retrieve_candidates.call_args.kwargs["exclude_rule_id"] == "cust-5b1f5c1e-0000-4000-8000-000000000001"
    )


def test_similar_rules_endpoint_passes_the_yaml_id_into_scoring(monkeypatch):
    row = _queued_row(submitted=True)
    session = Mock()
    session.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(sigma_queue, "DatabaseManager", lambda: SimpleNamespace(get_session=lambda: session))

    captured = {}

    class _StopAfterCapture(Exception):
        pass

    def _capture(proposed_rule, threshold):
        captured.update(proposed_rule)
        raise _StopAfterCapture

    with patch.object(sigma_queue, "SigmaMatchingService") as matching_cls:
        matching_cls.return_value.assess_rule_novelty.side_effect = _capture
        with pytest.raises(HTTPException):
            get_similar_rules_for_queued_rule(_request(), 42)

    assert captured["id"] == "5b1f5c1e-0000-4000-8000-000000000001"
