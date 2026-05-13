"""
Tests for the diagnosis API endpoints:
  GET /evals/{execution_id}/diagnosis        -- load most recent saved diagnosis
  GET /evals/{execution_id}/diagnoses        -- load all saved diagnoses, newest first
  GET /subagent-eval-compare                 -- per-article side-by-side version compare
  GET /subagent-eval-version-articles        -- distinct article URLs for a config version
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.web.routes.evaluation_api import (
    get_saved_diagnosis,
    get_subagent_eval_compare,
    get_subagent_eval_version_articles,
    list_saved_diagnoses,
)

pytestmark = [pytest.mark.api]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_eval_record(
    url,
    version,
    status="completed",
    actual_count=None,
    expected_count=2,
    execution_id=None,
    article_id=None,
    created_at=None,
):
    """Build a minimal mock SubagentEvaluationTable row."""
    from datetime import UTC, datetime

    r = MagicMock()
    r.article_url = url
    r.workflow_config_version = version
    r.status = status
    r.actual_count = actual_count
    r.expected_count = expected_count
    r.workflow_execution_id = execution_id
    r.article_id = article_id
    r.created_at = created_at or datetime.now(UTC)
    r.subagent_name = "cmdline"
    return r


class _FakeQuery:
    def __init__(self, records):
        self._records = records

    def filter(self, *a, **kw):
        return self

    def distinct(self):
        return self

    def order_by(self, *a, **kw):
        return self

    def all(self):
        return self._records


def _make_db(records):
    session = MagicMock()
    session.query.return_value = _FakeQuery(records)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    return db_manager


# ---------------------------------------------------------------------------
# get_saved_diagnosis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_saved_diagnosis_no_files_returns_404(tmp_path):
    """Empty diagnoses dir -> 404."""
    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        with pytest.raises(HTTPException) as exc:
            await get_saved_diagnosis(execution_id=999)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_saved_diagnosis_returns_most_recent(tmp_path):
    """When multiple files match the execution_id, the most recently modified one wins."""
    diag_old = {"diagnosis_id": "old", "summary": "older run"}
    diag_new = {"diagnosis_id": "new", "summary": "newer run"}

    old_file = tmp_path / "42_CmdlineExtract_aaa.json"
    new_file = tmp_path / "42_CmdlineExtract_bbb.json"

    old_file.write_text(json.dumps(diag_old))
    time.sleep(0.01)  # ensure distinct mtime
    new_file.write_text(json.dumps(diag_new))

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await get_saved_diagnosis(execution_id=42)

    assert result["diagnosis_id"] == "new"


@pytest.mark.asyncio
async def test_get_saved_diagnosis_ignores_other_executions(tmp_path):
    """Files for a different execution_id are not returned."""
    (tmp_path / "99_CmdlineExtract_zzz.json").write_text(json.dumps({"diagnosis_id": "wrong"}))

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        with pytest.raises(HTTPException) as exc:
            await get_saved_diagnosis(execution_id=42)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# list_saved_diagnoses  (GET /evals/{id}/diagnoses)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_diagnoses_empty_returns_empty_list(tmp_path):
    """No files -> empty list (not 404)."""
    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await list_saved_diagnoses(execution_id=999)
    assert result == []


@pytest.mark.asyncio
async def test_list_diagnoses_single_file(tmp_path):
    """One file -> list with one entry."""
    diag = {"diagnosis_id": "abc", "summary": "only run"}
    (tmp_path / "7_CmdlineExtract_abc.json").write_text(json.dumps(diag))

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await list_saved_diagnoses(execution_id=7)

    assert len(result) == 1
    assert result[0]["diagnosis_id"] == "abc"


@pytest.mark.asyncio
async def test_list_diagnoses_newest_first(tmp_path):
    """Multiple files -> returned newest-first by mtime."""
    diag_first = {"diagnosis_id": "run1", "summary": "first run"}
    diag_second = {"diagnosis_id": "run2", "summary": "second run"}
    diag_third = {"diagnosis_id": "run3", "summary": "third run"}

    (tmp_path / "42_CmdlineExtract_aaa.json").write_text(json.dumps(diag_first))
    time.sleep(0.01)
    (tmp_path / "42_CmdlineExtract_bbb.json").write_text(json.dumps(diag_second))
    time.sleep(0.01)
    (tmp_path / "42_CmdlineExtract_ccc.json").write_text(json.dumps(diag_third))

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await list_saved_diagnoses(execution_id=42)

    assert len(result) == 3
    assert result[0]["diagnosis_id"] == "run3"
    assert result[1]["diagnosis_id"] == "run2"
    assert result[2]["diagnosis_id"] == "run1"


@pytest.mark.asyncio
async def test_list_diagnoses_ignores_other_executions(tmp_path):
    """Files for other execution_ids are excluded."""
    (tmp_path / "99_CmdlineExtract_zzz.json").write_text(json.dumps({"diagnosis_id": "wrong"}))
    (tmp_path / "42_CmdlineExtract_aaa.json").write_text(json.dumps({"diagnosis_id": "right"}))

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await list_saved_diagnoses(execution_id=42)

    assert len(result) == 1
    assert result[0]["diagnosis_id"] == "right"


@pytest.mark.asyncio
async def test_list_diagnoses_all_runs_returned(tmp_path):
    """All N files for the same execution_id come back (not just the most recent)."""
    for i in range(5):
        diag = {"diagnosis_id": f"run{i}"}
        (tmp_path / f"10_Agent_{i:04d}.json").write_text(json.dumps(diag))
        time.sleep(0.005)

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await list_saved_diagnoses(execution_id=10)

    assert len(result) == 5


# ---------------------------------------------------------------------------
# get_subagent_eval_compare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_basic_improvement():
    """B closer to expected than A -> improvement > 0."""
    url = "https://example.com/article"
    rec_a = _make_eval_record(url, version=10, actual_count=0, expected_count=3, execution_id=1)
    rec_b = _make_eval_record(url, version=11, actual_count=2, expected_count=3, execution_id=2)

    db_manager = _make_db([rec_a, rec_b])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    assert result["version_a"] == 10
    assert result["version_b"] == 11
    assert len(result["articles"]) == 1

    article = result["articles"][0]
    # A: actual=0, expected=3, score=-3, |score|=3
    # B: actual=2, expected=3, score=-1, |score|=1
    # improvement = |score_a| - |score_b| = 3 - 1 = 2
    assert article["improvement"] == 2
    assert article["result_a"]["score"] == -3
    assert article["result_b"]["score"] == -1


@pytest.mark.asyncio
async def test_compare_regression():
    """B further from expected than A -> improvement < 0."""
    url = "https://example.com/article"
    rec_a = _make_eval_record(url, version=10, actual_count=3, expected_count=3, execution_id=1)
    rec_b = _make_eval_record(url, version=11, actual_count=1, expected_count=3, execution_id=2)

    db_manager = _make_db([rec_a, rec_b])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    article = result["articles"][0]
    # A: score=0, B: score=-2 -> improvement = 0 - 2 = -2
    assert article["improvement"] == -2


@pytest.mark.asyncio
async def test_compare_article_only_in_one_version():
    """Article missing from one version has improvement=None and result=None for that version."""
    url = "https://example.com/article"
    rec_a = _make_eval_record(url, version=10, actual_count=2, expected_count=2, execution_id=1)
    # No record for version 11

    db_manager = _make_db([rec_a])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    article = result["articles"][0]
    assert article["improvement"] is None
    assert article["result_b"] is None
    assert article["result_a"]["actual_count"] == 2


@pytest.mark.asyncio
async def test_compare_sort_biggest_change_first():
    """Articles sorted by abs(improvement) descending; nulls at end."""
    url1 = "https://example.com/a1"
    url2 = "https://example.com/a2"
    url3 = "https://example.com/a3"  # only in version_a

    # url1: improvement = |5-0| - |5-4| = 5 - 1 = 4 (big change)
    # url2: improvement = |2-0| - |2-1| = 2 - 1 = 1 (small change)
    rec_a1 = _make_eval_record(url1, version=10, actual_count=0, expected_count=5, execution_id=1)
    rec_b1 = _make_eval_record(url1, version=11, actual_count=4, expected_count=5, execution_id=2)
    rec_a2 = _make_eval_record(url2, version=10, actual_count=0, expected_count=2, execution_id=3)
    rec_b2 = _make_eval_record(url2, version=11, actual_count=1, expected_count=2, execution_id=4)
    rec_a3 = _make_eval_record(url3, version=10, actual_count=1, expected_count=1, execution_id=5)

    db_manager = _make_db([rec_a1, rec_b1, rec_a2, rec_b2, rec_a3])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    improvements = [a["improvement"] for a in result["articles"]]
    # url1 (imp=4) before url2 (imp=1), url3 (imp=None) last
    assert improvements[0] == 4
    assert improvements[1] == 1
    assert improvements[2] is None


@pytest.mark.asyncio
async def test_compare_aggregate_perfect_matches():
    """Aggregate correctly counts perfect matches for each version."""
    url1 = "https://example.com/a1"
    url2 = "https://example.com/a2"

    # version 10: url1 exact (2/2), url2 miss (1/2)
    # version 11: url1 exact (2/2), url2 exact (2/2)
    recs = [
        _make_eval_record(url1, version=10, actual_count=2, expected_count=2, execution_id=1),
        _make_eval_record(url2, version=10, actual_count=1, expected_count=2, execution_id=2),
        _make_eval_record(url1, version=11, actual_count=2, expected_count=2, execution_id=3),
        _make_eval_record(url2, version=11, actual_count=2, expected_count=2, execution_id=4),
    ]

    db_manager = _make_db(recs)

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    assert result["aggregate_a"]["perfect_matches"] == 1
    assert result["aggregate_a"]["perfect_match_percentage"] == 50.0
    assert result["aggregate_b"]["perfect_matches"] == 2
    assert result["aggregate_b"]["perfect_match_percentage"] == 100.0


@pytest.mark.asyncio
async def test_compare_preset_expected_overrides_record_expected():
    """preset_expected_by_url takes priority over record.expected_count for scoring."""
    url = "https://example.com/article"
    rec_a = _make_eval_record(url, version=10, actual_count=3, expected_count=99, execution_id=1)
    rec_b = _make_eval_record(url, version=11, actual_count=4, expected_count=99, execution_id=2)

    db_manager = _make_db([rec_a, rec_b])

    # Preset says expected=3, not 99
    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api._load_preset_expected_by_url", return_value={url: 3}),
        patch("src.web.routes.evaluation_api._load_static_eval_articles", return_value={}),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_compare(
            request=MagicMock(), subagent="cmdline", version_a=10, version_b=11
        )

    article = result["articles"][0]
    # A: actual=3, preset_expected=3, score=0
    # B: actual=4, preset_expected=3, score=+1
    assert article["result_a"]["score"] == 0
    assert article["result_b"]["score"] == 1
    # improvement = |0| - |1| = -1 (regression)
    assert article["improvement"] == -1


# ---------------------------------------------------------------------------
# get_subagent_eval_version_articles
# ---------------------------------------------------------------------------


def _make_url_db(urls):
    """Mock DB for single-column article_url queries. urls is a list of str|None."""
    records = [(u,) for u in urls]
    session = MagicMock()
    session.query.return_value = _FakeQuery(records)
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    return db_manager


_VERSION_ARTICLES_PATCHES = dict(
    resolve=("src.web.routes.evaluation_api._resolve_subagent_query", ("cmdline", ["cmdline"])),
    excluded=("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
)


def _va_ctx(db_manager):
    """Context manager stack for version-articles endpoint."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager))
    stack.enter_context(patch(*_VERSION_ARTICLES_PATCHES["resolve"][0:1], return_value=_VERSION_ARTICLES_PATCHES["resolve"][1]))
    stack.enter_context(patch(_VERSION_ARTICLES_PATCHES["excluded"][0], new=_VERSION_ARTICLES_PATCHES["excluded"][1]))
    return stack


@pytest.mark.asyncio
async def test_version_articles_basic_returns_urls():
    """Returns correct URLs and count for a version with records."""
    urls = ["https://example.com/a1", "https://example.com/a2"]
    db_manager = _make_url_db(urls)

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_version_articles(
            request=MagicMock(), subagent="cmdline", config_version=42
        )

    assert result["config_version"] == 42
    assert result["count"] == 2
    assert set(result["urls"]) == set(urls)


@pytest.mark.asyncio
async def test_version_articles_empty_version_returns_empty():
    """No records -> empty urls list and count=0."""
    db_manager = _make_url_db([])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_version_articles(
            request=MagicMock(), subagent="cmdline", config_version=99
        )

    assert result["urls"] == []
    assert result["count"] == 0
    assert result["config_version"] == 99


@pytest.mark.asyncio
async def test_version_articles_skips_none_urls():
    """Rows with a None url are excluded from the returned list."""
    db_manager = _make_url_db(["https://example.com/real", None, "https://example.com/also-real"])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_version_articles(
            request=MagicMock(), subagent="cmdline", config_version=5
        )

    assert result["count"] == 2
    assert None not in result["urls"]


@pytest.mark.asyncio
async def test_version_articles_response_has_required_keys():
    """Response always contains config_version, urls, and count."""
    db_manager = _make_url_db([])

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_version_articles(
            request=MagicMock(), subagent="cmdline", config_version=7
        )

    assert "config_version" in result
    assert "urls" in result
    assert "count" in result


@pytest.mark.asyncio
async def test_version_articles_count_matches_urls_length():
    """count field is always consistent with the length of the urls list."""
    urls = ["https://example.com/x", "https://example.com/y", "https://example.com/z"]
    db_manager = _make_url_db(urls)

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api._resolve_subagent_query", return_value=("cmdline", ["cmdline"])),
        patch("src.web.routes.evaluation_api.EXCLUDED_EVAL_ARTICLE_IDS", frozenset()),
    ):
        result = await get_subagent_eval_version_articles(
            request=MagicMock(), subagent="cmdline", config_version=20
        )

    assert result["count"] == len(result["urls"])
