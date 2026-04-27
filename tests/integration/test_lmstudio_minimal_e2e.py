"""
Minimal LMStudio end-to-end integration test.

This test loads a committed minimal workflow preset, activates it in the test DB,
runs the workflow against LMStudio with Gemma 3 1B, and restores the previous active
config afterward.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func

from src.config.workflow_config_loader import load_workflow_config
from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, AgenticWorkflowExecutionTable, ArticleTable, SourceTable
from src.workflows.agentic_workflow import run_workflow
from tests.utils.test_database_url import build_test_database_url

_LMSTUDIO_BASE_URL = (os.getenv("LMSTUDIO_API_URL") or "http://localhost:1234/v1").rstrip("/")
_MODEL_HINT = "google/gemma-3-1b"
_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "workflow" / "minimal-lmstudio-gemma3-1b.json"


def _probe_lmstudio() -> tuple[bool, list[str]]:
    try:
        response = httpx.get(f"{_LMSTUDIO_BASE_URL}/models", timeout=5.0)
        if response.status_code == 200:
            ids = [model.get("id", "") for model in response.json().get("data", [])]
            return True, ids
    except Exception:  # noqa: BLE001 -- probe is best-effort; any failure means LMStudio is unreachable
        pass
    return False, []


_LMSTUDIO_AVAILABLE, _LOADED_MODELS = _probe_lmstudio()

pytestmark = [
    pytest.mark.lmstudio,
    pytest.mark.integration,
    pytest.mark.skipif(not _LMSTUDIO_AVAILABLE, reason=f"LMStudio not reachable at {_LMSTUDIO_BASE_URL}"),
]


def _test_db_url() -> str:
    return build_test_database_url(asyncpg=False).replace("+asyncpg", "")


@pytest.fixture(scope="module")
def db_session():
    manager = None
    try:
        manager = DatabaseManager(database_url=_test_db_url())
    except Exception as exc:
        pytest.skip(f"Test database unavailable: {exc}")
    assert manager is not None
    session = manager.get_session()
    yield session
    session.close()


@pytest.fixture()
def minimal_active_config(db_session):
    preset_data = json.loads(_FIXTURE_PATH.read_text())
    config_v2 = load_workflow_config(preset_data)
    legacy = config_v2.to_legacy_response_dict()

    previous_active = (
        db_session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.is_active == True)  # noqa: E712
        .first()
    )
    if previous_active:
        previous_active.is_active = False
        db_session.commit()

    max_version = db_session.query(func.max(AgenticWorkflowConfigTable.version)).scalar() or 0
    test_config = AgenticWorkflowConfigTable(
        min_hunt_score=legacy["min_hunt_score"],
        ranking_threshold=legacy["ranking_threshold"],
        similarity_threshold=legacy["similarity_threshold"],
        junk_filter_threshold=legacy["junk_filter_threshold"],
        auto_trigger_hunt_score_threshold=legacy.get("auto_trigger_hunt_score_threshold", 60.0),
        version=max_version + 1,
        is_active=True,
        description="Minimal LMStudio Gemma 3 1B E2E test",
        agent_models=legacy["agent_models"],
        agent_prompts=legacy["agent_prompts"],
        qa_enabled=legacy["qa_enabled"],
        sigma_fallback_enabled=legacy.get("sigma_fallback_enabled", False),
        qa_max_retries=legacy.get("qa_max_retries", 1),
        rank_agent_enabled=legacy.get("rank_agent_enabled", False),
        cmdline_attention_preprocessor_enabled=legacy.get("cmdline_attention_preprocessor_enabled", True),
    )
    db_session.add(test_config)
    db_session.commit()
    db_session.refresh(test_config)

    try:
        yield test_config
    finally:
        test_config.is_active = False
        db_session.commit()
        if previous_active:
            db_session.refresh(previous_active)
            previous_active.is_active = True
            db_session.commit()


@pytest.fixture()
def minimal_test_article(db_session):
    uid = uuid.uuid4().hex[:8]
    source = SourceTable(
        identifier=f"minimal-lmstudio-source-{uid}",
        name="Minimal LMStudio Test Source",
        url="https://test-cti.example.com",
        rss_url="https://test-cti.example.com/feed.xml",
        check_frequency=3600,
        lookback_days=180,
        active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    article = ArticleTable(
        source_id=source.id,
        canonical_url=f"https://test-cti.example.com/minimal-lmstudio-{uid}",
        title="Minimal Gemma 3 1B LMStudio Workflow Test",
        published_at=datetime.now(),
        content=(
            "Incident report: an intruder used WINWORD.EXE to launch cmd.exe /c whoami /all "
            "and then ran powershell.exe -nop -w hidden for follow-on execution. "
            "The article is intentionally brief but still describes malicious Windows behavior."
        ),
        content_hash=f"minimal-lmstudio-hash-{uid}",
        article_metadata={"threat_hunting_score": 95.0},
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    try:
        yield article
    finally:
        db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.article_id == article.id
        ).delete(synchronize_session=False)
        db_session.delete(article)
        db_session.delete(source)
        db_session.commit()


@pytest.mark.smoke
def test_lmstudio_gemma3_1b_smoke_workflow_completes(db_session, minimal_active_config, minimal_test_article):
    missing = [model for model in (_MODEL_HINT,) if not any(model in loaded for loaded in _LOADED_MODELS)]
    if missing:
        pytest.skip(f"Required LMStudio model not loaded: {missing}. Loaded models: {_LOADED_MODELS}")

    config_snapshot = {
        "skip_rank_agent": True,
        "skip_os_detection": True,
        "eval_run": False,
        "min_hunt_score": minimal_active_config.min_hunt_score,
        "ranking_threshold": minimal_active_config.ranking_threshold,
        "similarity_threshold": minimal_active_config.similarity_threshold,
        "junk_filter_threshold": minimal_active_config.junk_filter_threshold,
        "auto_trigger_hunt_score_threshold": getattr(minimal_active_config, "auto_trigger_hunt_score_threshold", 60.0),
        "agent_models": minimal_active_config.agent_models or {},
        "agent_prompts": minimal_active_config.agent_prompts or {},
        "qa_enabled": minimal_active_config.qa_enabled or {},
        "rank_agent_enabled": False,
        "cmdline_attention_preprocessor_enabled": getattr(
            minimal_active_config, "cmdline_attention_preprocessor_enabled", True
        ),
        "sigma_fallback_enabled": getattr(minimal_active_config, "sigma_fallback_enabled", False),
        "osdetection_fallback_enabled": False,
        "qa_max_retries": getattr(minimal_active_config, "qa_max_retries", 1),
        "extract_agent_settings": {
            "disabled_agents": [
                "ProcTreeExtract",
                "HuntQueriesExtract",
                "RegistryExtract",
                "ServicesExtract",
                "ScheduledTasksExtract",
            ]
        },
        "config_id": minimal_active_config.id,
        "config_version": minimal_active_config.version,
    }

    execution = AgenticWorkflowExecutionTable(
        article_id=minimal_test_article.id,
        status="pending",
        config_snapshot=config_snapshot,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)

    @contextmanager
    def _noop_trace(*args, **kwargs):
        yield None

    from unittest.mock import patch

    with patch("src.workflows.agentic_workflow.trace_workflow_execution", _noop_trace):
        result = asyncio.run(
            asyncio.wait_for(run_workflow(minimal_test_article.id, db_session, execution_id=execution.id), timeout=300)
        )

    db_session.expire_all()
    final = (
        db_session.query(AgenticWorkflowExecutionTable).filter(AgenticWorkflowExecutionTable.id == execution.id).first()
    )
    assert final is not None
    assert final.status == "completed", (
        f"Workflow status should be completed, got {final.status}: {final.error_message}"
    )
    assert result is not None
