"""Rule sourcing for POST /api/articles/{article_id}/sigma-matches.

The route used to read its rules from ``article_metadata["sigma_rules"]``, a key written
only by the manual ``/generate-sigma`` endpoint. That endpoint was removed and the live
workflow queues its rules instead, so the route answered "generate rules first" for every
article the pipeline had actually produced rules for. It now reads the Sigma queue.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.web.routes.ai import _queued_rules_for_article

pytestmark = pytest.mark.unit


def _row(row_id: int, yaml_text: str) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, rule_yaml=yaml_text)


def _patched_queue(rows: list[SimpleNamespace]):
    """Patch DatabaseManager so the helper's query chain yields *rows*."""
    query = Mock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = rows

    session = Mock()
    session.query.return_value = query

    manager = Mock()
    manager.get_session.return_value = session
    return patch("src.database.manager.DatabaseManager", return_value=manager), session


def test_returns_parsed_rules_in_row_order():
    rows = [
        _row(1, "title: First\nlogsource:\n  category: process_creation\ndetection:\n  condition: selection\n"),
        _row(2, "title: Second\nlogsource:\n  category: dns_query\ndetection:\n  condition: selection\n"),
    ]
    patcher, session = _patched_queue(rows)
    with patcher:
        rules = _queued_rules_for_article(42)

    assert [r["title"] for r in rules] == ["First", "Second"]
    assert rules[0]["logsource"]["category"] == "process_creation"
    session.close.assert_called_once()


def test_unparseable_row_is_skipped_not_fatal():
    rows = [
        _row(1, "title: Good\ndetection:\n  condition: selection\n"),
        _row(2, "title: [unclosed\n  bad: : yaml\n"),
        _row(3, "title: AlsoGood\ndetection:\n  condition: selection\n"),
    ]
    patcher, _ = _patched_queue(rows)
    with patcher:
        rules = _queued_rules_for_article(42)

    assert [r["title"] for r in rules] == ["Good", "AlsoGood"]


def test_non_mapping_yaml_is_skipped():
    """A row whose YAML parses to a scalar or list is not a rule."""
    rows = [_row(1, "just a string"), _row(2, "- a\n- b\n")]
    patcher, _ = _patched_queue(rows)
    with patcher:
        assert _queued_rules_for_article(42) == []


def test_empty_queue_returns_empty_list():
    patcher, _ = _patched_queue([])
    with patcher:
        assert _queued_rules_for_article(42) == []


def test_rejected_rules_are_filtered_out():
    """The status filter must exclude rejected rows from the coverage assessment."""
    from src.database.models import SigmaRuleQueueTable

    query = Mock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    session = Mock()
    session.query.return_value = query
    manager = Mock()
    manager.get_session.return_value = session

    with patch("src.database.manager.DatabaseManager", return_value=manager):
        _queued_rules_for_article(7)

    session.query.assert_called_once_with(SigmaRuleQueueTable)
    criteria = [str(arg) for arg in query.filter.call_args.args]
    assert any("article_id" in c for c in criteria)
    assert any("status" in c for c in criteria)
