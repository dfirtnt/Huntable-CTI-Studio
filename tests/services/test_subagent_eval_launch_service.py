"""Unit tests for subagent_eval_launch_service.

Covers the four behaviours the service was extracted for: a plan writes
nothing, the per-launch cap is enforced before any write, inline execution
is skipped when the caller disallows it, and replicates expand server-side.
No database: the session is a fake that records adds, flushes and commits.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SubagentEvaluationTable,
)
from src.services import subagent_eval_launch_service as svc

pytestmark = pytest.mark.unit

URL_A = "https://example.test/a"
URL_B = "https://example.test/b"
URL_NO_ROW = "https://example.test/no-db-row"
URL_NO_FIXTURE = "https://example.test/no-fixture"


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def all(self):
        return self._result if isinstance(self._result, list) else []


class FakeSession:
    """Sync-session stand-in that assigns ids on flush and records write calls."""

    def __init__(self, config, article_rows=None):
        self.config = config
        self.article_rows = article_rows or []
        self.added = []
        self.flush_count = 0
        self.committed = False
        self.queried_models = []
        self._next_id = 1000

    def query(self, *entities):
        self.queried_models.append(entities)
        if entities and entities[0] is AgenticWorkflowConfigTable:
            return _FakeQuery(self.config)
        return _FakeQuery(self.article_rows)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _config(**overrides):
    values = {
        "id": 7,
        "version": 5139,
        "is_active": True,
        "agent_models": {
            "CmdlineExtract_provider": "lmstudio",
            "CmdlineExtract_model": "qwen/qwen3-8b",
            "ExtractAgent_provider": "openai",
            "ExtractAgent": "gpt-4.1",
        },
        "agent_prompts": {"CmdlineExtract": {"prompt": json.dumps({"system": "extract"})}},
    }
    values.update(overrides)
    return AgenticWorkflowConfigTable(**values)


def _fixture(url, content="fixture body", expected_items=None):
    return {
        "url": url,
        "title": f"Title for {url}",
        "content": content,
        "expected_count": 3,
        "expected_items": expected_items,
        "acceptable_items": None,
    }


@pytest.fixture
def stub_inputs(monkeypatch):
    """Point the planner at in-memory fixtures, committed URLs and DB rows."""
    fixtures = {
        URL_A: _fixture(URL_A, expected_items=["cmd a"]),
        URL_B: _fixture(URL_B),
        URL_NO_ROW: _fixture(URL_NO_ROW),
        URL_NO_FIXTURE: _fixture(URL_NO_FIXTURE, content=""),
    }
    db_rows = {URL_A: 42, URL_B: 43, URL_NO_FIXTURE: 44}
    committed = [(URL_A, 5), (URL_B, 2)]

    monkeypatch.setattr(
        svc, "load_static_eval_articles", lambda subagent: dict(fixtures) if subagent == "cmdline" else {}
    )
    monkeypatch.setattr(
        svc, "committed_eval_articles", lambda subagent: list(committed) if subagent == "cmdline" else []
    )
    monkeypatch.setattr(
        svc, "resolve_article_ids_by_urls", lambda session, urls: {u: db_rows[u] for u in urls if u in db_rows}
    )
    return {"fixtures": fixtures, "db_rows": db_rows, "committed": committed}


@pytest.fixture
def capture_writes(monkeypatch):
    """Capture snapshot payloads and Celery dispatches without touching a DB or broker."""
    snapshots = []
    dispatches = []

    def fake_attach(session, execution, payload):
        snapshots.append(payload)
        execution.config_snapshot_id = 77
        execution.config_snapshot = {"snapshot_id": 77}

    def fake_enqueue(article_id, execution_id, countdown):
        dispatches.append(((article_id, execution_id), countdown))

    monkeypatch.setattr(svc, "attach_snapshot", fake_attach)
    monkeypatch.setattr(svc, "_enqueue_eval_execution", fake_enqueue)
    return {"snapshots": snapshots, "dispatches": dispatches}


# ---------------------------------------------------------------------------
# plan_subagent_eval
# ---------------------------------------------------------------------------


def test_plan_defaults_to_committed_urls_and_writes_nothing(stub_inputs):
    session = FakeSession(_config())

    plan = svc.plan_subagent_eval(session, "CmdlineExtract")

    assert [row.url for row in plan.rows] == [URL_A, URL_B]
    assert [row.expected_count for row in plan.rows] == [5, 2]
    assert plan.subagent == "cmdline"
    assert plan.agent_name == "CmdlineExtract"
    assert plan.config_id == 7
    assert plan.config_version == 5139
    assert plan.run_label == "v5139"
    assert plan.provider == "lmstudio"
    assert plan.model == "qwen/qwen3-8b"
    assert plan.is_local_provider is True
    assert plan.total_executions == 2
    assert plan.exceeds_cap is False
    assert session.added == []
    assert session.flush_count == 0
    assert session.committed is False


def test_plan_to_dict_omits_fixture_bodies_and_orm_row(stub_inputs):
    plan = svc.plan_subagent_eval(FakeSession(_config()), "cmdline", article_urls=[URL_A])

    payload = plan.to_dict()

    assert payload["rows"] == [
        {"url": URL_A, "replicate": 1, "article_id": 42, "status": "ready", "expected_count": 5},
    ]
    assert "config" not in payload
    assert "fixture_content" not in json.dumps(payload)
    assert payload["counts"] == {"ready": 1, "no_db_row": 0, "no_fixture": 0}
    assert payload["max_executions"] == svc.DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH


def test_plan_expands_replicates_server_side(stub_inputs):
    plan = svc.plan_subagent_eval(FakeSession(_config()), "cmdline", article_urls=[URL_A, URL_B], replicates=3)

    assert len(plan.rows) == 6
    assert [(row.url, row.replicate) for row in plan.rows] == [
        (URL_A, 1),
        (URL_B, 1),
        (URL_A, 2),
        (URL_B, 2),
        (URL_A, 3),
        (URL_B, 3),
    ]
    assert plan.total_executions == 6
    assert plan.replicates == 3


@pytest.mark.parametrize("replicates", [0, 51, -1, True, 2.0, "3"])
def test_plan_rejects_replicates_out_of_range_before_touching_db(stub_inputs, replicates):
    session = FakeSession(_config())

    with pytest.raises(svc.EvalLaunchError):
        svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A], replicates=replicates)

    assert session.queried_models == []


def test_plan_rejects_empty_subagent_before_touching_db(stub_inputs):
    session = FakeSession(_config())

    with pytest.raises(svc.EvalLaunchError):
        svc.plan_subagent_eval(session, "   ")

    assert session.queried_models == []


def test_plan_raises_when_no_active_config(stub_inputs):
    with pytest.raises(svc.NoActiveConfigError):
        svc.plan_subagent_eval(FakeSession(None), "cmdline", article_urls=[URL_A])


def test_plan_classifies_missing_fixture_and_missing_db_row(stub_inputs):
    urls = [URL_A, URL_NO_ROW, URL_NO_FIXTURE]

    inline_ok = svc.plan_subagent_eval(FakeSession(_config()), "cmdline", article_urls=urls)
    inline_off = svc.plan_subagent_eval(
        FakeSession(_config()), "cmdline", article_urls=urls, allow_inline_execution=False
    )

    assert [row.status for row in inline_ok.rows] == ["ready", "no_db_row", "no_fixture"]
    assert inline_ok.missing_fixture_urls == [URL_NO_FIXTURE]
    # A no_fixture row keeps its article id so found_articles still counts it.
    assert inline_ok.rows[2].article_id == 44
    assert inline_ok.rows[2].fixture_content_sha256 is None
    assert inline_ok.total_executions == 2
    assert inline_off.total_executions == 1
    assert inline_ok.counts == {"ready": 1, "no_db_row": 1, "no_fixture": 1}


def test_plan_preserves_duplicate_urls_from_the_caller(stub_inputs):
    plan = svc.plan_subagent_eval(FakeSession(_config()), "cmdline", article_urls=[URL_A, URL_A, URL_A])

    assert [row.url for row in plan.rows] == [URL_A, URL_A, URL_A]
    assert plan.total_executions == 3


def test_plan_reads_cap_from_env_at_call_time(stub_inputs, monkeypatch):
    monkeypatch.setenv(svc.MAX_EVAL_EXECUTIONS_ENV, "2")

    plan = svc.plan_subagent_eval(FakeSession(_config()), "cmdline", article_urls=[URL_A, URL_B, URL_A])

    assert plan.max_executions == 2
    assert plan.total_executions == 3
    assert plan.exceeds_cap is True


@pytest.mark.parametrize("raw", ["", "   ", "abc", "0", "-5"])
def test_max_executions_falls_back_to_default_on_bad_env(monkeypatch, raw):
    monkeypatch.setenv(svc.MAX_EVAL_EXECUTIONS_ENV, raw)

    assert svc.max_eval_executions_per_launch() == svc.DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH


def test_plan_reports_cloud_provider_as_billable(stub_inputs):
    config = _config(agent_models={"CmdlineExtract_provider": "openai", "CmdlineExtract_model": "gpt-4.1"})

    plan = svc.plan_subagent_eval(FakeSession(config), "cmdline", article_urls=[URL_A])

    assert plan.provider == "openai"
    assert plan.is_local_provider is False


def test_resolve_agent_provider_model_handles_flat_nested_and_fallback():
    flat = {"CmdlineExtract_provider": "anthropic", "CmdlineExtract_model": "claude-sonnet-4-5"}
    nested = {"CmdlineExtract": {"provider": "openai", "model": "gpt-4.1-mini"}}
    fallback = {"ExtractAgent_provider": "openai", "ExtractAgent": "gpt-4.1"}
    nested_fallback = {"ExtractAgent": {"provider": "anthropic", "model": "claude-opus-4-5"}}

    assert svc.resolve_agent_provider_model(flat, "CmdlineExtract") == ("anthropic", "claude-sonnet-4-5")
    assert svc.resolve_agent_provider_model(nested, "CmdlineExtract") == ("openai", "gpt-4.1-mini")
    assert svc.resolve_agent_provider_model(fallback, "CmdlineExtract") == ("openai", "gpt-4.1")
    assert svc.resolve_agent_provider_model(nested_fallback, "CmdlineExtract") == ("anthropic", "claude-opus-4-5")
    assert svc.resolve_agent_provider_model({}, "CmdlineExtract") == (None, None)
    assert svc.resolve_agent_provider_model(None, None) == (None, None)


def test_resolve_article_ids_by_urls_matches_canonical_url_rows():
    session = FakeSession(_config(), article_rows=[(URL_A, 42), (URL_B, 43)])

    resolved = svc.resolve_article_ids_by_urls(session, [URL_A, URL_B])

    assert resolved == {URL_A: 42, URL_B: 43}
    assert session.queried_models and session.queried_models[0][0] is ArticleTable.canonical_url


# ---------------------------------------------------------------------------
# launch_subagent_eval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_rejects_cap_before_any_write(stub_inputs, capture_writes, monkeypatch):
    monkeypatch.setenv(svc.MAX_EVAL_EXECUTIONS_ENV, "2")
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A, URL_B, URL_A])
    assert plan.exceeds_cap is True

    with pytest.raises(svc.EvalLaunchCapExceededError) as excinfo:
        await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=0.0, initiated_by="service:test")

    assert "MAX_EVAL_EXECUTIONS_PER_LAUNCH=2" in str(excinfo.value)
    assert session.added == []
    assert session.committed is False
    assert capture_writes["snapshots"] == []
    assert capture_writes["dispatches"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("throttle", [-0.1, 60.1])
async def test_launch_rejects_bad_throttle_before_any_write(stub_inputs, capture_writes, throttle):
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A])

    with pytest.raises(svc.EvalLaunchError):
        await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=throttle, initiated_by="web")

    assert session.added == []
    assert capture_writes["dispatches"] == []


@pytest.mark.asyncio
async def test_launch_requires_initiated_by(stub_inputs, capture_writes):
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A])

    with pytest.raises(svc.EvalLaunchError):
        await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=1.0, initiated_by="  ")

    assert session.added == []


@pytest.mark.asyncio
async def test_launch_creates_rows_commits_then_staggers_dispatch(stub_inputs, capture_writes, monkeypatch):
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A, URL_B, URL_A])
    commit_seen_at_dispatch = []
    dispatch_log = capture_writes["dispatches"]

    def enqueue_checks_commit(article_id, execution_id, countdown):
        commit_seen_at_dispatch.append(session.committed)
        dispatch_log.append(((article_id, execution_id), countdown))

    monkeypatch.setattr(svc, "_enqueue_eval_execution", enqueue_checks_commit)

    result = await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=5.0, initiated_by="service:mcp")

    executions = [obj for obj in session.added if isinstance(obj, AgenticWorkflowExecutionTable)]
    records = [obj for obj in session.added if isinstance(obj, SubagentEvaluationTable)]
    assert len(executions) == 3
    assert len(records) == 3
    assert all(execution.status == "pending" for execution in executions)
    assert [execution.article_id for execution in executions] == [42, 43, 42]
    assert all(record.status == "pending" for record in records)
    assert [record.workflow_execution_id for record in records] == [execution.id for execution in executions]
    assert all(record.workflow_config_version == 5139 for record in records)
    assert records[0].expected_items == ["cmd a"]
    assert session.committed is True
    assert commit_seen_at_dispatch == [True, True, True]

    # Response rows carry real ids, including the eval record id the UI polls.
    assert [info["execution_id"] for info in result.executions] == [execution.id for execution in executions]
    assert [info["eval_record_id"] for info in result.executions] == [record.id for record in records]
    assert all(info["eval_record_id"] is not None for info in result.executions)
    assert result.execution_ids == [execution.id for execution in executions]
    assert result.eval_record_ids == [record.id for record in records]
    assert result.total_executions == 3
    assert result.found_articles == 3
    assert result.skipped == []
    assert result.message == "Triggered 3 workflow executions for cmdline evaluation"

    # Snapshot extras: eval flags, fixture hash and provenance; provenance is hash-excluded.
    snapshots = capture_writes["snapshots"]
    assert len(snapshots) == 3
    for payload, row in zip(snapshots, plan.rows, strict=True):
        assert payload["eval_run"] is True
        assert payload["skip_os_detection"] is True
        assert payload["skip_rank_agent"] is True
        assert payload["skip_sigma_generation"] is True
        assert payload["subagent_eval"] == "cmdline"
        assert payload["eval_fixture_content"] == row.fixture_content
        assert payload["eval_fixture_content_sha256"] == row.fixture_content_sha256
        assert payload["initiated_by"] == "service:mcp"
    assert snapshots[0]["snapshot_hash"] == snapshots[2]["snapshot_hash"]

    # Dispatch: stagger floor plus throttle, strictly increasing.
    dispatches = capture_writes["dispatches"]
    step = svc.EVAL_STAGGER_SECONDS + 5.0
    assert [args for args, _ in dispatches] == [(42, executions[0].id), (43, executions[1].id), (42, executions[2].id)]
    assert [countdown for _, countdown in dispatches] == pytest.approx([0.0, step, 2 * step])

    metadata = result.audit_metadata()
    assert metadata["eval_kind"] == "subagent"
    assert metadata["subagent"] == "cmdline"
    assert metadata["executions_count"] == 3
    assert metadata["total_articles"] == 3
    assert metadata["found_articles"] == 3
    assert metadata["initiated_by"] == "service:mcp"
    assert metadata["run_label"] == "v5139"
    assert result.to_dict()["execution_ids"] == result.execution_ids


@pytest.mark.asyncio
async def test_launch_skips_no_db_row_when_inline_execution_disallowed(stub_inputs, capture_writes, monkeypatch):
    llm_service_cls = MagicMock(side_effect=AssertionError("inline LLM path must not run"))
    monkeypatch.setattr(svc, "LLMService", llm_service_cls)
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(
        session, "cmdline", article_urls=[URL_A, URL_NO_ROW, URL_NO_FIXTURE], allow_inline_execution=False
    )

    result = await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=0.0, initiated_by="service:mcp")

    assert llm_service_cls.call_count == 0
    assert len(result.executions) == 1
    assert result.inline_eval_record_ids == []
    assert result.skipped == [
        {"url": URL_NO_ROW, "replicate": 1, "reason": "no_db_row"},
        {"url": URL_NO_FIXTURE, "replicate": 1, "reason": "no_fixture"},
    ]
    records = [obj for obj in session.added if isinstance(obj, SubagentEvaluationTable)]
    assert [record.article_url for record in records] == [URL_A]
    assert len(capture_writes["dispatches"]) == 1
    assert result.audit_metadata()["skipped_count"] == 2


@pytest.mark.asyncio
async def test_launch_runs_inline_when_allowed_and_scores_fixture(stub_inputs, capture_writes, monkeypatch):
    run_extraction_agent = AsyncMock(return_value={"cmdline_items": [{"value": "whoami"}, {"value": "net user"}]})
    llm_service = MagicMock()
    llm_service.run_extraction_agent = run_extraction_agent
    monkeypatch.setattr(svc, "LLMService", MagicMock(return_value=llm_service))
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_NO_ROW])

    result = await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=0.0, initiated_by="web")

    assert run_extraction_agent.await_count == 1
    kwargs = run_extraction_agent.await_args.kwargs
    assert kwargs["agent_name"] == "CmdlineExtract"
    assert kwargs["content"] == "fixture body"
    assert kwargs["url"] == URL_NO_ROW
    assert kwargs["provider"] == "lmstudio"
    assert kwargs["model_name"] == "qwen/qwen3-8b"
    assert kwargs["max_extraction_retries"] == 1
    records = [obj for obj in session.added if isinstance(obj, SubagentEvaluationTable)]
    assert len(records) == 1
    assert records[0].status == "completed"
    assert records[0].actual_count == 2
    assert records[0].expected_count == 0
    assert records[0].score == 2
    assert records[0].workflow_execution_id is None
    assert result.executions == []
    assert result.inline_eval_record_ids == [records[0].id]
    assert result.total_executions == 1
    assert capture_writes["dispatches"] == []
    assert session.committed is True


@pytest.mark.asyncio
async def test_launch_inline_records_failed_when_agent_prompt_missing(stub_inputs, capture_writes, monkeypatch):
    llm_service_cls = MagicMock(side_effect=AssertionError("must not instantiate without a prompt"))
    monkeypatch.setattr(svc, "LLMService", llm_service_cls)
    session = FakeSession(_config(agent_prompts={}))
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_NO_ROW])

    result = await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=0.0, initiated_by="web")

    records = [obj for obj in session.added if isinstance(obj, SubagentEvaluationTable)]
    assert len(records) == 1
    assert records[0].status == "failed"
    assert llm_service_cls.call_count == 0
    assert result.inline_eval_record_ids == [records[0].id]


@pytest.mark.asyncio
async def test_launch_wraps_broker_failure_after_commit(stub_inputs, capture_writes, monkeypatch):
    session = FakeSession(_config())
    plan = svc.plan_subagent_eval(session, "cmdline", article_urls=[URL_A, URL_B])
    calls = []

    def failing_enqueue(article_id, execution_id, countdown):
        calls.append((article_id, execution_id))
        if len(calls) == 2:
            raise ConnectionError("broker down")

    monkeypatch.setattr(svc, "_enqueue_eval_execution", failing_enqueue)

    with pytest.raises(svc.EvalDispatchError) as excinfo:
        await svc.launch_subagent_eval(session, plan, concurrency_throttle_seconds=0.0, initiated_by="web")

    assert "after 1 of 2" in str(excinfo.value)
    assert session.committed is True
