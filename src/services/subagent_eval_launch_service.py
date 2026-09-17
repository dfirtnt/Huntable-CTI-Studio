"""Plan and launch subagent eval runs against the active workflow config.

Lifted out of ``POST /api/evaluations/run-subagent-eval`` so the HTTP route and
the MCP launch tool share one planner, one per-launch execution cap and one set
of writes. Keep this module free of FastAPI objects: callers own the session,
the audit actor and the response shape. ``plan_subagent_eval`` never writes;
``launch_subagent_eval`` performs every write the route used to perform.

Nothing here reads, re-scrapes or mutates eval-article rows or the
``config/eval_articles_data`` fixtures; fixtures are read-only inputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import yaml

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SubagentEvaluationTable,
)
from src.services.eval_item_scorer import score_items
from src.services.execution_snapshot_store import attach_snapshot
from src.services.llm_service import LLMService
from src.services.workflow_config_snapshot import build_config_snapshot
from src.utils.subagent_utils import SUBAGENT_TO_EXTRACT_AGENT, normalize_subagent_name

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Per-URL plan statuses.
ROW_READY = "ready"
ROW_NO_FIXTURE = "no_fixture"
ROW_NO_DB_ROW = "no_db_row"

# The Agent Evals page clamps its "Runs per article" multiplier to 50; the
# server-side replicate expansion honours the same ceiling.
MAX_REPLICATES = 50
MAX_THROTTLE_SECONDS = 60.0

# Hard ceiling on LLM runs a single launch may start, so a runaway URL list or
# replicate count cannot fan out unbounded provider spend. Read at call time so
# a container env change is picked up without a code reload.
MAX_EVAL_EXECUTIONS_ENV = "MAX_EVAL_EXECUTIONS_PER_LAUNCH"
DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH = 100

# Providers whose runs bill nothing. Everything else spends provider tokens.
LOCAL_PROVIDERS = frozenset({"lmstudio"})

# Per-submission delay when dispatching a batch of eval workflows.
# Without staggering, concurrent child workers race on inherited DB connections
# during os_detection (Celery prefork + SQLAlchemy pool corruption). A short
# broker-side countdown spreads os_detection DB hits across distinct ticks.
EVAL_STAGGER_SECONDS = float(os.getenv("EVAL_STAGGER_SECONDS", "0.2"))

_ROOT = Path(__file__).resolve().parents[2]
EVAL_ARTICLES_DATA_DIR = _ROOT / "config" / "eval_articles_data"
EVAL_ARTICLES_CONFIG_PATH = _ROOT / "config" / "eval_articles.yaml"

# Strict allowlist on the fixture directory key (defense-in-depth above the
# resolve/startswith containment guard in load_static_eval_articles). Real keys
# are lowercase identifiers like "cmdline", "hunt_queries", "process_lineage"
# and never contain "/" or ".".
SUBAGENT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class EvalLaunchError(ValueError):
    """A launch could not be planned or performed. Callers map this to their own error shape."""


class NoActiveConfigError(EvalLaunchError):
    """No active agentic workflow config row exists."""


class EvalLaunchCapExceededError(EvalLaunchError):
    """The plan would start more LLM runs than MAX_EVAL_EXECUTIONS_PER_LAUNCH allows."""


class EvalDispatchError(EvalLaunchError):
    """Rows were committed but the Celery broker refused one or more dispatches."""


def max_eval_executions_per_launch() -> int:
    """Return the per-launch execution cap, falling back to the default on a bad value."""
    raw = os.getenv(MAX_EVAL_EXECUTIONS_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; using default %s",
            MAX_EVAL_EXECUTIONS_ENV,
            raw,
            DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH,
        )
        return DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH
    if value < 1:
        logger.warning(
            "%s=%s must be at least 1; using default %s",
            MAX_EVAL_EXECUTIONS_ENV,
            value,
            DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH,
        )
        return DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH
    return value


def load_static_eval_articles(subagent_key: str) -> dict[str, dict]:
    """Load static eval article snapshots for a subagent.

    Returns dict url -> {url, title, content, expected_count,
    expected_items?, acceptable_items?}.  expected_items comes from the
    separate ground_truth.json file (if present) and is never stored in
    articles.json.
    """
    out: dict[str, dict] = {}
    if not isinstance(subagent_key, str) or not SUBAGENT_KEY_RE.fullmatch(subagent_key):
        return out
    data_dir = (EVAL_ARTICLES_DATA_DIR / subagent_key).resolve()
    # Prevent path traversal: resolved path must stay within the allowed data directory.
    if not str(data_dir).startswith(str(EVAL_ARTICLES_DATA_DIR.resolve()) + "/"):
        return out
    articles_path = data_dir / "articles.json"
    if not articles_path.exists():
        return out
    try:
        with open(articles_path) as f:
            articles = json.load(f)
        if not isinstance(articles, list):
            return out
        for entry in articles:
            url = entry.get("url")
            if url:
                out[url] = {
                    "url": url,
                    "title": entry.get("title", ""),
                    "content": entry.get("content", ""),
                    "expected_count": entry.get("expected_count", 0),
                    "expected_items": None,
                    "acceptable_items": None,
                }
    except Exception as e:
        logger.warning("Failed to load static eval articles for %s: %s", subagent_key, e)
        return out

    # Merge expected_items from ground_truth.json (item-level eval ground truth).
    # This file is separate so article snapshot refreshes never clobber annotations.
    gt_path = data_dir / "ground_truth.json"
    if gt_path.exists():
        try:
            with open(gt_path) as f:
                gt_entries = json.load(f)
            if isinstance(gt_entries, list):
                for gt in gt_entries:
                    url = gt.get("url")
                    items = gt.get("expected_items")
                    if url and url in out and isinstance(items, list):
                        out[url]["expected_items"] = items
                        acceptable_items = gt.get("acceptable_items")
                        if isinstance(acceptable_items, list):
                            out[url]["acceptable_items"] = acceptable_items
        except Exception as e:
            logger.warning("Failed to load ground_truth.json for %s: %s", subagent_key, e)

    return out


def committed_eval_articles(subagent: str) -> list[tuple[str, int]]:
    """Return ``(url, expected_count)`` pairs for a subagent from ``config/eval_articles.yaml``.

    Preserves file order so a launch that defaults to the full committed set runs
    the articles in the order the operator curated them. Missing file or subagent
    yields an empty list.
    """
    if not EVAL_ARTICLES_CONFIG_PATH.exists():
        return []
    with open(EVAL_ARTICLES_CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    subagent_articles = (config.get("subagents") or {}).get(subagent) or []
    if not isinstance(subagent_articles, list):
        return []
    out: list[tuple[str, int]] = []
    for article_def in subagent_articles:
        if not isinstance(article_def, dict):
            continue
        url = article_def.get("url")
        if not url:
            continue
        expected_count = article_def.get("expected_count")
        out.append((url, expected_count if expected_count is not None else 0))
    return out


def resolve_article_ids_by_urls(session: Session, urls: list[str]) -> dict[str, int]:
    """Resolve article URLs to article IDs on the caller's session with batch queries.

    Returns:
        Dict mapping url -> article_id (only entries that were found).
    """
    result: dict[str, int] = {}
    if not urls:
        return result

    # Split into localhost (by id) and external (by canonical_url)
    localhost_ids: list[int] = []
    localhost_url_to_id: dict[str, int] = {}
    external_urls: list[str] = []
    for url in urls:
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.netloc in ("127.0.0.1:8001", "localhost:8001", "127.0.0.1", "localhost"):
            match = re.match(r"/articles/(\d+)", parsed.path)
            if match:
                aid = int(match.group(1))
                localhost_ids.append(aid)
                localhost_url_to_id[url] = aid
        else:
            external_urls.append(url)

    # Batch: resolve localhost IDs (verify existence)
    if localhost_ids:
        found = session.query(ArticleTable.id).filter(ArticleTable.id.in_(localhost_ids)).all()
        found_ids = {r[0] for r in found}
        for url, aid in localhost_url_to_id.items():
            if aid in found_ids:
                result[url] = aid

    # Batch: exact match on canonical_url
    if external_urls:
        rows = (
            session.query(ArticleTable.canonical_url, ArticleTable.id)
            .filter(ArticleTable.canonical_url.in_(external_urls))
            .all()
        )
        for canonical_url, aid in rows:
            result[canonical_url] = aid

    # For any external URL not found, try normalized (path-only) LIKE
    missing = [u for u in external_urls if u not in result]
    for url in missing:
        parsed = urlparse(url)
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if normalized == url:
            continue
        row = session.query(ArticleTable.id).filter(ArticleTable.canonical_url.like(f"{normalized}%")).first()
        if row:
            result[url] = row[0]

    return result


def resolve_agent_provider_model(
    agent_models: dict[str, Any] | None, agent_name: str | None
) -> tuple[str | None, str | None]:
    """Return the ``(provider, model)`` an extractor resolves to under ``agent_models``.

    Mirrors the flat-key lookup the inline eval path has always used
    (``{Agent}_provider`` / ``{Agent}_model`` with the ExtractAgent supervisor as
    fallback) and also reads the nested WorkflowConfigV2 form so the plan reports
    the same provider LLMService would pick.
    """
    models = agent_models or {}

    def _lookup(name: str | None, kind: str) -> str | None:
        if not name:
            return None
        value = models.get(f"{name}_{kind}")
        if value is None:
            nested = models.get(name)
            if isinstance(nested, dict):
                value = nested.get(kind)
            elif kind == "model" and isinstance(nested, str):
                # Main agents use the bare agent name as their model key.
                value = nested
        return value if isinstance(value, str) and value else None

    provider = _lookup(agent_name, "provider") or _lookup("ExtractAgent", "provider")
    model = _lookup(agent_name, "model") or _lookup("ExtractAgent", "model")
    return provider, model


def actual_count_from_agent_result(subagent_name: str, agent_result: dict) -> int | None:
    """Derive observable count from run_extraction_agent result for a single subagent."""
    if subagent_name == "hunt_queries":
        n = agent_result.get("count")
        if n is not None:
            return int(n)
        q = agent_result.get("queries") or agent_result.get("items", [])
        return len(q) if isinstance(q, list) else 0
    if subagent_name == "cmdline":
        items = agent_result.get("cmdline_items") or agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    if subagent_name == "process_lineage":
        items = agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    if subagent_name == "registry_artifacts":
        items = agent_result.get("registry_artifacts") or agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    if subagent_name == "windows_services":
        items = agent_result.get("windows_services") or agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    if subagent_name == "scheduled_tasks":
        items = agent_result.get("scheduled_tasks") or agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    if subagent_name == "network_indicators":
        items = agent_result.get("network_indicators") or agent_result.get("items", [])
        return len(items) if isinstance(items, list) else agent_result.get("count")
    n = agent_result.get("count")
    if n is not None:
        return int(n)
    items = agent_result.get("items", [])
    return len(items) if isinstance(items, list) else 0


def raw_actual_items_from_agent_result(subagent_name: str, agent_result: dict) -> list:
    """Return the raw extractor item list from a direct static-eval agent result.

    Canonical identity extraction and normalization happen in
    ``eval_item_scorer.score_items`` (keyed by ``subagent_name``); this helper
    only locates the list under the agent-specific or generic key, keeping the
    structured dicts intact so registry/service/scheduled-task identities are
    built from their real fields rather than the generic ``value`` field.
    """
    item_keys = {
        "cmdline": ("cmdline_items", "items"),
        "hunt_queries": ("queries", "items"),
        "process_lineage": ("items",),
        "registry_artifacts": ("registry_artifacts", "items"),
        "windows_services": ("windows_services", "items"),
        "scheduled_tasks": ("scheduled_tasks", "items"),
        "network_indicators": ("network_indicators", "items"),
    }.get(subagent_name, ("items",))
    raw_items = next((agent_result.get(key) for key in item_keys if isinstance(agent_result.get(key), list)), [])
    return raw_items or []


@dataclass(frozen=True)
class EvalLaunchRow:
    """One planned run: a URL under one replicate, with everything launch needs for it."""

    url: str
    replicate: int
    article_id: int | None
    status: str
    expected_count: int
    expected_items: list[str] | None
    acceptable_items: list[dict[str, str]] | None
    fixture_title: str
    fixture_content: str
    fixture_content_sha256: str | None

    def summary(self) -> dict[str, Any]:
        """JSON-safe view without the fixture body."""
        return {
            "url": self.url,
            "replicate": self.replicate,
            "article_id": self.article_id,
            "status": self.status,
            "expected_count": self.expected_count,
        }


@dataclass(frozen=True)
class EvalLaunchPlan:
    """Everything a launch will do, resolved without any write."""

    subagent: str
    agent_name: str | None
    config: Any = field(repr=False, compare=False)
    config_id: int
    config_version: int
    run_label: str
    provider: str | None
    model: str | None
    is_local_provider: bool
    replicates: int
    allow_inline_execution: bool
    rows: tuple[EvalLaunchRow, ...]
    max_executions: int

    def _will_run(self, row: EvalLaunchRow) -> bool:
        if row.status == ROW_READY:
            return True
        return row.status == ROW_NO_DB_ROW and self.allow_inline_execution

    @property
    def total_executions(self) -> int:
        """LLM runs this launch would start: dispatched workflows plus inline runs."""
        return sum(1 for row in self.rows if self._will_run(row))

    @property
    def exceeds_cap(self) -> bool:
        return self.total_executions > self.max_executions

    @property
    def missing_fixture_urls(self) -> list[str]:
        return [row.url for row in self.rows if row.status == ROW_NO_FIXTURE]

    @property
    def counts(self) -> dict[str, int]:
        counts = {ROW_READY: 0, ROW_NO_DB_ROW: 0, ROW_NO_FIXTURE: 0}
        for row in self.rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe plan without fixture bodies or the ORM config row."""
        return {
            "subagent": self.subagent,
            "agent_name": self.agent_name,
            "config_id": self.config_id,
            "config_version": self.config_version,
            "run_label": self.run_label,
            "provider": self.provider,
            "model": self.model,
            "is_local_provider": self.is_local_provider,
            "replicates": self.replicates,
            "allow_inline_execution": self.allow_inline_execution,
            "total_executions": self.total_executions,
            "max_executions": self.max_executions,
            "exceeds_cap": self.exceeds_cap,
            "counts": self.counts,
            "rows": [row.summary() for row in self.rows],
        }


@dataclass(frozen=True)
class EvalLaunchResult:
    """What a launch wrote and dispatched."""

    plan: EvalLaunchPlan
    initiated_by: str
    executions: list[dict[str, Any]]
    inline_eval_record_ids: list[int | None]
    skipped: list[dict[str, Any]]

    @property
    def subagent(self) -> str:
        return self.plan.subagent

    @property
    def run_label(self) -> str:
        return self.plan.run_label

    @property
    def config_version(self) -> int:
        return self.plan.config_version

    @property
    def execution_ids(self) -> list[int]:
        return [info["execution_id"] for info in self.executions]

    @property
    def eval_record_ids(self) -> list[int | None]:
        return [info["eval_record_id"] for info in self.executions] + list(self.inline_eval_record_ids)

    @property
    def total_executions(self) -> int:
        return len(self.executions) + len(self.inline_eval_record_ids)

    @property
    def found_articles(self) -> int:
        return sum(1 for row in self.plan.rows if row.article_id is not None)

    @property
    def message(self) -> str:
        return f"Triggered {len(self.executions)} workflow executions for {self.subagent} evaluation"

    def audit_metadata(self) -> dict[str, Any]:
        """Payload for the ACTION_EVAL_RUN_REQUESTED audit event."""
        return {
            "eval_kind": "subagent",
            "subagent": self.subagent,
            "executions_count": len(self.executions),
            "total_articles": len(self.plan.rows),
            "found_articles": self.found_articles,
            "initiated_by": self.initiated_by,
            "config_version": self.config_version,
            "run_label": self.run_label,
            "replicates": self.plan.replicates,
            "inline_count": len(self.inline_eval_record_ids),
            "skipped_count": len(self.skipped),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "subagent": self.subagent,
            "run_label": self.run_label,
            "config_version": self.config_version,
            "initiated_by": self.initiated_by,
            "total_executions": self.total_executions,
            "execution_ids": self.execution_ids,
            "eval_record_ids": self.eval_record_ids,
            "found_articles": self.found_articles,
            "skipped": list(self.skipped),
        }


def _active_config(session: Session) -> AgenticWorkflowConfigTable:
    config = (
        session.query(AgenticWorkflowConfigTable)
        .filter(AgenticWorkflowConfigTable.is_active.is_(True))
        .order_by(AgenticWorkflowConfigTable.version.desc())
        .first()
    )
    if config is None:
        raise NoActiveConfigError("No active workflow config found")
    return config


def _fixture_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def plan_subagent_eval(
    session: Session,
    subagent: str,
    article_urls: list[str] | None = None,
    replicates: int = 1,
    allow_inline_execution: bool = True,
) -> EvalLaunchPlan:
    """Resolve everything a launch needs without writing anything.

    Args:
        session: Caller-owned sync session. Only SELECTs are issued.
        subagent: Any alias ``normalize_subagent_name`` accepts; an unknown value
            is kept verbatim and simply matches no fixture directory.
        article_urls: URLs to run, duplicates preserved in order. ``None`` means
            the full committed set for the subagent from ``config/eval_articles.yaml``.
        replicates: Server-side expansion factor, 1..MAX_REPLICATES. Every URL is
            planned once per replicate.
        allow_inline_execution: Whether URLs with a fixture but no DB article row
            may run the extractor inline in the calling process. The MCP tool
            passes ``False`` so those rows are reported as skipped instead.

    Raises:
        EvalLaunchError: bad ``subagent`` or ``replicates``.
        NoActiveConfigError: no active workflow config row.
    """
    raw_subagent = str(subagent or "").strip()
    if not raw_subagent:
        raise EvalLaunchError("subagent is required")
    if isinstance(replicates, bool) or not isinstance(replicates, int) or not 1 <= replicates <= MAX_REPLICATES:
        raise EvalLaunchError(f"replicates must be an integer between 1 and {MAX_REPLICATES}, got {replicates!r}")
    allow_inline_execution = bool(allow_inline_execution)

    config = _active_config(session)
    canonical = normalize_subagent_name(raw_subagent) or raw_subagent

    committed = committed_eval_articles(canonical)
    urls: list[str] = [url for url, _ in committed] if article_urls is None else list(article_urls)
    expected_counts = dict(committed)

    url_to_static = load_static_eval_articles(canonical)
    url_to_id = resolve_article_ids_by_urls(session, list(dict.fromkeys(url for url in urls if url)))

    agent_name = SUBAGENT_TO_EXTRACT_AGENT.get(canonical)
    provider, model = resolve_agent_provider_model(config.agent_models, agent_name)
    is_local_provider = (provider or "").strip().lower() in LOCAL_PROVIDERS

    rows: list[EvalLaunchRow] = []
    for replicate in range(1, replicates + 1):
        for url in urls:
            static_entry = url_to_static.get(url) or {}
            content = static_entry.get("content") or ""
            article_id = url_to_id.get(url)
            if not content:
                status = ROW_NO_FIXTURE
            elif article_id is None:
                status = ROW_NO_DB_ROW
            else:
                status = ROW_READY
            expected_items = static_entry.get("expected_items")
            acceptable_items = static_entry.get("acceptable_items")
            rows.append(
                EvalLaunchRow(
                    url=url,
                    replicate=replicate,
                    article_id=article_id,
                    status=status,
                    expected_count=expected_counts.get(url, 0),
                    expected_items=expected_items if isinstance(expected_items, list) else None,
                    acceptable_items=acceptable_items if isinstance(acceptable_items, list) else None,
                    fixture_title=static_entry.get("title", "") or "",
                    fixture_content=content,
                    fixture_content_sha256=_fixture_sha256(content) if content else None,
                )
            )

    return EvalLaunchPlan(
        subagent=canonical,
        agent_name=agent_name,
        config=config,
        config_id=config.id,
        config_version=config.version,
        run_label=f"v{config.version}",
        provider=provider,
        model=model,
        is_local_provider=is_local_provider,
        replicates=replicates,
        allow_inline_execution=allow_inline_execution,
        rows=tuple(rows),
        max_executions=max_eval_executions_per_launch(),
    )


def _failed_record(plan: EvalLaunchPlan, row: EvalLaunchRow) -> SubagentEvaluationTable:
    return SubagentEvaluationTable(
        subagent_name=plan.subagent,
        article_url=row.url,
        article_id=None,
        expected_count=row.expected_count,
        workflow_config_id=plan.config_id,
        workflow_config_version=plan.config_version,
        status="failed",
    )


async def _run_inline(session: Session, plan: EvalLaunchPlan, row: EvalLaunchRow) -> SubagentEvaluationTable:
    """Run the extractor in-process for a fixture with no DB article row.

    Startup seeding normally guarantees every committed fixture has a row, so
    this is the exception path. It scores the committed fixture text directly
    and persists a completed or failed eval record with no workflow execution.
    """
    config = plan.config
    agent_name = plan.agent_name
    agent_prompts = config.agent_prompts or {}
    if not agent_name or agent_name not in agent_prompts:
        record = _failed_record(plan, row)
        session.add(record)
        return record
    try:
        agent_prompt_data = agent_prompts[agent_name]
        prompt_config = (
            json.loads(agent_prompt_data["prompt"]) if isinstance(agent_prompt_data.get("prompt"), str) else None
        )
        if not prompt_config:
            raise ValueError(f"No prompt for {agent_name}")
        agent_models = config.agent_models or {}
        llm_service = LLMService(config_models=agent_models)
        agent_result = await llm_service.run_extraction_agent(
            agent_name=agent_name,
            content=row.fixture_content,
            title=row.fixture_title,
            url=row.url,
            prompt_config=prompt_config,
            max_extraction_retries=1,
            execution_id=None,
            model_name=agent_models.get(f"{agent_name}_model") or agent_models.get("ExtractAgent"),
            temperature=float(agent_models.get(f"{agent_name}_temperature", 0) or 0),
            top_p=float(agent_models.get(f"{agent_name}_top_p"))
            if agent_models.get(f"{agent_name}_top_p") is not None
            else None,
            provider=agent_models.get(f"{agent_name}_provider") or agent_models.get("ExtractAgent_provider"),
            attention_preprocessor_enabled=True,
            langfuse_session_id=f"eval_subagent_{plan.subagent}",
        )
        actual_count = actual_count_from_agent_result(plan.subagent, agent_result or {})
        if actual_count is None:
            actual_count = 0
        score = actual_count - row.expected_count
        raw_actual_items = raw_actual_items_from_agent_result(plan.subagent, agent_result or {})
        item_score = (
            score_items(
                row.expected_items,
                raw_actual_items,
                row.acceptable_items,
                subagent_name=plan.subagent,
            )
            if isinstance(row.expected_items, list)
            else None
        )
        record = SubagentEvaluationTable(
            subagent_name=plan.subagent,
            article_url=row.url,
            article_id=None,
            expected_count=row.expected_count,
            expected_items=row.expected_items,
            acceptable_items=row.acceptable_items,
            actual_count=actual_count,
            actual_items=item_score.actual if item_score else None,
            matched_count=item_score.matched_count if item_score else None,
            missed_count=item_score.missed_count if item_score else None,
            extra_count=item_score.extra_count if item_score else None,
            neutral_count=item_score.neutral_count if item_score else None,
            score=score,
            workflow_config_id=plan.config_id,
            workflow_config_version=plan.config_version,
            workflow_execution_id=None,
            status="completed",
            completed_at=datetime.utcnow(),
        )
        session.add(record)
        logger.info(
            "Static eval %s url=%s actual=%s expected=%s",
            plan.subagent,
            row.url[:50],
            actual_count,
            row.expected_count,
        )
        return record
    except Exception as e:
        logger.warning("Static eval failed for %s: %s", row.url[:50], e)
        record = _failed_record(plan, row)
        session.add(record)
        return record


def _enqueue_eval_execution(article_id: int, execution_id: int, countdown: float) -> None:
    """Enqueue one eval workflow run.

    Imported lazily, like the MCP retry tool does, so importing this module
    never loads the Celery app; tests patch this seam instead of the task.
    """
    from src.worker.celery_app import trigger_agentic_workflow

    trigger_agentic_workflow.apply_async(args=[article_id, execution_id], countdown=countdown)


def ensure_broker_reachable(max_retries: int = 1) -> None:
    """Raise EvalDispatchError when the Celery broker cannot be reached.

    Cheap preflight for callers that must not leave pending rows behind when no
    worker will ever pick them up. Imported lazily like the enqueue seam.
    """
    from src.worker.celery_app import celery_app

    try:
        with celery_app.connection_for_write() as connection:
            connection.ensure_connection(
                max_retries=max_retries,
                interval_start=0,
                interval_step=0.2,
                interval_max=0.5,
            )
    except Exception as e:
        raise EvalDispatchError(f"Celery broker is unreachable, nothing was launched: {e}") from e


def _dispatch(executions: list[dict[str, Any]], concurrency_throttle_seconds: float) -> None:
    """Enqueue the committed executions with a broker-side stagger.

    The internal EVAL_STAGGER_SECONDS floor is always applied; the caller's
    concurrency throttle adds on top to spread provider token budget across
    the run window.
    """
    per_step_countdown = EVAL_STAGGER_SECONDS + concurrency_throttle_seconds
    for idx, exec_info in enumerate(executions):
        try:
            _enqueue_eval_execution(exec_info["article_id"], exec_info["execution_id"], idx * per_step_countdown)
        except Exception as e:
            raise EvalDispatchError(
                f"Celery dispatch failed after {idx} of {len(executions)} executions were enqueued; "
                f"the remaining rows are committed as pending and need a worker-side recovery: {e}"
            ) from e
        logger.info(
            "Triggered workflow execution %s for article %s",
            exec_info["execution_id"],
            exec_info["article_id"],
        )


async def launch_subagent_eval(
    session: Session,
    plan: EvalLaunchPlan,
    concurrency_throttle_seconds: float = 5.0,
    initiated_by: str = "web",
) -> EvalLaunchResult:
    """Perform the writes and Celery dispatch for a plan.

    Order matters and is the same as the route always used: create one
    execution plus one eval record per ready row, run inline rows when the plan
    allows it, commit, then enqueue with increasing countdowns. The cap and the
    argument checks all run before the first ``session.add``.

    Raises:
        EvalLaunchCapExceededError: before any write, when the plan exceeds the cap.
        EvalLaunchError: bad throttle or empty ``initiated_by``.
        EvalDispatchError: after commit, when the broker refuses a dispatch.
    """
    throttle = float(concurrency_throttle_seconds)
    if not 0.0 <= throttle <= MAX_THROTTLE_SECONDS:
        raise EvalLaunchError(f"concurrency_throttle_seconds must be between 0 and {MAX_THROTTLE_SECONDS:g}")
    initiated_by = str(initiated_by or "").strip()
    if not initiated_by:
        raise EvalLaunchError("initiated_by is required")
    if plan.exceeds_cap:
        raise EvalLaunchCapExceededError(
            f"Requested {plan.total_executions} eval executions; "
            f"{MAX_EVAL_EXECUTIONS_ENV}={plan.max_executions} caps a single launch"
        )

    dispatched: list[tuple[AgenticWorkflowExecutionTable, SubagentEvaluationTable, EvalLaunchRow]] = []
    inline_records: list[SubagentEvaluationTable] = []
    skipped: list[dict[str, Any]] = []

    for row in plan.rows:
        if row.status == ROW_NO_FIXTURE:
            skipped.append({"url": row.url, "replicate": row.replicate, "reason": ROW_NO_FIXTURE})
            continue
        if row.status == ROW_NO_DB_ROW:
            if not plan.allow_inline_execution:
                skipped.append({"url": row.url, "replicate": row.replicate, "reason": ROW_NO_DB_ROW})
                continue
            inline_records.append(await _run_inline(session, plan, row))
            continue

        execution = AgenticWorkflowExecutionTable(article_id=row.article_id, status="pending")
        session.add(execution)
        attach_snapshot(
            session,
            execution,
            build_config_snapshot(
                plan.config,
                extra={
                    "eval_run": True,
                    "skip_os_detection": True,  # Bypass OS detection for evals
                    "skip_rank_agent": True,  # Bypass rank agent for evals
                    "skip_sigma_generation": True,  # Skip SIGMA generation for evals
                    "subagent_eval": plan.subagent,
                    "eval_fixture_content": row.fixture_content,
                    "eval_fixture_content_sha256": row.fixture_content_sha256,
                    "initiated_by": initiated_by,
                },
            ),
        )
        session.flush()  # Get execution.id
        eval_record = SubagentEvaluationTable(
            subagent_name=plan.subagent,
            article_url=row.url,
            article_id=row.article_id,
            expected_count=row.expected_count,
            expected_items=row.expected_items,
            acceptable_items=row.acceptable_items,
            workflow_execution_id=execution.id,
            workflow_config_id=plan.config_id,
            workflow_config_version=plan.config_version,
            status="pending",
        )
        session.add(eval_record)
        dispatched.append((execution, eval_record, row))

    # Assign eval record ids before the response is built so callers can poll them.
    session.flush()
    session.commit()

    executions = [
        {
            "execution_id": execution.id,
            "article_id": row.article_id,
            "url": row.url,
            "eval_record_id": eval_record.id,
        }
        for execution, eval_record, row in dispatched
    ]
    _dispatch(executions, throttle)

    return EvalLaunchResult(
        plan=plan,
        initiated_by=initiated_by,
        executions=executions,
        inline_eval_record_ids=[record.id for record in inline_records],
        skipped=skipped,
    )
