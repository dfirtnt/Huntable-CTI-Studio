"""
Agentic Workflow using LangGraph for processing high-hunt-score articles.

This workflow processes articles through 7 steps:
0. Platform Detection (classifies OS/platforms for capability routing)
1. Junk Filter
2. LLM Rank Article
3. Extract Agent
4. Generate SIGMA rules
5. Similarity Search
6. Promote to Queue
"""

import contextlib
import json
import logging
import re
from datetime import datetime
from typing import Any, TypedDict

import yaml
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.database.models import (
    AgenticWorkflowExecutionTable,
    ArticleTable,
    SigmaRuleQueueTable,
    SubagentEvaluationTable,
)
from src.services.eval_item_scorer import score_items
from src.services.llm_service import LLMService
from src.services.lmstudio_model_loader import auto_load_workflow_models
from src.services.sigma_eval_service import (
    is_sigma_eval_execution,
    mark_pending_sigma_evals_as_failed,
    score_and_persist_execution,
)
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.workflow_provider_options import _probe_lmstudio
from src.services.workflow_trigger_service import WorkflowTriggerService
from src.utils.content_filter import ContentFilter
from src.utils.langfuse_client import (
    get_active_trace_id,
    log_workflow_step,
    score_langfuse_trace,
    trace_workflow_execution,
)
from src.utils.subagent_utils import build_subagent_lookup_values, normalize_subagent_name
from src.workflows.status_utils import (
    TERMINATION_REASON_JUNK_FILTER,
    TERMINATION_REASON_NO_SIGMA_RULES,
    TERMINATION_REASON_RANK_THRESHOLD,
    mark_execution_completed,
)

logger = logging.getLogger(__name__)

PLATFORM_WINDOWS = "windows"
PLATFORM_LINUX = "linux"
PLATFORM_MACOS = "macos"
PLATFORM_CROSS = "cross_platform"
PLATFORM_UNKNOWN = "unknown"
SUPPORTED_PLATFORM_VALUES = {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS, PLATFORM_CROSS, PLATFORM_UNKNOWN}

AGENT_PLATFORM_CAPABILITIES: dict[str, set[str]] = {
    "CmdlineExtract": {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS, PLATFORM_CROSS, PLATFORM_UNKNOWN},
    "ProcTreeExtract": {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS, PLATFORM_CROSS, PLATFORM_UNKNOWN},
    "HuntQueriesExtract": {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS, PLATFORM_CROSS, PLATFORM_UNKNOWN},
    "RegistryExtract": {PLATFORM_WINDOWS},
    "ServicesExtract": {PLATFORM_WINDOWS},
    "ScheduledTasksExtract": {PLATFORM_WINDOWS},
    "NetworkIndicatorExtract": {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS, PLATFORM_CROSS, PLATFORM_UNKNOWN},
}

OBSERVABLE_TELEMETRY_CATEGORY: dict[str, str] = {
    "cmdline": "process_creation",
    "process_lineage": "process_creation",
    "hunt_queries": "hunt_query",
    "registry_artifacts": "registry",
    "windows_services": "service_creation",
    "scheduled_tasks": "scheduled_task",
    "network_indicators": "network_connection",
}

WINDOWS_ONLY_OBSERVABLE_TYPES = {"registry_artifacts", "windows_services", "scheduled_tasks"}


def _bool_from_value(val: Any) -> bool:
    """Normalize various truthy/falsey inputs to a boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() == "true"
    return bool(val)


def _normalize_platform_value(value: Any) -> str:
    """Normalize OS/platform labels into the observable platform vocabulary."""
    if value is None:
        return PLATFORM_UNKNOWN
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"windows", "win"}:
        return PLATFORM_WINDOWS
    if text in {"linux"}:
        return PLATFORM_LINUX
    if text in {"macos", "mac", "mac_os", "darwin", "osx", "mac_os_x"}:
        return PLATFORM_MACOS
    if text in {"multiple", "multi", "cross_platform", "crossplatform", "platform_agnostic"}:
        return PLATFORM_CROSS
    if text in SUPPORTED_PLATFORM_VALUES:
        return text
    return PLATFORM_UNKNOWN


def _platforms_from_os_detection(detected_os: Any, os_result: dict[str, Any] | None) -> list[str]:
    """Build article-level platform context from OS detection output."""
    platforms: list[str] = []
    os_data = os_result if isinstance(os_result, dict) else {}
    explicit = os_data.get("platforms_detected")
    if isinstance(explicit, list):
        platforms.extend(_normalize_platform_value(item) for item in explicit)

    detected_platform = _normalize_platform_value(detected_os or os_data.get("operating_system"))
    if detected_platform == PLATFORM_CROSS:
        similarities = os_data.get("similarities", {})
        if isinstance(similarities, dict):
            for label in ("Windows", "Linux", "MacOS"):
                score = similarities.get(label)
                if isinstance(score, (int, float)) and score > 0:
                    platforms.append(_normalize_platform_value(label))
    elif detected_platform != PLATFORM_UNKNOWN:
        platforms.append(detected_platform)

    if not platforms:
        similarities = os_data.get("similarities", {})
        if isinstance(similarities, dict):
            scored = [
                (_normalize_platform_value(label), score)
                for label, score in similarities.items()
                if isinstance(score, (int, float)) and score > 0
            ]
            scored = [(platform, score) for platform, score in scored if platform in SUPPORTED_PLATFORM_VALUES]
            if scored:
                best_score = max(score for _, score in scored)
                platforms.extend(platform for platform, score in scored if score == best_score)

    deduped = []
    for platform in platforms:
        if platform in SUPPORTED_PLATFORM_VALUES and platform not in deduped:
            deduped.append(platform)
    return deduped or [PLATFORM_UNKNOWN]


def _make_skip_record(
    *,
    agent_name: str,
    reason_code: str,
    reason: str,
    detected_platforms: list[str],
    telemetry_categories: list[str] | None = None,
) -> dict[str, Any]:
    """Return a structured extractor skip/capability record."""
    return {
        "extractor": agent_name,
        "status": "skipped",
        "reason_code": reason_code,
        "reason": reason,
        "supported_platforms": sorted(AGENT_PLATFORM_CAPABILITIES.get(agent_name, set())),
        "detected_platforms": detected_platforms,
        "telemetry_categories": telemetry_categories or [],
    }


def _agent_supported_for_platforms(agent_name: str, detected_platforms: list[str]) -> bool:
    """Return True when an extractor can run for at least one detected platform."""
    capabilities = AGENT_PLATFORM_CAPABILITIES.get(agent_name)
    if not capabilities:
        return True
    return bool(capabilities.intersection(detected_platforms))


def _infer_observable_platform(
    observable_type: str,
    item: Any,
    article_platforms: list[str],
) -> tuple[str, str, str]:
    """Infer observable-scoped platform metadata without over-claiming mixed evidence."""
    if isinstance(item, dict):
        for key in ("platform", "os", "operating_system"):
            if item.get(key):
                platform = _normalize_platform_value(item.get(key))
                if platform != PLATFORM_UNKNOWN:
                    return platform, "high", f"Extractor emitted {key}={item.get(key)!r}."

    if observable_type in WINDOWS_ONLY_OBSERVABLE_TYPES:
        return PLATFORM_WINDOWS, "high", f"{observable_type} is Windows-only telemetry in phase one."

    concrete_platforms = [p for p in article_platforms if p in {PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS}]
    if len(concrete_platforms) == 1:
        return concrete_platforms[0], "medium", "Single article-level platform detected."

    if PLATFORM_CROSS in article_platforms and len(article_platforms) == 1:
        return PLATFORM_CROSS, "medium", "Article-level platform detection is cross-platform."

    return PLATFORM_UNKNOWN, "low", "Observable evidence did not uniquely identify a platform."


def _logsource_hint_for_observable(platform: str, telemetry_category: str) -> dict[str, Any] | None:
    """Return a Sigma logsource hint when phase-one support is explicit."""
    if telemetry_category == "process_creation" and platform in {PLATFORM_WINDOWS, PLATFORM_LINUX}:
        return {"product": platform, "category": "process_creation"}
    if telemetry_category == "network_connection":
        if platform in {PLATFORM_WINDOWS, PLATFORM_LINUX}:
            return {"product": platform, "category": "network_connection"}
        return {"category": "network_connection"}
    if telemetry_category == "registry":
        return {"product": "windows", "category": "registry_event"}
    if telemetry_category == "service_creation":
        return {"product": "windows", "category": "service_creation"}
    if telemetry_category == "scheduled_task":
        return {"product": "windows", "category": "scheduled_task"}
    return None


def _enrich_observable_metadata(
    obs_entry: dict[str, Any],
    *,
    item: Any,
    observable_type: str,
    article_platforms: list[str],
) -> None:
    """Add platform/telemetry routing metadata to a merged observable entry."""
    platform, platform_confidence, platform_rationale = _infer_observable_platform(
        observable_type, item, article_platforms
    )
    telemetry_category = None
    telemetry_confidence = "medium"
    logsource_hint = None
    if isinstance(item, dict):
        telemetry_category = item.get("telemetry_category") or item.get("telemetry_type")
        telemetry_confidence = str(item.get("telemetry_confidence") or telemetry_confidence)
        logsource_hint = item.get("logsource_hint") or item.get("logsource")

    telemetry_category = str(telemetry_category or OBSERVABLE_TELEMETRY_CATEGORY.get(observable_type, observable_type))
    if logsource_hint is None:
        logsource_hint = _logsource_hint_for_observable(platform, telemetry_category)

    obs_entry["platform"] = platform
    obs_entry["platform_confidence"] = platform_confidence
    obs_entry["platform_rationale"] = platform_rationale
    obs_entry["telemetry_category"] = telemetry_category
    obs_entry["telemetry_confidence"] = telemetry_confidence
    if logsource_hint is not None:
        obs_entry["logsource_hint"] = logsource_hint


def _observable_sigma_eligible(obs: dict[str, Any]) -> bool:
    """Return True when an observable has enough routing metadata for Sigma generation."""
    if not isinstance(obs, dict):
        return False
    platform = _normalize_platform_value(obs.get("platform"))
    telemetry_category = obs.get("telemetry_category")
    logsource_hint = obs.get("logsource_hint")
    if platform in {PLATFORM_WINDOWS, PLATFORM_LINUX} and telemetry_category and logsource_hint:
        return True
    if platform in {PLATFORM_UNKNOWN, PLATFORM_CROSS} and telemetry_category and logsource_hint:
        return True
    return False


def _has_sigma_generation_eligible_observables(extraction_result: dict[str, Any] | None) -> bool:
    """Return True when at least one observable can safely drive Sigma generation."""
    if not isinstance(extraction_result, dict):
        return False
    observables = extraction_result.get("observables") or []
    if not isinstance(observables, list):
        return False
    return any(_observable_sigma_eligible(obs) for obs in observables)


def _stable_logsource_key(logsource_hint: Any) -> str:
    """Return a stable grouping key for an explicit Sigma logsource hint."""
    if isinstance(logsource_hint, dict):
        return json.dumps(logsource_hint, sort_keys=True, separators=(",", ":"))
    return str(logsource_hint or "")


def _sigma_generation_group_key(obs: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return the platform/telemetry/logsource group key for one observable."""
    if not _observable_sigma_eligible(obs):
        return None
    platform = _normalize_platform_value(obs.get("platform"))
    if platform == PLATFORM_MACOS:
        return None
    telemetry_category = str(obs.get("telemetry_category") or "")
    logsource_hint = obs.get("logsource_hint")
    return (platform, telemetry_category, _stable_logsource_key(logsource_hint))


def _make_grouped_extraction_result(
    extraction_result: dict[str, Any],
    *,
    group_key: tuple[str, str, str],
    observables: list[dict[str, Any]],
    original_indices: list[int],
) -> dict[str, Any]:
    """Build a Sigma input extraction_result for a single platform/logsource group."""
    platform, telemetry_category, _ = group_key
    grouped_observables = []
    for local_index, (obs, original_index) in enumerate(zip(observables, original_indices, strict=False)):
        grouped = dict(obs)
        grouped["original_observable_index"] = original_index
        grouped["group_observable_index"] = local_index
        grouped_observables.append(grouped)

    group_summary = dict(extraction_result.get("summary") or {})
    group_summary.update(
        {
            "count": len(grouped_observables),
            "platforms_detected": [platform],
            "telemetry_category": telemetry_category,
            "sigma_generation_group": {
                "platform": platform,
                "telemetry_category": telemetry_category,
                "logsource_hint": observables[0].get("logsource_hint") if observables else None,
                "observable_indices": original_indices,
            },
        }
    )

    grouped_content_lines = []
    for obs in grouped_observables:
        value = obs.get("value")
        if isinstance(value, dict):
            value_text = ", ".join(f"{k}={v}" for k, v in value.items() if v is not None and v != "")
        else:
            value_text = str(value or "")
        if value_text:
            grouped_content_lines.append(value_text)

    return {
        **extraction_result,
        "observables": grouped_observables,
        "summary": group_summary,
        "discrete_huntables_count": len(grouped_observables),
        "content": "\n".join(grouped_content_lines) or extraction_result.get("content", ""),
        "sigma_generation_group": group_summary["sigma_generation_group"],
    }


def _build_sigma_generation_groups(extraction_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Group Sigma-eligible observables by platform, telemetry category, and logsource."""
    if not isinstance(extraction_result, dict):
        return []
    observables = extraction_result.get("observables") or []
    if not isinstance(observables, list):
        return []

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for original_index, obs in enumerate(observables):
        if not isinstance(obs, dict):
            continue
        group_key = _sigma_generation_group_key(obs)
        if group_key is None:
            continue
        bucket = grouped.setdefault(
            group_key,
            {
                "group_key": group_key,
                "platform": group_key[0],
                "telemetry_category": group_key[1],
                "logsource_hint": obs.get("logsource_hint"),
                "observables": [],
                "original_indices": [],
            },
        )
        bucket["observables"].append(obs)
        bucket["original_indices"].append(original_index)

    result = []
    for group in grouped.values():
        result.append(
            {
                **group,
                "extraction_result": _make_grouped_extraction_result(
                    extraction_result,
                    group_key=group["group_key"],
                    observables=group["observables"],
                    original_indices=group["original_indices"],
                ),
            }
        )
    return result


def _build_sigma_full_content_fallback_group(
    extraction_result: dict[str, Any] | None,
    *,
    content: str,
    platforms_detected: list[str] | None = None,
) -> dict[str, Any]:
    """Build one legacy full-content Sigma generation group when no observables qualify."""
    platforms = platforms_detected or []
    platform = platforms[0] if len(platforms) == 1 else PLATFORM_UNKNOWN
    group = {
        "platform": platform,
        "telemetry_category": "full_content",
        "logsource_hint": None,
        "observable_indices": [],
        "generation_basis": "full_content_fallback",
    }
    grouped_result = dict(extraction_result or {})
    grouped_result["observables"] = []
    grouped_result["content"] = content
    grouped_result["discrete_huntables_count"] = 0
    grouped_result["summary"] = {
        **(grouped_result.get("summary") or {}),
        "count": 0,
        "platforms_detected": platforms,
        "telemetry_category": "full_content",
        "sigma_generation_group": group,
    }
    grouped_result["sigma_generation_group"] = group
    return {
        "group_key": (platform, "full_content", ""),
        "platform": platform,
        "telemetry_category": "full_content",
        "logsource_hint": None,
        "observables": [],
        "original_indices": [],
        "extraction_result": grouped_result,
    }


def _rebase_group_observable_indices(rule: dict[str, Any], original_indices: list[int]) -> None:
    """Translate group-local observables_used indices back to execution-wide indices."""
    raw_indices = rule.get("observables_used")
    if not isinstance(raw_indices, list):
        return
    rebased = []
    for idx in raw_indices:
        if isinstance(idx, int) and 0 <= idx < len(original_indices):
            rebased.append(original_indices[idx])
    rule["observables_used"] = rebased


_INFRA_FAILURE_RE = re.compile(
    r"lmstudio is not ready|no model.{0,20}loaded|ensure lmstudio is running"
    r"|context.{0,15}(size|length|window).{0,15}exceeded"
    r"|must not contain 'user_template'|promptconfigvalidation"
    r"|\"code\":\s*\"model_not_found\"|does not exist or you do not have access"
    r"|openai api key is not configured"
    r"|generator didn't stop after throw",
    re.IGNORECASE,
)


def _extraction_is_infra_failure(extraction_result: dict | None) -> bool:
    """Return True if every executed (non-skipped) subagent failed with an infra error."""
    if not isinstance(extraction_result, dict):
        return False
    subresults = extraction_result.get("subresults", {})
    if not isinstance(subresults, dict) or not subresults:
        return False

    executed = []
    for sr in subresults.values():
        if not isinstance(sr, dict):
            continue
        raw = sr.get("raw", {})
        if isinstance(raw, dict) and raw.get("status") == "skipped_for_eval":
            continue
        executed.append(sr)

    if not executed:
        return False

    for sr in executed:
        raw = sr.get("raw", {}) if isinstance(sr.get("raw"), dict) else {}
        err = sr.get("error") or raw.get("error") or ""
        if not (isinstance(err, str) and _INFRA_FAILURE_RE.search(err)):
            return False

    return True


def _all_extractors_errored(extraction_result: dict | None) -> tuple[bool, str | None]:
    """Return (True, reason) if every executed subagent returned an error, (False, None) otherwise.

    Broader than _extraction_is_infra_failure: catches any error type, not just known
    infra patterns.  Used to set success=False on the workflow_completed Langfuse span
    when LangGraph reaches END without raising (the graph swallows subagent errors so
    final_state carries no top-level 'error' key even when nothing was extracted).
    """
    if not isinstance(extraction_result, dict):
        return False, None
    subresults = extraction_result.get("subresults", {})
    if not isinstance(subresults, dict) or not subresults:
        return False, None

    executed = []
    for sr in subresults.values():
        if not isinstance(sr, dict):
            continue
        raw = sr.get("raw", {})
        if isinstance(raw, dict) and raw.get("status") == "skipped_for_eval":
            continue
        executed.append(sr)

    if not executed:
        return False, None

    errors = []
    for sr in executed:
        raw = sr.get("raw", {}) if isinstance(sr.get("raw"), dict) else {}
        err = sr.get("error") or raw.get("error") or ""
        if not (isinstance(err, str) and err):
            return False, None  # at least one subagent succeeded
        errors.append(err)

    # Every executed subagent errored -- build a compact reason string
    unique_errors = list(dict.fromkeys(errors))  # deduplicate, preserve order
    reason = f"All {len(executed)} extractor(s) failed: {'; '.join(unique_errors[:2])}"
    if len(unique_errors) > 2:
        reason += f" (and {len(unique_errors) - 2} more)"
    return True, reason


def summarize_rule_novelty(match_result: dict, threshold: float = 0.5) -> dict:
    """Classify one rule's novelty comparison for the review queue (todo 001, C1+C2).

    Distinguishes a *scored* low/zero result from an *inconclusive* one: the
    comparator evaluated candidates but found zero behavioral matches. The old
    code collapsed the inconclusive case into ``max_similarity=0.0``, which
    silently disabled novelty suppression for ~86% of the queue.

    Inconclusive => ``max_similarity=None`` (unscored), never a confident ``0.0``.

    Two distinct ``total==0`` cases must NOT be conflated:
    - **Empty corpus / nothing to compare against** (no ``no_atoms_extracted`` flag):
      genuinely novel, NOT inconclusive — keep the ``0.0`` semantics.
    - **Proposed rule produced no atoms** (``no_atoms_extracted`` set by the
      assess_novelty guard): a FAILURE TO ASSESS. This IS inconclusive, so it routes
      to needs_review and a human sees it — fail open, but never silently as a
      confident pending novel.
    """
    matches = match_result.get("matches", []) or []
    total = int(match_result.get("total_candidates_evaluated", 0) or 0)
    behavioral = int(match_result.get("behavioral_matches_found", 0) or 0)
    no_atoms = bool(match_result.get("no_atoms_extracted"))
    sims = [m.get("similarity", 0.0) for m in matches]
    inconclusive = no_atoms or (total > 0 and behavioral == 0)
    # SigmaSim Finding B: surface whether the proposed rule's logsource resolved to a
    # canonical telemetry class. None => the rule fell to the weak logsource_key fallback
    # (e.g. SigmaAgent emitting bare `service: sysmon` with no category/EventID for a
    # process_creation-shaped rule). We keep the rule (fail open) but flag the degraded-dedup
    # condition so it is visible — logged + queryable via rule_metadata — instead of silent.
    canonical_class = match_result.get("canonical_class")
    return {
        "max_similarity": None if inconclusive else (max(sims) if sims else 0.0),
        "total_candidates_evaluated": total,
        "behavioral_matches_found": behavioral,
        "comparator_inconclusive": inconclusive,
        "canonical_class": canonical_class,
        "logsource_unresolved": canonical_class is None,
        "logsource_lint_failures": ["unresolved_logsource"] if canonical_class is None else [],
    }


class WorkflowState(TypedDict):
    """State for the agentic workflow."""

    article_id: int
    execution_id: int
    article: ArticleTable | None
    config: dict[str, Any] | None
    eval_run: bool
    skip_rank_agent: bool

    # Step 0: Platform Detection
    os_detection_result: dict[str, Any] | None
    detected_os: str | None
    # Article-level platform context (controlled vocabulary) for capability routing.
    # Declared as a channel so it propagates between nodes instead of being dropped.
    platforms_detected: list[str] | None

    # Step 1: Junk Filter
    filtered_content: str | None
    junk_filter_result: dict[str, Any] | None

    # Step 1: LLM Ranking
    ranking_score: float | None
    ranking_reasoning: str | None
    should_continue: bool

    # Step 2: Extract Agent
    extraction_result: dict[str, Any] | None
    discrete_huntables_count: int | None

    # Step 3: SIGMA Generation
    sigma_rules: list | None

    # Step 4: Similarity Search
    similarity_results: list | None
    max_similarity: float | None

    # Step 5: Queue Promotion
    queued_rules: list | None

    # Error handling
    error: str | None
    current_step: str
    status: str | None
    termination_reason: str | None
    termination_details: dict[str, Any] | None


def _mark_pending_subagent_evals_as_failed(
    execution: "AgenticWorkflowExecutionTable",
    db_session: "Session",
) -> int:
    """Mark any still-pending SubagentEvaluationTable rows for this execution as failed.

    Called when a workflow execution fails before reaching extract_agent (e.g. the
    os_detection pool-corruption bug). Without this, eval rows linger in "pending"
    forever and the eval report can't tell runaway failures from in-flight work.

    Returns the number of rows updated.
    """
    if execution is None or getattr(execution, "id", None) is None:
        return 0
    try:
        pending_evals = (
            db_session.query(SubagentEvaluationTable)
            .filter(
                SubagentEvaluationTable.workflow_execution_id == execution.id,
                SubagentEvaluationTable.status == "pending",
            )
            .all()
        )
        if not pending_evals:
            return 0

        now = datetime.now()
        for eval_record in pending_evals:
            eval_record.status = "failed"
            eval_record.completed_at = now

        db_session.commit()
        logger.info(
            f"Marked {len(pending_evals)} orphaned SubagentEvaluation row(s) as failed for execution {execution.id}"
        )
        return len(pending_evals)
    except Exception as e:
        logger.error(
            f"Error marking orphaned subagent_evaluations for execution {execution.id}: {e}",
            exc_info=True,
        )
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001 -- best-effort rollback; original error already logged
            pass
        return 0


def _update_subagent_eval_on_completion(
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
    extraction_result_override: dict[str, Any] | None = None,
) -> None:
    """
    Update SubagentEvaluationTable when workflow execution completes.
    Extracts count from extraction_result.subresults.{subagent_name} and calculates score.
    If extraction_result_override is provided (e.g. from workflow state), use it instead of execution.extraction_result.
    """
    try:
        config_snapshot = execution.config_snapshot or {}
        subagent_name = normalize_subagent_name(config_snapshot.get("subagent_eval"))

        if not subagent_name:
            # Not an eval run
            return

        # For hunt_queries, find eval records (hunt_queries, hunt_queries_edr, or hunt_queries_sigma)
        # run-subagent-eval creates records with subagent_name "hunt_queries"; also support legacy EDR/SIGMA
        if subagent_name == "hunt_queries":
            eval_records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.workflow_execution_id == execution.id,
                    SubagentEvaluationTable.subagent_name.in_(
                        ["hunt_queries", "hunt_queries_edr", "hunt_queries_sigma"]
                    ),
                )
                .all()
            )

            if not eval_records:
                logger.warning(f"No SubagentEvaluation records found for execution {execution.id} (hunt_queries)")
                return

            for eval_record in eval_records:
                _update_single_eval_record(
                    eval_record,
                    execution,
                    db_session,
                    extraction_result_override=extraction_result_override,
                )
            return

        # Standard single eval record
        eval_record = (
            db_session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.workflow_execution_id == execution.id)
            .first()
        )

        if not eval_record:
            logger.warning(f"No SubagentEvaluation record found for execution {execution.id}")
            return

        _update_single_eval_record(
            eval_record,
            execution,
            db_session,
            extraction_result_override=extraction_result_override,
        )

    except Exception as e:
        logger.error(f"Error updating SubagentEvaluation for execution {execution.id}: {e}", exc_info=True)
        # Don't fail the workflow if eval update fails. Per-record terminal state is
        # handled inside _update_single_eval_record; here we just keep the session clean
        # so a partial transaction can't poison later commits.
        with contextlib.suppress(Exception):
            db_session.rollback()


def _extract_actual_count(subagent_name: str, subresults: dict, execution_id: int) -> int | None:
    """Extract actual count from subresults based on subagent name."""
    # Handle historical hunt_queries_edr records (backward compatibility)
    if subagent_name == "hunt_queries_edr":
        hunt_queries_result = subresults.get("hunt_queries", {})
        if not isinstance(hunt_queries_result, dict):
            logger.warning(f"No hunt_queries result in subresults for execution {execution_id}")
            return None
        # Extract EDR query count from old dual-format results
        query_count = hunt_queries_result.get("query_count")
        if query_count is None:
            queries = hunt_queries_result.get("queries", [])
            query_count = len(queries) if isinstance(queries, list) else 0
        return query_count

    # hunt_queries: prefer count (current contract), then len(queries/items).
    if subagent_name == "hunt_queries":
        hq = subresults.get("hunt_queries", {})
        if not isinstance(hq, dict):
            logger.warning(f"No hunt_queries result in subresults for execution {execution_id}")
            return None
        n = hq.get("count")
        if n is not None:
            return int(n)
        q = hq.get("queries") or hq.get("items", [])
        return len(q) if isinstance(q, list) else 0

    # Standard subagent handling (cmdline, process_lineage)
    subagent_result = subresults.get(subagent_name, {})
    if not isinstance(subagent_result, dict):
        logger.warning(f"No {subagent_name} result in subresults for execution {execution_id}")
        return None

    # Extract count (prefer count field, fallback to items array length)
    actual_count = subagent_result.get("count")
    if actual_count is None:
        items = subagent_result.get("items", [])
        actual_count = len(items) if isinstance(items, list) else 0

    return actual_count


def _extract_actual_items(subagent_name: str, subresults: dict) -> list[str] | None:
    """Extract the items list from subresults for item-level scoring.

    Returns a list of strings or None if the subagent type doesn't support item lists.
    """
    if subagent_name in ("hunt_queries", "hunt_queries_edr", "hunt_queries_sigma"):
        # Hunt queries produce query text objects, not simple string items
        return None

    subagent_result = subresults.get(subagent_name, {})
    if not isinstance(subagent_result, dict):
        return None

    items = subagent_result.get("items")
    if not isinstance(items, list):
        return None

    # Flatten: each item may be a string, or a dict with a "cmdline" / "command" / "value" field
    flat: list[str] = []
    for item in items:
        if isinstance(item, str):
            flat.append(item)
        elif isinstance(item, dict):
            # Try common string payload fields in priority order
            for field in ("cmdline", "command", "commandline", "value", "name"):
                v = item.get(field)
                if isinstance(v, str) and v.strip():
                    flat.append(v.strip())
                    break
    return flat if flat else None


def _update_single_eval_record(
    eval_record: SubagentEvaluationTable,
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
    extraction_result_override: dict[str, Any] | None = None,
) -> None:
    """Update a single eval record with actual count from execution."""
    try:
        # Prefer override (e.g. from workflow state) so skip-sigma path has extraction_result
        extraction_result = (
            extraction_result_override if extraction_result_override is not None else execution.extraction_result
        )
        if not extraction_result or not isinstance(extraction_result, dict):
            logger.warning(f"No extraction_result for execution {execution.id}")
            eval_record.status = "failed"
            db_session.commit()
            return

        subresults = extraction_result.get("subresults", {})
        if not isinstance(subresults, dict):
            logger.warning(f"No subresults in extraction_result for execution {execution.id}")
            eval_record.status = "failed"
            db_session.commit()
            return

        # Extract count based on subagent type
        actual_count = _extract_actual_count(eval_record.subagent_name, subresults, execution.id)

        if actual_count is None:
            eval_record.status = "failed"
            db_session.commit()
            return

        if not isinstance(actual_count, int):
            actual_count = int(actual_count) if actual_count else 0

        # Calculate score
        score = actual_count - eval_record.expected_count

        # Item-level scoring (only when expected_items ground truth is available).
        # When the model returns zero items, _extract_actual_items returns None to signal
        # "no items field present at all". For scoring purposes that's identical to an
        # empty list -- the run completed and produced nothing -- so we coerce here so
        # the zero-extraction case still scores (matched=0, missed=len(expected), extra=0).
        if eval_record.expected_items and isinstance(eval_record.expected_items, list):
            actual_items = _extract_actual_items(eval_record.subagent_name, subresults)
            if actual_items is None:
                actual_items = []
            result = score_items(eval_record.expected_items, actual_items)
            eval_record.actual_items = actual_items
            eval_record.matched_count = result.matched_count
            eval_record.missed_count = result.missed_count
            eval_record.extra_count = result.extra_count

        # Update eval record
        eval_record.actual_count = actual_count
        eval_record.score = score
        eval_record.status = "completed"
        eval_record.completed_at = datetime.now()

        # Commit the update
        db_session.commit()

        logger.info(
            f"Updated SubagentEvaluation {eval_record.id}: "
            f"subagent={eval_record.subagent_name}, expected={eval_record.expected_count}, "
            f"actual={actual_count}, score={score}"
        )
    except Exception as e:
        logger.error(f"Error updating SubagentEvaluation for execution {execution.id}: {e}", exc_info=True)
        # Don't fail the workflow if eval update fails -- but never leave the record
        # stranded in 'pending', or the poll loop shows it as permanently "stuck".
        # Roll back the partial transaction, then write a terminal 'failed' state.
        try:
            db_session.rollback()
            eval_record.status = "failed"
            db_session.commit()
        except Exception:
            logger.error(
                f"Failed to mark SubagentEvaluation {eval_record.id} as failed after update error",
                exc_info=True,
            )


# CamelCase-keyed map used by the supervisor loop to resolve agent names to subagent aliases.
# Canonical source: src/utils/subagent_utils.py (lowercase keys).  This copy uses CamelCase
# because the workflow loop iterates with CamelCase agent names.
_AGENT_NAME_TO_SUBAGENT: dict[str, str] = {
    "CmdlineExtract": "cmdline",
    "ProcTreeExtract": "process_lineage",
    "HuntQueriesExtract": "hunt_queries",
    "RegistryExtract": "registry_artifacts",
    "ServicesExtract": "windows_services",
    "ScheduledTasksExtract": "scheduled_tasks",
    "NetworkIndicatorExtract": "network_indicators",
}


def _is_agent_allowed(
    agent_name: str,
    execution: Any,
    subagent_eval: str | None,
    eval_lookup_values: set | None,
    execution_id: int | str,
) -> bool:
    """Return True if *agent_name* should run, False if it should be blocked.

    Reads ``subagent_eval`` from *execution.config_snapshot* (with fallback to
    the *subagent_eval* variable), builds a merged lookup set, and checks
    whether the agent matches.  Consolidates the three previously-separate
    eval-blocking checks into a single call.
    """
    # 1. Re-read subagent_eval from execution config_snapshot (defensive)
    raw_eval = None
    if execution and getattr(execution, "config_snapshot", None):
        raw_eval = execution.config_snapshot.get("subagent_eval")

    # Fallback to the variable
    if not raw_eval and subagent_eval:
        raw_eval = subagent_eval

    # 2. Build the lookup set
    eval_match: set[str] = set()
    if raw_eval:
        canonical, lookup_values = build_subagent_lookup_values(raw_eval)
        for v in lookup_values or set():
            if v is not None and str(v).strip():
                eval_match.add(str(v).strip().lower())
        if canonical and canonical not in eval_match:
            eval_match.add(canonical)
    # Merge in any pre-computed eval_lookup_values
    if eval_lookup_values:
        for v in eval_lookup_values:
            if v is not None and str(v).strip():
                eval_match.add(str(v).strip().lower())

    if not eval_match:
        return True

    # 3. Check whether this agent matches
    agent_subagent = _AGENT_NAME_TO_SUBAGENT.get(agent_name)
    normalized_subagent = str(agent_subagent).lower().strip() if agent_subagent else None
    normalized_name = agent_name.lower().strip()

    matches = (normalized_subagent in eval_match if normalized_subagent else False) or normalized_name in eval_match

    if matches:
        logger.info(
            f"[Workflow {execution_id}] Allowing {agent_name} to run -- matches eval_values={sorted(eval_match)}"
        )
    else:
        logger.error(
            f"[Workflow {execution_id}] BLOCKING {agent_name} (subagent={normalized_subagent}) "
            f"-- does not match eval_values={sorted(eval_match)}"
        )

    return matches


def _parse_agent_result(agent_name: str, result_key: str, agent_result: dict) -> tuple[list, dict]:
    """Parse an extraction agent's raw result into (items, subresult_entry).

    HuntQueriesExtract has custom normalization; all other agents share a
    generic path.  Error fields are copied uniformly for both paths.
    """
    items: list = []
    subresult_entry: dict

    if agent_name == "HuntQueriesExtract":
        # Extract query-envelope items. Sigma rules are represented as type="sigma".
        edr_queries = agent_result.get("queries", [])

        # Normalize field names for UI compatibility
        # LLM may return: platform, query_text, source_context
        # UI expects: type, query, context
        normalized_edr_queries = []
        for q in edr_queries:
            if isinstance(q, dict):
                normalized_q = {
                    "query": q.get("query") or q.get("query_text", ""),
                    "type": q.get("type") or q.get("platform", "unknown"),
                    "context": q.get("context") or q.get("source_context", ""),
                    # Preserve traceability fields through normalization
                    "source_evidence": q.get("source_evidence"),
                    "extraction_justification": q.get("extraction_justification"),
                    "confidence_score": q.get("confidence_score"),
                }
                normalized_edr_queries.append(normalized_q)
            else:
                normalized_edr_queries.append(q)

        items = normalized_edr_queries
        subresult_entry = {
            "items": items,
            "count": len(items),
            "queries": items,
            "raw": agent_result,
        }
    else:
        # Standard extraction agents
        if result_key in agent_result:
            items = agent_result[result_key]
        elif agent_name == "CmdlineExtract" and "cmdline_items" in agent_result:
            items = agent_result["cmdline_items"]
        elif "items" in agent_result:
            items = agent_result["items"]
        else:
            # Fallback: find first list
            for v in agent_result.values():
                if isinstance(v, list):
                    items = v
                    break

        subresult_entry = {"items": items, "count": len(items), "raw": agent_result}

    # Copy error fields uniformly
    if agent_result.get("error"):
        subresult_entry["error"] = agent_result["error"]
        if agent_result.get("error_details"):
            subresult_entry["error_details"] = agent_result["error_details"]
        if agent_result.get("error_type"):
            subresult_entry["error_type"] = agent_result["error_type"]

    return items, subresult_entry


async def _maybe_adjudicate_platform(
    content: str,
    agent_models: dict[str, Any],
    os_result: dict[str, Any],
    detected_os: Any,
    execution_id: int,
) -> tuple[dict[str, Any], Any]:
    """Phase B: LLM platform adjudication for the inconclusive (KB Unknown/low) tail.

    Invoked only when the deterministic KB gate could not classify the article. Uses
    the configured PlatformAdjudicator model (falling back to ExtractAgent/RankAgent).
    Returns possibly-updated (os_result, detected_os); never raises.
    See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (§6).
    """
    try:
        from src.services.llm_service import LLMService
        from src.services.platform_adjudicator import adjudicate_platforms

        models = agent_models or {}
        provider = (
            models.get("PlatformAdjudicator_provider")
            or models.get("ExtractAgent_provider")
            or models.get("RankAgent_provider")
            or "openai"
        )
        model_name = models.get("PlatformAdjudicator") or models.get("ExtractAgent") or models.get("RankAgent")
        llm_service = LLMService(config_models=models)

        async def _adj_call(messages: list[dict]) -> str:
            resp = await llm_service.request_chat(
                provider=provider,
                model_name=model_name,
                messages=messages,
                max_tokens=400,
                temperature=0.0,
                timeout=60.0,
                failure_context="platform_adjudication",
            )
            choices = resp.get("choices", []) if isinstance(resp, dict) else []
            return choices[0].get("message", {}).get("content", "") if choices else ""

        adj = await adjudicate_platforms(content, llm_call=_adj_call)
        if adj.platforms:
            logger.info(
                f"[Workflow {execution_id}] Platform adjudicated via LLM: "
                f"{adj.platforms} (confidence={adj.confidence})"
            )
            new_result = adj.as_os_result()
            return new_result, new_result.get("operating_system", detected_os)
    except Exception as e:
        logger.warning(f"[Workflow {execution_id}] Platform adjudication skipped: {e}")
    return os_result, detected_os


def create_agentic_workflow(db_session: Session) -> StateGraph:
    """
    Create LangGraph workflow for agentic processing.

    Workflow steps:
    0. Platform Detection - Detect operating system/platform context
    1. Junk Filter - Filter content using conservative junk filter
    2. LLM Ranking - Rank article using LLM
    3. Extract Agent - Extract behaviors using ExtractAgent
    4. Generate SIGMA - Generate SIGMA detection rules
    5. Similarity Search - Check similarity against existing rules
    6. Queue Promotion - Queue new rules for human review

    Args:
        db_session: Database session

    Returns:
        Compiled LangGraph workflow
    """

    # Initialize services
    content_filter = ContentFilter()
    trigger_service = WorkflowTriggerService(db_session)

    # Define workflow nodes

    async def os_detection_node(state: WorkflowState) -> WorkflowState:
        """Step 0: Detect operating system from article content."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 0: Platform Detection")

            article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            content = article.content if article else ""

            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                execution.current_step = "os_detection"
                db_session.commit()

            config = state.get("config")
            config_snapshot = execution.config_snapshot if execution else {}
            if isinstance(config_snapshot, str):
                try:
                    config_snapshot = json.loads(config_snapshot)
                except (json.JSONDecodeError, ValueError):
                    config_snapshot = {}
            if not isinstance(config_snapshot, dict):
                config_snapshot = {}

            skip_os_detection_flag = _bool_from_value(config_snapshot.get("skip_os_detection", False))
            eval_run_flag = _bool_from_value(config_snapshot.get("eval_run", False))
            skip_os_detection = skip_os_detection_flag or eval_run_flag

            if skip_os_detection:
                logger.info(f"[Workflow {state['execution_id']}] Skipping Platform Detection (eval run)")
                detected_os = "Windows"
                os_result = {
                    "operating_system": "Windows",
                    "method": "eval_skip",
                    "confidence": 1.0,
                    "similarities": {"Windows": 1.0},
                }
            else:
                from src.services.os_detection_service import OSDetectionService

                agent_models = (config.get("agent_models") or {}) if config and isinstance(config, dict) else {}
                embedding_model = agent_models.get("OSDetectionAgent_embedding", "ibm-research/CTI-BERT")

                service = OSDetectionService(model_name=embedding_model)
                os_result = await service.detect_os(
                    content=content,
                    use_classifier=True,
                )
                detected_os = os_result.get("operating_system", "Unknown") if os_result else "Unknown"

                # Phase B: deterministic gate inconclusive -> LLM adjudication on the
                # low-confidence / Unknown tail only (never on the eval-skip path above).
                # "low" is the canonical inconclusive signal from the KB gate (Unknown).
                if content and (os_result or {}).get("confidence") == "low":
                    os_result, detected_os = await _maybe_adjudicate_platform(
                        content, agent_models, os_result, detected_os, state["execution_id"]
                    )

            similarities = os_result.get("similarities", {}) if os_result else {}
            windows_similarity = similarities.get("Windows", 0.0) if isinstance(similarities, dict) else 0.0

            if detected_os == "Unknown" and similarities:
                max_similarity_os = max(similarities, key=similarities.get)
                if max_similarity_os == "Windows" and windows_similarity > 0.0:
                    detected_os = "Windows"
                    os_result["operating_system"] = "Windows"
                    logger.info(
                        f"[Workflow {state['execution_id']}] Overriding detected_os to 'Windows' (highest similarity: {windows_similarity:.1%})"
                    )

            platforms_detected = _platforms_from_os_detection(detected_os, os_result)

            termination_reason = state.get("termination_reason")
            termination_details = state.get("termination_details")

            if execution:
                execution.current_step = "os_detection"
                if execution.error_log is None:
                    execution.error_log = {}
                execution.error_log["os_detection_result"] = {
                    "detected_os": detected_os,
                    "platforms_detected": platforms_detected,
                    "detection_method": os_result.get("method"),
                    "confidence": os_result.get("confidence"),
                    "similarities": os_result.get("similarities"),
                    "max_similarity": os_result.get("max_similarity"),
                    "probabilities": os_result.get("probabilities"),
                }
                flag_modified(execution, "error_log")

                execution.status = "running"
                db_session.commit()

            logger.info(
                f"[Workflow {state['execution_id']}] Platform Detection: {detected_os}, "
                f"platforms={platforms_detected}, continue=True"
            )

            return {
                **state,
                "os_detection_result": os_result,
                "detected_os": detected_os,
                "platforms_detected": platforms_detected,
                "should_continue": True,
                "current_step": "os_detection",
                "status": "running",
                "termination_reason": termination_reason,
                "termination_details": termination_details,
            }

        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] OS detection error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                db_session.commit()

            return {
                **state,
                "error": str(e),
                "should_continue": False,
                "current_step": "os_detection",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    def junk_filter_node(state: WorkflowState) -> WorkflowState:
        """Step 1: Filter content using conservative junk filter."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 1: Junk Filter")

            # Load article from DB instead of state (state['article'] is None to avoid serialization issues)
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")

            # Validate article content
            if not article.content or len(article.content.strip()) == 0:
                raise ValueError(f"Article {article.id} has no content to filter")

            # Get junk filter threshold from config
            config = state.get("config")
            junk_filter_threshold = (
                config.get("junk_filter_threshold", 0.8) if config and isinstance(config, dict) else 0.8
            )

            # Use configured filter threshold
            try:
                filter_result = content_filter.filter_content(
                    article.content,
                    min_confidence=junk_filter_threshold,
                    hunt_score=article.article_metadata.get("threat_hunting_score", 0)
                    if article.article_metadata
                    else 0,
                    article_id=article.id,
                )
            except Exception as filter_error:
                logger.error(f"[Workflow {state['execution_id']}] ContentFilter error: {filter_error}", exc_info=True)
                raise ValueError(f"ContentFilter failed: {filter_error}") from filter_error

            # Update execution record
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                execution.current_step = "junk_filter"
                # Calculate chunks kept (total chunks - removed chunks)
                total_chunks = (len(article.content) // 1000) + 1  # Rough estimate
                chunks_removed = len(filter_result.removed_chunks) if filter_result.removed_chunks else 0
                chunks_kept = total_chunks - chunks_removed if chunks_removed > 0 else total_chunks

                execution.junk_filter_result = {
                    "filtered_length": len(filter_result.filtered_content) if filter_result.filtered_content else 0,
                    "original_length": len(article.content),
                    "chunks_kept": chunks_kept,
                    "chunks_removed": chunks_removed,
                    "is_huntable": filter_result.is_huntable,
                    "confidence": filter_result.confidence,
                }
                db_session.commit()

            # Terminate early when no chunks survived the filter
            if not filter_result.is_huntable:
                logger.info(
                    f"[Workflow {state['execution_id']}] Junk filter: no huntable content "
                    f"(confidence={filter_result.confidence:.2f}, threshold={junk_filter_threshold}). Terminating."
                )
                termination_details = {
                    "confidence": filter_result.confidence,
                    "threshold": junk_filter_threshold,
                    "original_length": len(article.content),
                }
                if execution:
                    mark_execution_completed(
                        execution,
                        step="junk_filter",
                        db_session=db_session,
                        reason=TERMINATION_REASON_JUNK_FILTER,
                        details=termination_details,
                        commit=True,
                    )
                return {
                    **state,
                    "filtered_content": "",
                    "junk_filter_result": execution.junk_filter_result if execution else None,
                    "current_step": "junk_filter",
                    "status": "completed",
                    "termination_reason": TERMINATION_REASON_JUNK_FILTER,
                    "termination_details": termination_details,
                }

            return {
                **state,
                "filtered_content": filter_result.filtered_content,
                "junk_filter_result": execution.junk_filter_result if execution else None,
                "current_step": "junk_filter",
                "status": state.get("status", "running"),
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Junk filter error: {e}", exc_info=True)
            # Update execution with error
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.current_step = "junk_filter"
                db_session.commit()
            return {
                **state,
                "error": str(e),
                "current_step": "junk_filter",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    def rank_agent_bypass_node(state: WorkflowState) -> WorkflowState:
        """Bypass node when rank agent disabled/skipped for evals; sets should_continue=True."""
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
            .first()
        )

        # Determine bypass reason
        config_snapshot = execution.config_snapshot if execution else {}
        eval_run_flag = _bool_from_value(config_snapshot.get("eval_run", False))
        state_eval_run = _bool_from_value(state.get("eval_run", False))
        is_eval_run = state_eval_run or eval_run_flag
        bypass_reason = "Rank Agent skipped for eval run" if is_eval_run else "Rank Agent disabled - bypassed"

        logger.info(f"[Workflow {state['execution_id']}] {bypass_reason}")

        # Update execution record
        if execution:
            execution.current_step = "rank_article_bypassed"
            execution.ranking_score = None
            execution.ranking_reasoning = bypass_reason
            db_session.commit()

        return {
            **state,
            "ranking_score": None,
            "ranking_reasoning": bypass_reason,
            "should_continue": True,
            "current_step": "rank_article_bypassed",
            "status": state.get("status", "running"),
            "termination_reason": state.get("termination_reason"),
            "termination_details": state.get("termination_details"),
        }

    async def rank_article_node(state: WorkflowState) -> WorkflowState:
        """Step 2: Rank article using LLM."""
        try:
            # CRITICAL: Check if this is an eval run - evals MUST NOT use rank agent
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            state_eval_run = _bool_from_value(state.get("eval_run", False))
            state_skip_rank = _bool_from_value(state.get("skip_rank_agent", False))
            if state_eval_run or state_skip_rank:
                logger.warning(f"[Workflow {state['execution_id']}] BLOCKED: Rank agent node for eval run - bypass")
                if execution:
                    execution.current_step = "rank_article_bypassed"
                    execution.ranking_score = None
                    execution.ranking_reasoning = "Rank Agent blocked for eval run"
                    db_session.commit()

                return {
                    **state,
                    "ranking_score": None,
                    "ranking_reasoning": "Rank Agent blocked for eval run",
                    "should_continue": True,
                    "current_step": "rank_article_bypassed",
                    "status": state.get("status", "running"),
                }

            if execution and execution.config_snapshot:
                config_snapshot = execution.config_snapshot or {}
                skip_rank_agent = _bool_from_value(config_snapshot.get("skip_rank_agent", False)) or _bool_from_value(
                    config_snapshot.get("eval_run", False)
                )

                if skip_rank_agent:
                    logger.warning(f"[Workflow {state['execution_id']}] BLOCKED: Rank agent node for eval run - bypass")
                    # Redirect to bypass node behavior
                    if execution:
                        execution.current_step = "rank_article_bypassed"
                        execution.ranking_score = None
                        execution.ranking_reasoning = "Rank Agent blocked for eval run"
                        db_session.commit()

                    return {
                        **state,
                        "ranking_score": None,
                        "ranking_reasoning": "Rank Agent blocked for eval run",
                        "should_continue": True,
                        "current_step": "rank_article_bypassed",
                        "status": state.get("status", "running"),
                    }

            logger.info(f"[Workflow {state['execution_id']}] Step 2: LLM Ranking")

            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get("filtered_content") or article.content if article else ""

            # Update execution record BEFORE calling LLM (so status is accurate during long-running LLM call)
            if execution:
                execution.current_step = "rank_article"
                db_session.commit()

            # Get config models for LLMService
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None
            llm_service = LLMService(config_models=agent_models)
            llm_service._current_execution_id = state["execution_id"]
            llm_service._current_article_id = article.id

            ranking_result = None

            # Get source name
            source_name = article.source.name if article.source else "Unknown"

            hunt_score = article.article_metadata.get("threat_hunting_score") if article.article_metadata else None
            ml_score = article.article_metadata.get("ml_hunt_score") if article.article_metadata else None
            ground_truth_details = LLMService.compute_rank_ground_truth(hunt_score, ml_score)
            ground_truth_rank = ground_truth_details.get("ground_truth_rank")

            # Get agent prompt from config (for both ranking and QA)
            rank_prompt_template = None
            rank_system_prompt = None
            agent_prompt = (
                "You are a cybersecurity detection engineer. "
                "Score threat intelligence articles 1-10 for SIGMA huntability. "
                "Output only a score and brief reasoning."
            )
            if config_obj and config_obj.agent_prompts and "RankAgent" in config_obj.agent_prompts:
                from src.utils.prompt_loader import parse_rank_agent_prompt_data

                rank_prompt_template, rank_system_prompt = parse_rank_agent_prompt_data(
                    config_obj.agent_prompts["RankAgent"]
                )
                if rank_prompt_template or rank_system_prompt:
                    agent_prompt = (rank_system_prompt or rank_prompt_template or "")[:5000]
                    logger.info(
                        f"Using RankAgent prompt from workflow config "
                        f"(template_len={len(rank_prompt_template or '')} chars, "
                        f"system_len={len(rank_system_prompt or '')} chars)"
                    )

            # Materialize article fields, then release the DB connection before the long
            # LLM call so it doesn't sit 'idle in transaction' for the call duration.
            rank_title = article.title
            rank_url = article.canonical_url or ""
            rank_article_id = article.id
            db_session.commit()

            # Rank article using LLM
            ranking_result = await llm_service.rank_article(
                title=rank_title,
                content=filtered_content,
                source=source_name,
                url=rank_url,
                prompt_template=rank_prompt_template,
                system_override=rank_system_prompt,
                execution_id=state["execution_id"],
                article_id=rank_article_id,
                ground_truth_rank=ground_truth_rank,
                ground_truth_details=ground_truth_details,
            )

            # Store LLM interaction in conversation log
            conversation_log = [
                {
                    "attempt": 1,
                    "messages": [
                        {
                            "role": "system",
                            "content": agent_prompt,
                        },
                        {
                            "role": "user",
                            "content": f"Title: {article.title}\nSource: {source_name}\nURL: {article.canonical_url or ''}\n\nContent: {filtered_content[:2000]}..."
                            if len(filtered_content) > 2000
                            else f"Title: {article.title}\nSource: {source_name}\nURL: {article.canonical_url or ''}\n\nContent: {filtered_content}",
                        },
                    ],
                    "llm_response": ranking_result.get("raw_response", ranking_result.get("reasoning", "")),
                    "score": ranking_result.get("score"),
                }
            ]

            # Store conversation log in execution.error_log
            if execution:
                if execution.error_log is None:
                    execution.error_log = {}
                execution.error_log["rank_article"] = {"conversation_log": conversation_log}
                db_session.commit()

            ranking_score = ranking_result["score"] if ranking_result else 0.0
            config = state.get("config")
            ranking_threshold = config.get("ranking_threshold", 6.0) if config and isinstance(config, dict) else 6.0
            should_continue = ranking_score >= ranking_threshold

            termination_reason = state.get("termination_reason")
            termination_details = state.get("termination_details")

            # Update execution record with ranking results
            if execution:
                execution.ranking_score = ranking_score
                execution.ranking_reasoning = ranking_result.get("reasoning", "")  # Store full reasoning
                execution.current_step = "rank_article"
                if should_continue:
                    execution.status = "running"
                    db_session.commit()
                else:
                    termination_details = {"ranking_score": ranking_score, "ranking_threshold": ranking_threshold}
                    mark_execution_completed(
                        execution,
                        "rank_article",
                        db_session=db_session,
                        reason=TERMINATION_REASON_RANK_THRESHOLD,
                        details=termination_details,
                        commit=False,
                    )
                    db_session.commit()
                    termination_reason = TERMINATION_REASON_RANK_THRESHOLD

            logger.info(
                f"[Workflow {state['execution_id']}] Ranking: {ranking_score}/10 (threshold: {ranking_threshold}), continue: {should_continue}"
            )

            return {
                **state,
                "ranking_score": ranking_score,
                "ranking_reasoning": ranking_result.get("reasoning"),
                "should_continue": should_continue,
                "current_step": "rank_article",
                "status": "completed" if not should_continue else "running",
                "termination_reason": termination_reason,
                "termination_details": termination_details,
            }

        except Exception as e:
            error_msg = str(e).lower()
            error_repr = repr(e).lower()
            # Check if this is a generator error from Langfuse cleanup (non-critical)
            # Check both str() and repr() to catch all variations
            is_generator_error = (
                "generator" in error_msg
                and ("didn't stop" in error_msg or "didn't stop" in error_repr or "throw" in error_msg)
            ) or ("generator" in error_repr and ("didn't stop" in error_repr or "throw" in error_repr))

            if is_generator_error:
                logger.warning(
                    f"[Workflow {state['execution_id']}] Generator error during ranking (Langfuse cleanup issue, non-critical): {e}"
                )
                # Don't mark as failed for generator errors - they're tracing issues, not workflow failures
                # Return state indicating workflow should stop due to ranking failure, but don't set error
                return {
                    **state,
                    "error": None,  # Don't propagate generator errors as workflow errors
                    "should_continue": False,
                    "current_step": "rank_article",
                    "status": "completed",  # Mark as completed, not failed
                    "termination_reason": TERMINATION_REASON_RANK_THRESHOLD,
                    "termination_details": {"reason": "Generator error during ranking (non-critical)"},
                }

            logger.error(f"[Workflow {state['execution_id']}] Ranking error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                db_session.commit()

            return {
                **state,
                "error": str(e),
                "should_continue": False,
                "current_step": "rank_article",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    async def extract_agent_node(state: WorkflowState) -> WorkflowState:
        """Step 3: Extract behaviors using ExtractAgent."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Extract Agent")

            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get("filtered_content") or article.content if article else ""
            # Materialize article fields into plain locals while the read transaction is
            # legitimately open. The per-subagent LLM calls below then use these locals
            # instead of touching the ORM object -- otherwise accessing article.title after
            # a commit (expire_on_commit=True) lazily re-SELECTs and reopens a transaction
            # that sits 'idle in transaction' holding a pooled connection for the entire
            # multi-second extraction. See also create_tables() lock_timeout note.
            article_title = article.title if article else ""
            article_url = (article.canonical_url or "") if article else ""

            # Update execution record BEFORE calling LLM
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                execution.current_step = "extract_agent"
                db_session.commit()

            # Extract behaviors using sequential sub-agents and Supervisor
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Extract Agent (Supervisor Mode with Sub-Agents)")
            article_platforms = state.get("platforms_detected")
            if not isinstance(article_platforms, list) or not article_platforms:
                article_platforms = _platforms_from_os_detection(state.get("detected_os"), state.get("os_detection_result"))
            article_platforms = [_normalize_platform_value(platform) for platform in article_platforms]

            config_obj = trigger_service.get_active_config()
            if not config_obj:
                raise ValueError("No active workflow configuration found")

            # Check if this is a subagent eval run
            config_snapshot = execution.config_snapshot if execution else {}
            state_config = state.get("config", {})
            subagent_eval = normalize_subagent_name(
                config_snapshot.get("subagent_eval") or state_config.get("subagent_eval")
            )
            if subagent_eval:
                subagent_to_agent = {
                    "cmdline": "CmdlineExtract",
                    "process_lineage": "ProcTreeExtract",
                    "hunt_queries": "HuntQueriesExtract",
                    "registry_artifacts": "RegistryExtract",
                    "windows_services": "ServicesExtract",
                    "scheduled_tasks": "ScheduledTasksExtract",
                    "network_indicators": "NetworkIndicatorExtract",
                }
                if subagent_eval not in subagent_to_agent:
                    logger.warning(
                        f"[Workflow {state['execution_id']}] Unknown subagent_eval value: {subagent_eval}. "
                        f"Available: {list(subagent_to_agent.keys())}"
                    )

            # Initialize sub-results accumulator
            subresults = {
                "cmdline": {"items": [], "count": 0},
                "process_lineage": {"items": [], "count": 0},
                "hunt_queries": {"items": [], "count": 0},
                "registry_artifacts": {"items": [], "count": 0},
                "windows_services": {"items": [], "count": 0},
                "scheduled_tasks": {"items": [], "count": 0},
                "network_indicators": {"items": [], "count": 0},
            }

            # Get config models for LLMService
            # For eval runs, exclude SigmaAgent to avoid loading the SIGMA model unnecessarily
            # For subagent evals, only include models for the agent being evaluated
            agent_models = config_obj.agent_models if config_obj else None
            max_extraction_retries = 5
            if agent_models:
                # Check if this is an eval run (check both config_snapshot and state config)
                config_snapshot = execution.config_snapshot if execution else {}
                state_config = state.get("config", {})
                is_eval_run = (
                    _bool_from_value(config_snapshot.get("eval_run", False))
                    or _bool_from_value(config_snapshot.get("skip_sigma_generation", False))
                    or _bool_from_value(state_config.get("eval_run", False))
                    or _bool_from_value(state_config.get("skip_sigma_generation", False))
                )
                # subagent_eval was already set and normalized above, don't overwrite it
                # subagent_eval = config_snapshot.get('subagent_eval') or state_config.get('subagent_eval')

                if is_eval_run:
                    # Remove SigmaAgent from models to prevent loading it
                    original_count = len(agent_models)
                    agent_models = {k: v for k, v in agent_models.items() if not k.startswith("SigmaAgent")}
                    filtered_count = len(agent_models)
                    logger.info(
                        f"[Workflow {state['execution_id']}] Eval run: Excluding SigmaAgent models from LLMService initialization "
                        f"(filtered {original_count} -> {filtered_count} models). "
                        f"Remaining models: {list(agent_models.keys())}"
                    )

                # For subagent evals, filter to only include models for the agent being evaluated
                # subagent_eval was already normalized above (line 818), ensure it's still normalized
                if subagent_eval:
                    # Ensure it's still normalized (defensive check)
                    subagent_eval = str(subagent_eval).lower().strip() if subagent_eval else None
                if subagent_eval:
                    agent_name = subagent_to_agent.get(subagent_eval)
                    if agent_name:
                        # Keep only models for this agent plus ExtractAgent (fallback) and RankAgent
                        prefixes_to_keep = [
                            f"{agent_name}_",  # Agent model, temperature, provider
                            "ExtractAgent",  # Fallback model
                            "RankAgent",  # May be needed for initialization
                        ]
                        original_count = len(agent_models)
                        agent_models = {
                            k: v
                            for k, v in agent_models.items()
                            if any(k.startswith(prefix) or k == prefix for prefix in prefixes_to_keep)
                        }
                        filtered_count = len(agent_models)
                        logger.info(
                            f"[Workflow {state['execution_id']}] Subagent eval ({subagent_eval}): Filtering models to only {agent_name} "
                            f"(filtered {original_count} -> {filtered_count} models). "
                            f"Remaining models: {list(agent_models.keys())}"
                        )
            llm_service = LLMService(config_models=agent_models)

            # --- Sub-Agents (including CmdlineExtract) ---
            sub_agents = [
                ("CmdlineExtract", "cmdline"),
                ("ProcTreeExtract", "process_lineage"),
                ("HuntQueriesExtract", "hunt_queries"),
                ("RegistryExtract", "registry_artifacts"),
                ("ServicesExtract", "windows_services"),
                ("ScheduledTasksExtract", "scheduled_tasks"),
                ("NetworkIndicatorExtract", "network_indicators"),
            ]

            # Initialize conversation log for extract_agent
            conversation_log = []
            sub_agents_run = []
            disabled_sub_agents = []
            capability_skip_records = []

            # Determine disabled sub-agents (supports list or map in config)
            disabled_agents_cfg = set()
            extract_settings = {}

            # Try to get disabled agents from config_obj.agent_prompts
            if config_obj:
                logger.info(
                    f"[Workflow {state['execution_id']}] config_obj found. agent_prompts type: {type(config_obj.agent_prompts)}, is None: {config_obj.agent_prompts is None}"
                )
                if config_obj.agent_prompts is not None:
                    logger.info(
                        f"[Workflow {state['execution_id']}] agent_prompts keys: {list(config_obj.agent_prompts.keys()) if isinstance(config_obj.agent_prompts, dict) else 'not a dict'}"
                    )
                if config_obj.agent_prompts and isinstance(config_obj.agent_prompts, dict):
                    extract_settings = (
                        config_obj.agent_prompts.get("ExtractAgentSettings")
                        or config_obj.agent_prompts.get("ExtractAgent")
                        or {}
                    )
                    logger.info(
                        f"[Workflow {state['execution_id']}] Found extract_settings from agent_prompts: {extract_settings}"
                    )
                else:
                    logger.warning(
                        f"[Workflow {state['execution_id']}] agent_prompts not available or not a dict. agent_prompts type: {type(config_obj.agent_prompts)}, value: {config_obj.agent_prompts}"
                    )
            else:
                logger.warning(f"[Workflow {state['execution_id']}] config_obj is None - cannot read disabled agents")

            # Fallback to state config if extract_settings is still empty
            state_config = state.get("config", {}) if isinstance(state.get("config", {}), dict) else {}
            if not extract_settings and isinstance(state_config.get("extract_agents_disabled"), (list, dict)):
                extract_settings = {"disabled_agents": state_config.get("extract_agents_disabled")}
                logger.debug(
                    f"[Workflow {state['execution_id']}] Found extract_settings from state config: {extract_settings}"
                )

            disabled_agents_value = (
                extract_settings.get("disabled_agents") or extract_settings.get("disabled_sub_agents") or []
            )

            # Filter out deleted subagents (SigExtract, RegExtract, EventCodeExtract)
            # Valid subagents: CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract, NetworkIndicatorExtract
            deleted_agents = {"SigExtract", "RegExtract", "EventCodeExtract"}

            logger.info(
                f"[Workflow {state['execution_id']}] disabled_agents_value: {disabled_agents_value} (type: {type(disabled_agents_value)})"
            )

            if isinstance(disabled_agents_value, dict):
                # Filter out deleted agents from dict
                filtered_dict = {
                    name: enabled for name, enabled in disabled_agents_value.items() if name not in deleted_agents
                }
                disabled_agents_cfg = {
                    name
                    for name, enabled in filtered_dict.items()
                    if enabled is False or (isinstance(enabled, str) and enabled.lower() == "false")
                }
            elif isinstance(disabled_agents_value, list):
                # Filter out deleted agents from list
                filtered_list = [name for name in disabled_agents_value if name not in deleted_agents]
                disabled_agents_cfg = set(filtered_list)

                # Log if deleted agents were found and filtered
                found_deleted = [name for name in disabled_agents_value if name in deleted_agents]
                if found_deleted:
                    logger.warning(
                        f"[Workflow {state['execution_id']}] Filtered out deleted subagents from disabled_agents: {found_deleted}"
                    )

            logger.info(f"[Workflow {state['execution_id']}] Final disabled_agents_cfg: {disabled_agents_cfg}")

            # Check if this is a subagent eval run - if so, only run the specified agent
            # Re-read subagent_eval directly from execution to ensure we have the correct value
            # (config_snapshot was redefined at line 858, so we need to read from execution again)
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 DEBUG: About to check subagent_eval. execution is None: {execution is None}, "
                f"config_snapshot keys: {list(config_snapshot.keys()) if config_snapshot else 'None'}"
            )

            if execution:
                config_snapshot_for_filter = execution.config_snapshot if execution.config_snapshot else {}
                logger.info(
                    f"[Workflow {state['execution_id']}] 🔍 DEBUG: execution.config_snapshot keys: {list(config_snapshot_for_filter.keys()) if config_snapshot_for_filter else 'None'}"
                )
            else:
                config_snapshot_for_filter = config_snapshot
                logger.warning(
                    f"[Workflow {state['execution_id']}] ⚠️ execution is None, using config_snapshot from state"
                )
            state_config_for_filter = state.get("config", {})
            raw_subagent_eval = config_snapshot_for_filter.get("subagent_eval") or state_config_for_filter.get(
                "subagent_eval"
            )
            subagent_eval_for_filter, eval_lookup_values = build_subagent_lookup_values(raw_subagent_eval)
            subagent_eval = subagent_eval_for_filter
            eval_lookup_values = {
                str(value).strip().lower()
                for value in (eval_lookup_values or set())
                if value is not None and str(value).strip()
            }
            if subagent_eval and subagent_eval not in eval_lookup_values:
                eval_lookup_values.add(subagent_eval)

            # Log for debugging
            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 Filtering check - subagent_eval from execution: '{raw_subagent_eval}' "
                f"(normalized: '{subagent_eval}'), lookup_values={sorted(eval_lookup_values)}, "
                f"type={type(raw_subagent_eval)}, execution is None: {execution is None}"
            )

            if eval_lookup_values:
                # Filter sub_agents to only include the agent being evaluated
                # subagent_eval is the subagent name (e.g., "process_lineage"), so compare with alias and agent name
                original_sub_agents = sub_agents

                # Debug: log what we're comparing
                logger.info(
                    f"[Workflow {state['execution_id']}] 🔍 BEFORE FILTERING - subagent_eval='{subagent_eval}' "
                    f"(lookup_values={sorted(eval_lookup_values)}), sub_agents list: "
                    f"{[(name, subagent, f'match={subagent.lower() in eval_lookup_values or name.lower() in eval_lookup_values}') for name, subagent in original_sub_agents]}"
                )

                # Filter with explicit comparison logging
                filtered_agents = []
                for agent in sub_agents:
                    agent_subagent = agent[1].lower() if len(agent) > 1 else ""
                    agent_name = agent[0].lower() if len(agent) > 0 else ""
                    matches = agent_subagent in eval_lookup_values or agent_name in eval_lookup_values
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔍 Comparing: agent[0]='{agent[0]}' -> lower()='{agent_name}', "
                        f"agent[1]='{agent[1]}' -> lower()='{agent_subagent}' vs lookup_values={sorted(eval_lookup_values)} -> {matches}"
                    )
                    if matches:
                        filtered_agents.append(agent)

                sub_agents = filtered_agents

                logger.info(
                    f"[Workflow {state['execution_id']}] AFTER FILTERING - looking for subagent='{subagent_eval}'. "
                    f"Original count: {len(original_sub_agents)}, Filtered count: {len(sub_agents)}. "
                    f"Original agents: {[(name, subagent) for name, subagent in original_sub_agents]}. "
                    f"Filtered agents: {[(name, subagent) for name, subagent in sub_agents]}"
                )

                # CRITICAL: Verify filtering worked
                if len(sub_agents) != 1:
                    logger.error(
                        f"[Workflow {state['execution_id']}] 🚫 CRITICAL FILTERING ERROR: Expected 1 agent, got {len(sub_agents)}. "
                        f"Filtered agents: {[(name, subagent) for name, subagent in sub_agents]}. "
                        f"This will cause incorrect agent execution!"
                    )

                if not sub_agents:
                    logger.error(
                        f"[Workflow {state['execution_id']}] ⚠️ subagent_eval='{subagent_eval}' not found in sub_agents list. "
                        f"Available subagents: {[subagent for _, subagent in original_sub_agents]}. "
                        f"CRITICAL: This should not happen - filtering failed!"
                    )
                    # DO NOT reset to original - this is a critical error
                    # Instead, keep the empty list so no agents run
                    logger.error(
                        f"[Workflow {state['execution_id']}] 🚫 CRITICAL: Filtering failed, keeping empty sub_agents list to prevent all agents from running"
                    )
                else:
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🔬 Eval mode: Only running {subagent_eval}. "
                        f"Filtered sub_agents: {[name for name, _ in sub_agents]}. "
                        f"Other agents will be skipped."
                    )
                    # Mark all non-evaluated agents as skipped
                    evaluated_agent_names = {agent[0] for agent in sub_agents}
                    for agent_name, result_key in original_sub_agents:
                        if agent_name not in evaluated_agent_names and agent_name not in disabled_agents_cfg:
                            subresults[result_key] = {"items": [], "count": 0, "raw": {"status": "skipped_for_eval"}}
                            conversation_log.append(
                                {"agent": agent_name, "items_count": 0, "result": {"status": "skipped_for_eval"}}
                            )
                            logger.info(
                                f"[Workflow {state['execution_id']}] ⏭️ {agent_name} skipped (eval mode: only {subagent_eval} running)"
                            )

            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 FINAL CHECK - Sub-agents to process: {[name for name, _ in sub_agents]}, "
                f"subagent_eval='{subagent_eval}', count={len(sub_agents)}"
            )

            # Final safety check: if subagent_eval is set, ensure we only process the evaluated agent
            if subagent_eval:
                evaluated_subagent_names = {agent[1] for agent in sub_agents}
                if subagent_eval not in evaluated_subagent_names:
                    logger.error(
                        f"[Workflow {state['execution_id']}] CRITICAL: subagent_eval={subagent_eval} not in filtered sub_agents! "
                        f"Filtered agents: {evaluated_subagent_names}. This should not happen."
                    )

            logger.info(
                f"[Workflow {state['execution_id']}] 🔍 ABOUT TO LOOP - sub_agents count: {len(sub_agents)}, "
                f"agents: {[(name, subagent) for name, subagent in sub_agents]}, subagent_eval='{subagent_eval}'"
            )

            for agent_name, result_key in sub_agents:
                if not _agent_supported_for_platforms(agent_name, article_platforms):
                    telemetry_category = OBSERVABLE_TELEMETRY_CATEGORY.get(result_key, result_key)
                    reason = (
                        f"{agent_name} supports {', '.join(sorted(AGENT_PLATFORM_CAPABILITIES.get(agent_name, set())))} "
                        f"only; detected platforms: {', '.join(article_platforms)}."
                    )
                    skip_record = _make_skip_record(
                        agent_name=agent_name,
                        reason_code="unsupported_platform",
                        reason=reason,
                        detected_platforms=article_platforms,
                        telemetry_categories=[telemetry_category],
                    )
                    subresults[result_key] = {"items": [], "count": 0, "raw": skip_record}
                    capability_skip_records.append(skip_record)
                    conversation_log.append({"agent": agent_name, "items_count": 0, "result": skip_record})
                    logger.info(f"[Workflow {state['execution_id']}] {reason}")
                    continue

                # Consolidated eval-blocking check (replaces three formerly-separate inline checks)
                if not _is_agent_allowed(
                    agent_name, execution, subagent_eval, eval_lookup_values, state["execution_id"]
                ):
                    subresults[result_key] = {"items": [], "count": 0, "raw": {"status": "blocked_by_eval_filter"}}
                    conversation_log.append(
                        {"agent": agent_name, "items_count": 0, "result": {"status": "blocked_by_eval_filter"}}
                    )
                    continue

                try:
                    if agent_name in disabled_agents_cfg:
                        logger.info(
                            f"[Workflow {state['execution_id']}] ⚠️ {agent_name} is DISABLED via config; SKIPPING execution"
                        )
                        subresults[result_key] = {"items": [], "count": 0, "raw": {"status": "disabled"}}
                        conversation_log.append(
                            {"agent": agent_name, "items_count": 0, "result": {"status": "disabled"}}
                        )
                        disabled_sub_agents.append(agent_name)
                        continue

                    sub_agents_run.append(agent_name)

                    # Load Prompts from config only (no file fallback)
                    prompt_config = None

                    # Get prompt from config
                    if not config_obj or not config_obj.agent_prompts or agent_name not in config_obj.agent_prompts:
                        logger.error(f"{agent_name} prompt not found in workflow config, skipping")
                        continue

                    agent_prompt_data = config_obj.agent_prompts[agent_name]
                    if not isinstance(agent_prompt_data.get("prompt"), str):
                        logger.error(f"{agent_name} prompt in config is not a string, skipping")
                        continue

                    try:
                        prompt_config = json.loads(agent_prompt_data["prompt"])
                        logger.info(
                            f"Using {agent_name} prompt from workflow config (length: {len(agent_prompt_data['prompt'])} chars)"
                        )
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse {agent_name} prompt from config as JSON: {e}, skipping")
                        continue

                    # Get model and provider for this agent
                    model_key = f"{agent_name}_model"
                    provider_key = f"{agent_name}_provider"
                    agent_model = agent_models.get(model_key) if agent_models else None
                    if not agent_model:
                        agent_model = agent_models.get("ExtractAgent") if agent_models else None
                    # Get provider for this agent, fallback to ExtractAgent provider
                    agent_provider = agent_models.get(provider_key) if agent_models else None
                    if not agent_provider or (isinstance(agent_provider, str) and not agent_provider.strip()):
                        agent_provider = agent_models.get("ExtractAgent_provider") if agent_models else None
                    # Normalize empty strings to None (will use fallback in llm_service)
                    if agent_provider and isinstance(agent_provider, str) and not agent_provider.strip():
                        agent_provider = None
                    # Log provider resolution for debugging
                    logger.info(
                        f"[Workflow {state['execution_id']}] Provider resolution for {agent_name}: "
                        f"provider_key={provider_key}, agent_provider={agent_provider}, "
                        f"agent_models keys={list(agent_models.keys()) if agent_models else []}, "
                        f"agent_models values={list(agent_models.values())[:10] if agent_models else []}"
                    )
                    # Safety check: Warn if provider is None when we have agent_models
                    if agent_provider is None and agent_models:
                        logger.warning(
                            f"[Workflow {state['execution_id']}] ⚠️ {agent_name} provider is None but agent_models exists. "
                            f"provider_key={provider_key} not found in config. Will fallback to ExtractAgent provider."
                        )
                    # Run Agent
                    logger.info(
                        f"[Workflow {state['execution_id']}] 🚀 About to call LLM for {agent_name} (provider={agent_provider}, model={agent_model})"
                    )
                    # Release the DB connection before the long LLM call so it doesn't sit
                    # 'idle in transaction' (blocking pool slots / DDL) for the call duration.
                    # Args use materialized locals (article_title/article_url) so building the
                    # call below cannot lazily reopen a transaction.
                    db_session.commit()
                    agent_result = await llm_service.run_extraction_agent(
                        agent_name=agent_name,
                        content=filtered_content,
                        title=article_title,
                        url=article_url,
                        prompt_config=prompt_config,
                        max_extraction_retries=max_extraction_retries,
                        execution_id=state["execution_id"],
                        article_id=state["article_id"],
                        model_name=agent_model,
                        temperature=0.0,
                        provider=agent_provider,
                        attention_preprocessor_enabled=state.get("config", {}).get(
                            "cmdline_attention_preprocessor_enabled", True
                        ),
                        proc_tree_attention_preprocessor_enabled=state.get("config", {}).get(
                            "proc_tree_attention_preprocessor_enabled", True
                        ),
                    )

                    # Store Result
                    items, subresult_entry = _parse_agent_result(agent_name, result_key, agent_result)
                    subresults[result_key] = subresult_entry
                    logger.info(f"[Workflow {state['execution_id']}] {agent_name}: {len(items)} items")

                    # Make cmdline items available on state for downstream consumers (e.g., SIGMA)
                    if agent_name == "CmdlineExtract":
                        state["cmdline_items"] = items
                        state["count"] = len(items)

                    # Store agent result in conversation log.
                    # _llm_messages / _llm_response are kept in result for eval-bundle fallback
                    # but are also promoted to top-level as *truncated* copies for the live-view
                    # SSE stream.  Storing the full article content in both places per agent
                    # causes the conversation_log JSONB to grow too large, which prevents the
                    # last agents' message data from being transferred correctly.
                    _MAX_MSG_CHARS = 3000
                    _MAX_RESP_CHARS = 20000
                    log_entry: dict = {"agent": agent_name, "items_count": len(items), "result": agent_result}
                    if isinstance(agent_result, dict):
                        if "_llm_messages" in agent_result:
                            truncated_msgs = []
                            for _m in agent_result["_llm_messages"]:
                                if isinstance(_m, dict):
                                    _c = _m.get("content", "")
                                    truncated_msgs.append(
                                        {**_m, "content": _c[:_MAX_MSG_CHARS] + "…"} if len(_c) > _MAX_MSG_CHARS else _m
                                    )
                                else:
                                    truncated_msgs.append(_m)
                            log_entry["messages"] = truncated_msgs
                        if "_llm_response" in agent_result:
                            _r = agent_result["_llm_response"]
                            log_entry["llm_response"] = _r[:_MAX_RESP_CHARS] + "…" if len(_r) > _MAX_RESP_CHARS else _r
                        if "_llm_attempt" in agent_result:
                            log_entry["attempt"] = agent_result["_llm_attempt"]
                        if "_attention_preprocessor" in agent_result:
                            log_entry["attention_preprocessor"] = agent_result["_attention_preprocessor"]
                    conversation_log.append(log_entry)

                    # Incremental commit: persist conversation_log after each agent so the
                    # live-view SSE stream shows agents one-by-one instead of all at once.
                    if execution:
                        if execution.error_log is None or not isinstance(execution.error_log, dict):
                            execution.error_log = {}
                        execution.error_log["extract_agent"] = {"conversation_log": conversation_log}
                        flag_modified(execution, "error_log")
                        db_session.commit()
                        logger.debug(
                            f"[Workflow {state['execution_id']}] Incremental commit after {agent_name} "
                            f"({len(conversation_log)} conversation_log entries)"
                        )

                except Exception as e:
                    from src.services.llm_service import ContextLengthExceededError, PreprocessInvariantError

                    if isinstance(e, ContextLengthExceededError):
                        logger.error(
                            f"[Workflow {state['execution_id']}] {agent_name} context length exceeded -- "
                            f"extraction silently dropped. Reduce article size or switch to a larger context model. "
                            f"Error: {e}"
                        )
                        subresults[result_key] = {
                            "items": [],
                            "count": 0,
                            "raw": {"context_length_exceeded": True},
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "error_details": {
                                "message": str(e),
                                "exception_type": type(e).__name__,
                                "agent_name": agent_name,
                            },
                        }
                    elif isinstance(e, PreprocessInvariantError):
                        logger.error(
                            f"[Workflow {state['execution_id']}] {agent_name} preprocess invariant failed: {e}. "
                            f"Debug artifacts: {getattr(e, 'debug_artifacts', {})}"
                        )
                        subresults[result_key] = {
                            "items": [],
                            "count": 0,
                            "raw": {"infra_failed": True, "infra_debug_artifacts": getattr(e, "debug_artifacts", {})},
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "error_details": {
                                "message": str(e),
                                "exception_type": type(e).__name__,
                                "agent_name": agent_name,
                            },
                        }
                    else:
                        logger.error(f"[Workflow {state['execution_id']}] {agent_name} failed: {e}")
                        subresults[result_key] = {
                            "items": [],
                            "count": 0,
                            "raw": {},
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "error_details": {
                                "message": str(e),
                                "exception_type": type(e).__name__,
                                "agent_name": agent_name,
                            },
                        }

            # --- Supervisor Aggregation ---
            # Merge all items into a single 'observables' list for backward compatibility
            all_observables = []
            content_summary = []  # Accumulate text summary for content field
            extraction_timestamp = datetime.now().isoformat()
            config = state.get("config") or {}
            agent_models = config.get("agent_models") or {}
            cat_to_agent = {
                "cmdline": "CmdlineExtract",
                "process_lineage": "ProcTreeExtract",
                "hunt_queries": "HuntQueriesExtract",
                "registry_artifacts": "RegistryExtract",
                "windows_services": "ServicesExtract",
                "scheduled_tasks": "ScheduledTasksExtract",
                "network_indicators": "NetworkIndicatorExtract",
            }
            cat_to_subagent_name = {
                "cmdline": "Command-line Extractor",
                "process_lineage": "Process Tree Extractor",
                "hunt_queries": "Hunt Queries Extractor",
                "registry_artifacts": "Registry Extractor",
                "windows_services": "Windows Services Extractor",
                "scheduled_tasks": "Scheduled Tasks Extractor",
                "network_indicators": "Network Indicators Extractor",
            }

            # Enrich subresults items with traceability system fields (observable traceability feature)
            for cat, data in subresults.items():
                items = data.get("items", [])
                if not isinstance(items, list):
                    continue
                agent_name = cat_to_agent.get(cat)
                model_version = None
                if agent_name:
                    model_version = agent_models.get(f"{agent_name}_model") or agent_models.get("ExtractAgent")
                subagent_name = cat_to_subagent_name.get(cat, cat)
                for item in items:
                    if isinstance(item, dict):
                        item["subagent_name"] = subagent_name
                        item["model_version"] = model_version
                        item["extraction_timestamp"] = extraction_timestamp

            # Tag and merge
            for cat, data in subresults.items():
                items = data.get("items", [])
                # Normalize non-list payloads (avoid iterating over strings character-by-character)
                if items is None:
                    items = []
                elif not isinstance(items, list):
                    items = [items]
                if items:
                    content_summary.append(f"Extracted {cat.replace('_', ' ').title()}:")
                    for item in items:
                        # Normalize to observable structure
                        # Ensure item is serializable
                        # For structured items (lineage, registry), keep as dict; use 'value' if present
                        val = (item.get("value") if "value" in item else item) if isinstance(item, dict) else item

                        obs_entry = {
                            "type": cat,
                            "value": val,
                            "original_data": item if isinstance(item, dict) else None,
                            "source": "supervisor_aggregation",
                        }
                        _enrich_observable_metadata(
                            obs_entry,
                            item=item,
                            observable_type=cat,
                            article_platforms=article_platforms,
                        )
                        # Observable traceability: surface traceability fields at top level for API
                        if isinstance(item, dict):
                            if item.get("source_evidence") is not None:
                                obs_entry["source_evidence"] = item.get("source_evidence")
                            if item.get("extraction_justification") is not None:
                                obs_entry["extraction_justification"] = item.get("extraction_justification")
                            if item.get("confidence_score") is not None:
                                obs_entry["confidence_score"] = item.get("confidence_score")
                            if item.get("subagent_name") is not None:
                                obs_entry["subagent_name"] = item.get("subagent_name")
                            if item.get("model_version") is not None:
                                obs_entry["model_version"] = item.get("model_version")
                            if item.get("extraction_timestamp") is not None:
                                obs_entry["extraction_timestamp"] = item.get("extraction_timestamp")
                        all_observables.append(obs_entry)

                        # Add to text summary
                        item_str = str(item)
                        if isinstance(item, dict):
                            item_str = json.dumps(item, indent=None)
                        content_summary.append(f"- {item_str}")
                    content_summary.append("")  # Newline separator

            total_count = len(all_observables)

            # Construct final result matching existing schema
            extraction_result = {
                "observables": all_observables,
                "summary": {
                    "count": total_count,
                    "source_url": article.canonical_url,
                    "platforms_detected": article_platforms,
                },
                "discrete_huntables_count": total_count,
                "subresults": subresults,  # Persist detailed breakdown
                "capability_skips": capability_skip_records,
                "extractor_capabilities": {
                    agent_name: sorted(platforms) for agent_name, platforms in AGENT_PLATFORM_CAPABILITIES.items()
                },
                "content": "\n".join(content_summary) if content_summary else "",  # Synthesized content for Sigma Agent
                "raw_response": json.dumps(subresults, indent=2),  # Store subresults as raw_response for compatibility
            }

            # Store conversation log in execution.error_log (merge, don't overwrite)
            # Use the execution object we already have (don't refresh to avoid transaction isolation issues)
            if execution:
                # Ensure error_log is a dict
                if execution.error_log is None or not isinstance(execution.error_log, dict):
                    execution.error_log = {}
                execution.error_log["extract_agent"] = {
                    "conversation_log": conversation_log,
                    "sub_agents_run": sub_agents_run,
                    "sub_agents_disabled": disabled_sub_agents,
                    "capability_skips": capability_skip_records,
                }
                flag_modified(execution, "error_log")
                db_session.commit()
                logger.info(
                    f"[Workflow {state['execution_id']}] Stored extract_agent log, error_log keys: {list(execution.error_log.keys())}"
                )

            discrete_count = total_count

            # Update execution record with extraction results
            if execution:
                execution.extraction_result = extraction_result
                db_session.commit()

            logger.info(f"[Workflow {state['execution_id']}] Extraction: {discrete_count} discrete huntables")

            # Mark extract_agent as complete before returning
            # This ensures generate_sigma doesn't appear until extraction is truly done
            if execution:
                execution.current_step = "extract_agent"  # Keep as extract_agent until next step starts
                # Store completion marker in error_log for streaming view
                if execution.error_log is None:
                    execution.error_log = {}
                if "extract_agent" not in execution.error_log:
                    execution.error_log["extract_agent"] = {}
                execution.error_log["extract_agent"]["completed"] = True
                execution.error_log["extract_agent"]["completed_at"] = datetime.now().isoformat()

                flag_modified(execution, "error_log")
                db_session.commit()

            return {
                **state,
                "extraction_result": extraction_result,
                "discrete_huntables_count": discrete_count,
                "current_step": "extract_agent",
                "status": state.get("status", "running"),
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Extraction error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                execution.current_step = "extract_agent"
                db_session.commit()

            return {
                **state,
                "error": str(e),
                "current_step": "extract_agent",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    async def generate_sigma_node(state: WorkflowState) -> WorkflowState:
        """Step 3: Generate SIGMA rules."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 3: Generate SIGMA")

            from src.services.sigma_generation_service import SigmaGenerationService

            # Load article from DB instead of state
            article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()
            if not article:
                raise ValueError(f"Article {state['article_id']} not found in database")
            filtered_content = state.get("filtered_content") or article.content if article else ""

            # Update execution record BEFORE calling LLM
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                execution.current_step = "generate_sigma"
                db_session.commit()

            # Get config models for SigmaGenerationService
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None

            # Get SIGMA fallback setting from config
            sigma_fallback_enabled = (
                config_obj.sigma_fallback_enabled
                if config_obj and hasattr(config_obj, "sigma_fallback_enabled")
                else False
            )

            # Use the same junk filter threshold the user configured so Sigma
            # content filtering stays in sync with the rest of the pipeline.
            sigma_min_confidence = (
                config_obj.junk_filter_threshold if config_obj and hasattr(config_obj, "junk_filter_threshold") else 0.8
            )

            generation_result = None

            # Get source name
            source_name = article.source.name if article.source else "Unknown"

            # Get agent prompt from database for SIGMA generation
            sigma_prompt_template = None
            sigma_system_prompt = None
            sigma_repair_template = None
            if config_obj and config_obj.agent_prompts and "SigmaRepair" in config_obj.agent_prompts:
                from src.utils.prompt_loader import parse_sigma_repair_prompt_data

                sigma_repair_template = parse_sigma_repair_prompt_data(config_obj.agent_prompts["SigmaRepair"])
                if sigma_repair_template:
                    logger.info(
                        f"[Workflow {state['execution_id']}] Using database prompt for SigmaRepair (len={len(sigma_repair_template)} chars)"
                    )
            if config_obj and config_obj.agent_prompts and "SigmaAgent" in config_obj.agent_prompts:
                from src.utils.prompt_loader import parse_sigma_agent_prompt_data

                sigma_prompt_template, sigma_system_prompt = parse_sigma_agent_prompt_data(
                    config_obj.agent_prompts["SigmaAgent"]
                )
                logger.info(
                    f"[Workflow {state['execution_id']}] Using database prompt for SigmaAgent (template_len={len(sigma_prompt_template or '')} chars, system_len={len(sigma_system_prompt or '')} chars)"
                )
            else:
                logger.info(
                    f"[Workflow {state['execution_id']}] No SigmaAgent prompt in database, using file-based prompt"
                )

            # Determine content to use for SIGMA generation
            extraction_result = state.get("extraction_result", {})
            content_to_use = None

            # If enabled, use filtered article content (minus junk) regardless of extraction results
            if sigma_fallback_enabled:
                content_to_use = filtered_content
                logger.info(
                    f"[Workflow {state['execution_id']}] Using filtered article content ({len(filtered_content)} chars) for SIGMA generation"
                )
            elif extraction_result and extraction_result.get("discrete_huntables_count", 0) > 0:
                # Use extracted content if we have meaningful huntables and toggle is disabled
                extracted_content = extraction_result.get("content", "")
                if extracted_content and len(extracted_content) > 100:
                    content_to_use = extracted_content
                    logger.info(
                        f"[Workflow {state['execution_id']}] Using extracted content ({len(extracted_content)} chars) for SIGMA generation"
                    )
                else:
                    logger.warning(
                        f"[Workflow {state['execution_id']}] Extraction result has {extraction_result.get('discrete_huntables_count', 0)} huntables but no usable content"
                    )

            if (
                content_to_use is not None
                and extraction_result
                and not sigma_fallback_enabled
                and not _has_sigma_generation_eligible_observables(extraction_result)
            ):
                logger.info(
                    f"[Workflow {state['execution_id']}] Extraction produced huntables, but none have "
                    "Sigma-eligible platform/telemetry/logsource metadata. Skipping SIGMA generation."
                )
                return {
                    **state,
                    "sigma_rules": [],
                    "current_step": "generate_sigma",
                    "status": state.get("status", "running"),
                    "termination_reason": TERMINATION_REASON_NO_SIGMA_RULES,
                    "termination_details": {
                        "reason": "No Sigma-eligible platform/telemetry observables",
                        "platforms_detected": extraction_result.get("summary", {}).get("platforms_detected", []),
                        "discrete_huntables_count": extraction_result.get("discrete_huntables_count", 0),
                    },
                }

            # If no content available, skip SIGMA generation
            if content_to_use is None:
                logger.warning(
                    f"[Workflow {state['execution_id']}] No extraction result or zero huntables, and filtered content toggle is disabled. Skipping SIGMA generation."
                )
                return {
                    **state,
                    "sigma_rules": [],
                    "current_step": "generate_sigma",
                    "status": state.get("status", "running"),
                    "termination_reason": TERMINATION_REASON_NO_SIGMA_RULES,
                    "termination_details": {
                        "reason": "No extraction results and filtered content toggle disabled",
                        "discrete_huntables_count": extraction_result.get("discrete_huntables_count", 0)
                        if extraction_result
                        else 0,
                        "sigma_fallback_enabled": False,
                    },
                }

            # Generate SIGMA rules per platform/logsource group. Mixed-platform articles
            # must not produce a single combined Windows/Linux rule in phase one.
            sigma_service = SigmaGenerationService(config_models=agent_models)
            sigma_generation_groups = _build_sigma_generation_groups(extraction_result)
            if not sigma_generation_groups and sigma_fallback_enabled:
                fallback_group = _build_sigma_full_content_fallback_group(
                    extraction_result,
                    content=content_to_use,
                    platforms_detected=extraction_result.get("summary", {}).get("platforms_detected", [])
                    if extraction_result
                    else [],
                )
                # Phase one: macOS generates no Sigma, even via the legacy full-content
                # fallback (spec §6). A macOS-only article therefore produces no rule here,
                # consistent with macOS exclusion in _build_sigma_generation_groups.
                if fallback_group["platform"] != PLATFORM_MACOS:
                    sigma_generation_groups = [fallback_group]
            if not sigma_generation_groups:
                logger.info(
                    f"[Workflow {state['execution_id']}] No Sigma generation groups were eligible after "
                    "platform/logsource routing. Skipping SIGMA generation."
                )
                return {
                    **state,
                    "sigma_rules": [],
                    "current_step": "generate_sigma",
                    "status": state.get("status", "running"),
                    "termination_reason": TERMINATION_REASON_NO_SIGMA_RULES,
                    "termination_details": {
                        "reason": "No eligible Sigma platform/logsource groups",
                        "platforms_detected": extraction_result.get("summary", {}).get("platforms_detected", []),
                        "discrete_huntables_count": extraction_result.get("discrete_huntables_count", 0),
                    },
                }

            sigma_rules = []
            group_errors = []
            combined_conversation_log = []
            combined_validation_results = []
            total_attempts = 0
            valid_rules = 0
            sigma_group_summaries = []

            for group in sigma_generation_groups:
                group_label = (
                    f"{group['platform']}:{group['telemetry_category']}:{_stable_logsource_key(group['logsource_hint'])}"
                )
                logger.info(
                    f"[Workflow {state['execution_id']}] Generating SIGMA for group {group_label} "
                    f"using observables {group['original_indices']}"
                )
                generation_result = await sigma_service.generate_sigma_rules(
                    article_title=article.title,
                    article_content=content_to_use,
                    source_name=source_name,
                    url=article.canonical_url or "",
                    ai_model="lmstudio",  # Provider resolved via config_models
                    max_attempts=3,
                    min_confidence=sigma_min_confidence,
                    execution_id=state["execution_id"],
                    article_id=state["article_id"],
                    sigma_prompt_template=sigma_prompt_template,  # Pass database prompt if available
                    sigma_system_prompt=sigma_system_prompt,  # Pass database system prompt if available
                    sigma_repair_template=sigma_repair_template,  # Pass database repair prompt if available
                    extraction_result=group["extraction_result"],
                )

                group_metadata = generation_result.get("metadata", {}) if generation_result else {}
                group_rules = generation_result.get("rules", []) if generation_result else []
                group_error = generation_result.get("errors") if generation_result else "No generation result"

                for rule in group_rules:
                    if not isinstance(rule, dict):
                        continue
                    _rebase_group_observable_indices(rule, group["original_indices"])
                    rule.setdefault("platform", group["platform"])
                    rule.setdefault("telemetry_category", group["telemetry_category"])
                    rule.setdefault("logsource_hint", group["logsource_hint"])
                    rule.setdefault("generation_basis", f"{group['telemetry_category']}_generic")
                    rule.setdefault("detection_readiness", "generic")
                    rule["sigma_generation_group"] = {
                        "platform": group["platform"],
                        "telemetry_category": group["telemetry_category"],
                        "logsource_hint": group["logsource_hint"],
                        "observable_indices": group["original_indices"],
                    }
                    sigma_rules.append(rule)

                if group_error and not group_rules:
                    group_errors.append(f"{group_label}: {group_error}")

                for entry in group_metadata.get("conversation_log", []) or []:
                    if isinstance(entry, dict):
                        entry = {
                            **entry,
                            "sigma_generation_group": {
                                "platform": group["platform"],
                                "telemetry_category": group["telemetry_category"],
                                "logsource_hint": group["logsource_hint"],
                                "observable_indices": group["original_indices"],
                            },
                        }
                    combined_conversation_log.append(entry)
                combined_validation_results.extend(group_metadata.get("validation_results", []) or [])
                total_attempts += int(group_metadata.get("total_attempts") or 0)
                valid_rules += int(group_metadata.get("valid_rules") or len(group_rules))
                sigma_group_summaries.append(
                    {
                        "platform": group["platform"],
                        "telemetry_category": group["telemetry_category"],
                        "logsource_hint": group["logsource_hint"],
                        "observable_indices": group["original_indices"],
                        "generated_rules": len(group_rules),
                        "error": group_error if group_error and not group_rules else None,
                    }
                )

            sigma_errors = "; ".join(group_errors) if group_errors and not sigma_rules else None
            sigma_metadata = {
                "total_attempts": total_attempts,
                "valid_rules": valid_rules,
                "validation_results": combined_validation_results,
                "conversation_log": combined_conversation_log,
                "sigma_generation_groups": sigma_group_summaries,
            }

            # Log repair-attempt count as a Langfuse score so it's queryable over time
            total_attempts = sigma_metadata.get("total_attempts")
            if total_attempts is not None:
                active_tid = get_active_trace_id()
                if active_tid:
                    score_langfuse_trace(
                        trace_id=active_tid,
                        name="sigma_repair_attempts",
                        value=float(total_attempts),
                        comment=f"execution_id={state.get('execution_id')} rules={len(sigma_rules)}",
                    )

            # Treat Langfuse generator cleanup errors as non-fatal: skip rules, continue workflow
            if sigma_errors and isinstance(sigma_errors, str):
                err_lower = sigma_errors.lower()
                if "generator" in err_lower and (
                    "didn't stop" in err_lower or "stop after throw" in err_lower or "throw" in err_lower
                ):
                    logger.warning(
                        f"[Workflow {state['execution_id']}] SIGMA generation returned generator error; treating as no-rules and continuing. Error: {sigma_errors}"
                    )
                    sigma_errors = None
                    sigma_rules = []
                    if execution:
                        execution.error_message = None
                        execution.status = execution.status or "running"
                        db_session.commit()

            # Update execution record with SIGMA results
            if execution:
                execution.sigma_rules = sigma_rules

                # Store detailed error info in error_log for debugging (even when no errors, for conversation log display)
                # Always store if conversation_log exists OR validation_results exist
                conversation_log = sigma_metadata.get("conversation_log", [])
                validation_results = sigma_metadata.get("validation_results", [])

                # Store if we have conversation_log (even if empty), validation_results, or errors
                if "conversation_log" in sigma_metadata or validation_results or sigma_errors:
                    error_log_entry = {
                        "errors": sigma_errors,
                        "total_attempts": sigma_metadata.get(
                            "total_attempts", len(conversation_log) if conversation_log else 0
                        ),
                        "validation_results": validation_results,
                        "conversation_log": conversation_log if conversation_log else [],  # Ensure it's always a list
                        "sigma_generation_groups": sigma_metadata.get("sigma_generation_groups", []),
                    }
                    execution.error_log = {**(execution.error_log or {}), "generate_sigma": error_log_entry}
                    logger.debug(f"Stored conversation_log with {len(conversation_log)} entries")

                # Check if SIGMA validation failed (no valid rules generated)
                # Check both errors field and metadata validation results
                validation_failed = (not sigma_rules and sigma_errors) or (
                    sigma_metadata.get("valid_rules", 0) == 0
                    and sigma_metadata.get("validation_results")
                    and not any(r.get("is_valid", False) for r in sigma_metadata.get("validation_results", []))
                )

                if validation_failed:
                    error_msg = sigma_errors or "SIGMA validation failed: No valid rules generated after all attempts"
                    execution.status = "failed"
                    execution.error_message = error_msg
                    execution.current_step = "generate_sigma"
                    db_session.commit()
                    logger.error(f"[Workflow {state['execution_id']}] SIGMA validation failed: {error_msg}")

                    return {
                        **state,
                        "sigma_rules": [],
                        "error": error_msg,
                        "current_step": "generate_sigma",
                        "should_continue": False,
                    }

                db_session.commit()

            logger.info(f"[Workflow {state['execution_id']}] Generated {len(sigma_rules)} SIGMA rules")

            return {
                **state,
                "sigma_rules": sigma_rules,
                "current_step": "generate_sigma",
                "status": state.get("status", "running"),
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

        except Exception as e:
            err_msg = str(e)
            is_generator_error = "generator" in err_msg.lower() and (
                "didn't stop" in err_msg.lower() or "throw" in err_msg.lower()
            )
            if is_generator_error:
                logger.warning(
                    f"[Workflow {state['execution_id']}] SIGMA generation encountered Langfuse generator error "
                    f"(non-critical): {e}. Treating as no-rules and continuing."
                )
                execution = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                    .first()
                )
                if execution:
                    # Do NOT mark failed; just note no rules
                    execution.current_step = "generate_sigma"
                    execution.sigma_rules = []
                    execution.error_message = None
                    execution.status = execution.status or "running"
                    db_session.commit()

                # Return state with no rules but no error so workflow continues
                return {
                    **state,
                    "sigma_rules": [],
                    "error": None,
                    "current_step": "generate_sigma",
                    "should_continue": False,
                    "status": state.get("status", "running"),
                    "termination_reason": TERMINATION_REASON_NO_SIGMA_RULES,
                    "termination_details": {
                        "reason": "Langfuse generator error during SIGMA generation",
                        **(state.get("termination_details") or {}),
                    },
                }

            logger.error(f"[Workflow {state['execution_id']}] SIGMA generation error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = err_msg
                db_session.commit()

            return {
                **state,
                "error": err_msg,
                "current_step": "generate_sigma",
                "should_continue": False,
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    def check_sigma_generation(state: WorkflowState) -> str:
        """Check if SIGMA generation succeeded or if workflow should stop."""
        # Only stop if there's an actual error (SIGMA validation failure)
        # Don't stop for threshold-based stops (those are handled by rank_article check)
        if state.get("error"):
            logger.warning(
                f"[Workflow {state.get('execution_id')}] SIGMA generation failed with error, stopping workflow"
            )
            return "end"
        # If there are zero rules but no error (e.g., generator error handled), treat as no-rules and still continue so downstream can mark termination_reason
        logger.info(
            f"[Workflow {state.get('execution_id')}] SIGMA generation completed (rules: {len(state.get('sigma_rules') or [])}); continuing to similarity search"
        )
        return "similarity_search"

    async def similarity_search_node(state: WorkflowState) -> WorkflowState:
        """Step 4: Search for similar SIGMA rules."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 4: Similarity Search")

            # Check if workflow already failed (e.g., SIGMA validation failed)
            if state.get("error"):
                logger.warning(f"[Workflow {state['execution_id']}] Workflow has error, skipping similarity search")
                return {
                    **state,
                    "similarity_results": None,  # None indicates search didn't run
                    "max_similarity": 1.0,
                    "current_step": state.get("current_step", "similarity_search"),
                    "status": state.get("status", "running"),
                    "termination_reason": state.get("termination_reason"),
                    "termination_details": state.get("termination_details"),
                }

            sigma_rules = state.get("sigma_rules", [])
            if not sigma_rules:
                logger.warning(f"[Workflow {state['execution_id']}] No SIGMA rules to search")
                return {
                    **state,
                    "similarity_results": None,  # None indicates search didn't run
                    "max_similarity": 0.0,
                    "current_step": "similarity_search",
                    "status": state.get("status", "running"),
                    "termination_reason": state.get("termination_reason"),
                    "termination_details": state.get("termination_details"),
                }

            novelty_results = []
            max_novelty_score = 1.0  # Start at 1.0 (fully novel), decrease with similarity
            config = state.get("config")
            similarity_threshold = (
                config.get("similarity_threshold", 0.5) if config and isinstance(config, dict) else 0.5
            )

            # Get config models for embedding model selection
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj else None

            # Initialize SigmaMatchingService (now uses novelty assessment internally)
            sigma_matching_service = SigmaMatchingService(db_session, config_models=agent_models)

            # Assess novelty for each generated rule using behavioral novelty assessment
            for rule in sigma_rules:
                # assess_rule_novelty now uses novelty assessment internally
                match_result = sigma_matching_service.assess_rule_novelty(
                    proposed_rule=rule,
                    threshold=0.0,  # Get all results, filter by threshold below
                )
                similar_rules = match_result.get("matches", [])

                # Single source of truth (todo 001, C1+C2): distinguish a scored
                # low/zero result from an *inconclusive* one (candidates evaluated,
                # 0 behavioral matches). rule_max_sim is None when inconclusive.
                rule_summary = summarize_rule_novelty(match_result)
                rule_max_sim = rule_summary["max_similarity"]

                # Filter by threshold and limit to top 10
                filtered_rules = [r for r in similar_rules if r.get("similarity", 0.0) >= similarity_threshold][:10]

                # Extract novelty information
                rule_novelty_scores = [r.get("novelty_score", 1.0) for r in filtered_rules]
                rule_min_novelty = min(rule_novelty_scores) if rule_novelty_scores else 1.0
                rule_novelty_label = filtered_rules[0].get("novelty_label", "NOVEL") if filtered_rules else "NOVEL"

                novelty_results.append(
                    {
                        "rule_title": rule.get("title"),
                        "similar_rules": [r for r in similar_rules if r.get("similarity", 0.0) > 0][:10],
                        "max_similarity": rule_max_sim,  # None when comparator inconclusive
                        "total_candidates_evaluated": rule_summary["total_candidates_evaluated"],
                        "behavioral_matches_found": rule_summary["behavioral_matches_found"],
                        "comparator_inconclusive": rule_summary["comparator_inconclusive"],
                        "canonical_class": rule_summary["canonical_class"],
                        "logsource_unresolved": rule_summary["logsource_unresolved"],
                        "novelty_label": rule_novelty_label,
                        "novelty_score": rule_min_novelty,
                        "top_matches": filtered_rules[:5] if filtered_rules else similar_rules[:5],
                    }
                )

                max_novelty_score = min(max_novelty_score, rule_min_novelty)

            # Update execution record
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                # Only update current_step if workflow didn't fail earlier
                if execution.status != "failed":
                    execution.current_step = "similarity_search"
                # Store both for backward compatibility
                execution.similarity_results = novelty_results  # Keep key name for backward compatibility
                db_session.commit()

            logger.info(f"[Workflow {state['execution_id']}] Novelty assessment: min_novelty={max_novelty_score:.2f}")

            return {
                **state,
                "similarity_results": novelty_results,
                "max_similarity": 1.0 - max_novelty_score,
                "current_step": "similarity_search",
                "status": state.get("status", "running"),
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Similarity search error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                execution.current_step = "similarity_search"
                db_session.commit()

            return {
                **state,
                "error": str(e),
                "current_step": "similarity_search",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    def promote_to_queue_node(state: WorkflowState) -> WorkflowState:
        """Step 5: Promote rules to queue if similarity is low."""
        try:
            logger.info(f"[Workflow {state['execution_id']}] Step 5: Promote to Queue")

            # Sigma eval runs score the generated rules (already persisted on
            # execution.sigma_rules by generate_sigma) but must NOT promote them
            # into the production review queue.
            eval_execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if eval_execution is not None and is_sigma_eval_execution(eval_execution):
                logger.info(
                    f"[Workflow {state['execution_id']}] Sigma eval run -- skipping queue promotion "
                    f"({len(state.get('sigma_rules') or [])} rules scored, not queued)"
                )
                return {
                    **state,
                    "queued_rules": [],
                    "current_step": "promote_to_queue",
                    "status": "completed",
                }

            # Check if workflow already failed - should not reach here if conditional edge works correctly
            if state.get("error"):
                logger.warning(f"[Workflow {state['execution_id']}] Workflow has error, skipping queue promotion")
                execution = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                    .first()
                )
                if execution and execution.status != "failed":
                    execution.status = "failed"
                    execution.error_message = state.get("error")
                    execution.current_step = state.get("current_step", "generate_sigma")
                    db_session.commit()
                return {
                    **state,
                    "queued_rules": [],
                    "current_step": state.get("current_step", "generate_sigma"),
                    "status": "failed",
                    "termination_reason": state.get("termination_reason"),
                    "termination_details": state.get("termination_details"),
                }

            sigma_rules = state.get("sigma_rules", [])
            similarity_results = state.get("similarity_results")
            config = state.get("config")
            similarity_threshold = (
                config.get("similarity_threshold", 0.5) if config and isinstance(config, dict) else 0.5
            )
            termination_reason = state.get("termination_reason")
            termination_details = state.get("termination_details")

            if not sigma_rules:
                if termination_reason is None:
                    termination_reason = TERMINATION_REASON_NO_SIGMA_RULES
                if termination_details is None:
                    termination_details = {"generated_rules": 0}

            # Check if similarity search failed or didn't run
            # Don't queue if similarity search failed (error in state) or didn't run (similarity_results is None)
            if state.get("error") or similarity_results is None:
                logger.warning(
                    f"[Workflow {state['execution_id']}] Similarity search failed or didn't run - skipping queue promotion"
                )
                queued_rules = []
            else:
                # Similarity search ran successfully - calculate max_similarity from results
                if len(similarity_results) > 0:
                    # None = inconclusive (todo 001). Exclude from the aggregate so an
                    # inconclusive-only batch yields 0.0 (-> falls through to promote as
                    # needs_review) rather than TypeError on max([..., None]).
                    scored = [s for s in (r.get("max_similarity") for r in similarity_results) if s is not None]
                    max_similarity = max(scored) if scored else 0.0
                else:
                    # Similarity search ran successfully but found 0 matches - treat as 0.0 similarity
                    max_similarity = 0.0
                    logger.info(
                        f"[Workflow {state['execution_id']}] Similarity search completed with 0 matches - treating as 0.0 similarity"
                    )

                # Only promote if max similarity is below threshold
                if max_similarity >= similarity_threshold:
                    logger.info(
                        f"[Workflow {state['execution_id']}] Max similarity {max_similarity:.2f} >= threshold {similarity_threshold}, skipping queue"
                    )
                    queued_rules = []
                else:
                    queued_rules = []
                    lint_failures_count = 0
                    # Load article from DB instead of state
                    article = db_session.query(ArticleTable).filter(ArticleTable.id == state["article_id"]).first()

                    # Queue each rule with low similarity
                    for idx, rule in enumerate(sigma_rules):
                        rule_similarity = (
                            similarity_results[idx] if idx < len(similarity_results) else {"max_similarity": 0.0}
                        )
                        inconclusive = rule_similarity.get("comparator_inconclusive", False)
                        rule_max_sim = rule_similarity.get("max_similarity")

                        # Enqueue when inconclusive (route to needs_review) OR a genuine
                        # sub-threshold score. A scored >= threshold rule is suppressed
                        # as a near-duplicate (novelty suppression now actually works).
                        if inconclusive or (rule_max_sim is not None and rule_max_sim < similarity_threshold):
                            # Strip non-Sigma grounding metadata from rule YAML; keep it in rule_metadata.
                            non_sigma_metadata_fields = {
                                "observables_used",
                                "observables_used_inferred",
                                "platform",
                                "telemetry_category",
                                "generation_basis",
                                "detection_readiness",
                                "logsource_hint",
                                "sigma_generation_group",
                            }
                            rule_for_yaml = {k: v for k, v in rule.items() if k not in non_sigma_metadata_fields}
                            rule_yaml = yaml.dump(rule_for_yaml, default_flow_style=False, sort_keys=False)

                            # Guard: confirm the generated YAML round-trips to a dict with required keys.
                            # yaml.dump(dict) should always satisfy this, but catch regressions early.
                            _parsed_back = yaml.safe_load(rule_yaml)
                            _missing_keys = [
                                k for k in ("title", "logsource", "detection") if k not in (_parsed_back or {})
                            ]
                            if not isinstance(_parsed_back, dict) or _missing_keys:
                                logger.warning(
                                    f"[Workflow {state['execution_id']}] Skipping rule idx={idx}: "
                                    f"rule_yaml failed Sigma dict validation "
                                    f"(type={type(_parsed_back).__name__}, missing={_missing_keys}). "
                                    f"Preview: {rule_yaml[:120]!r}"
                                )
                                continue

                            rule_meta = {
                                "title": rule.get("title"),
                                "description": rule.get("description"),
                                "tags": rule.get("tags", []),
                                "level": rule.get("level"),
                                "status": rule.get("status", "experimental"),
                            }
                            if rule.get("observables_used") is not None:
                                rule_meta["observables_used"] = rule["observables_used"]
                            for metadata_key in (
                                "observables_used_inferred",
                                "platform",
                                "telemetry_category",
                                "generation_basis",
                                "detection_readiness",
                                "logsource_hint",
                                "sigma_generation_group",
                            ):
                                if rule.get(metadata_key) is not None:
                                    rule_meta[metadata_key] = rule[metadata_key]

                            # SigmaSim Finding B: stamp the logsource-resolution result so a rule
                            # whose logsource does not map to a canonical class (degraded dedup) is
                            # queryable (rule_metadata->>'logsource_unresolved') and logged — not
                            # silent. Fail open: the rule is still enqueued either way.
                            rule_meta["canonical_class"] = rule_similarity.get("canonical_class")
                            rule_meta["logsource_unresolved"] = rule_similarity.get("logsource_unresolved", True)
                            rule_meta["logsource_lint_failures"] = rule_similarity.get("logsource_lint_failures", [])
                            if rule_meta["logsource_lint_failures"]:
                                lint_failures_count += 1
                            if rule_meta["logsource_unresolved"]:
                                logger.warning(
                                    f"[Workflow {state['execution_id']}] Generated rule idx={idx} "
                                    f"({rule.get('title')!r}) has an unclassifiable logsource "
                                    f"{rule.get('logsource')} — no canonical_class, dedup degraded to "
                                    f"logsource_key fallback (SigmaSim Finding B). Prefer a SigmaHQ "
                                    f"`category:` (e.g. process_creation) over bare `service:`."
                                )

                            # Create queue entry
                            queue_entry = SigmaRuleQueueTable(
                                article_id=article.id if article else state["article_id"],
                                workflow_execution_id=state["execution_id"],
                                rule_yaml=rule_yaml,
                                rule_metadata=rule_meta,
                                similarity_scores=rule_similarity.get("similar_rules", []),
                                max_similarity=None if inconclusive else rule_max_sim,
                                behavioral_matches_found=rule_similarity.get("behavioral_matches_found"),
                                total_candidates_evaluated=rule_similarity.get("total_candidates_evaluated"),
                                status="needs_review" if inconclusive else "pending",
                            )
                            db_session.add(queue_entry)
                            queued_rules.append(queue_entry.id)

                db_session.commit()
                logger.info(f"[Workflow {state['execution_id']}] Queued {len(queued_rules)} rules")
                if queued_rules:
                    logger.info(
                        f"[Workflow {state['execution_id']}] Logsource lint summary: "
                        f"{lint_failures_count}/{len(queued_rules)} rules have logsource_lint_failures"
                    )

            # Update execution record to completed
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )

            if execution:
                # Only update current_step if workflow didn't fail earlier
                if execution.status != "failed":
                    mark_execution_completed(
                        execution,
                        "promote_to_queue",
                        db_session=db_session,
                        reason=termination_reason,
                        details=termination_details,
                        commit=False,
                    )
                db_session.commit()

            return {
                **state,
                "queued_rules": queued_rules,
                "current_step": "promote_to_queue",
                "status": "completed",
                "termination_reason": termination_reason,
                "termination_details": termination_details,
            }

        except Exception as e:
            logger.error(f"[Workflow {state['execution_id']}] Queue promotion error: {e}")
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
                .first()
            )
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                execution.current_step = "promote_to_queue"
                db_session.commit()

            return {
                **state,
                "error": str(e),
                "current_step": "promote_to_queue",
                "status": "failed",
                "termination_reason": state.get("termination_reason"),
                "termination_details": state.get("termination_details"),
            }

    def check_should_continue_after_os_detection(state: WorkflowState) -> str:
        """Route after Platform Detection."""
        should_continue = state.get("should_continue", False)
        if should_continue:
            return "junk_filter"
        return "end"

    def check_should_continue_after_junk_filter(state: WorkflowState) -> str:
        """Gate the pipeline on junk filter result. Routes to END when no huntable content."""
        if state.get("termination_reason") == TERMINATION_REASON_JUNK_FILTER:
            return "end"
        return check_rank_agent_enabled(state)

    def check_rank_agent_enabled(state: WorkflowState) -> str:
        """Check if rank agent is enabled and route accordingly.

        Evals ALWAYS skip rank agent regardless of config setting.
        """
        config = state.get("config", {})
        execution_id = state.get("execution_id")
        state_eval_run = _bool_from_value(state.get("eval_run", False))
        state_skip_rank = _bool_from_value(state.get("skip_rank_agent", False))
        if state_eval_run or state_skip_rank:
            reason = "eval run from state config" if state_eval_run else "skip flag in state"
            logger.info(f"[Workflow {execution_id}] Skipping Rank Agent ({reason})")
            return "rank_agent_bypass"

        # Check if this is an eval run that should skip rank agent
        # This check takes precedence over any config setting
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )

        # Check execution config_snapshot first (most reliable for evals)
        if execution and execution.config_snapshot:
            config_snapshot = execution.config_snapshot
            skip_rank_agent = _bool_from_value(config_snapshot.get("skip_rank_agent", False)) or _bool_from_value(
                config_snapshot.get("eval_run", False)
            )

            if skip_rank_agent:
                logger.info(f"[Workflow {execution_id}] Skipping Rank Agent (eval run - always bypassed)")
                return "rank_agent_bypass"

        # Also check state config (in case it was set during config merge)
        if isinstance(config, dict):
            skip_from_state = _bool_from_value(config.get("skip_rank_agent", False)) or _bool_from_value(
                config.get("eval_run", False)
            )
            if skip_from_state:
                logger.info(f"[Workflow {execution_id}] Skipping Rank Agent (eval run from state config)")
                return "rank_agent_bypass"

        # Check config setting (only if not an eval run)
        # CRITICAL: Use _bool_from_value to handle string/None values correctly
        rank_agent_enabled_raw = config.get("rank_agent_enabled", True) if isinstance(config, dict) else True
        rank_agent_enabled = _bool_from_value(rank_agent_enabled_raw)
        logger.info(
            f"[Workflow {execution_id}] Rank agent enabled check: rank_agent_enabled={rank_agent_enabled} (raw: {rank_agent_enabled_raw}, type: {type(rank_agent_enabled_raw).__name__}), config keys: {list(config.keys()) if isinstance(config, dict) else 'N/A'}"
        )
        if rank_agent_enabled:
            return "rank_article"
        logger.info(f"[Workflow {execution_id}] Rank agent disabled - bypassing to extract_agent")
        return "rank_agent_bypass"

    def check_should_continue_after_rank(state: WorkflowState) -> str:
        """Check if workflow should continue after ranking."""
        if state.get("should_continue", False):
            return "extract_agent"
        return "end"

    def check_should_skip_sigma_for_eval(state: WorkflowState) -> str:
        """Check if SIGMA generation should be skipped for eval runs."""
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == state["execution_id"])
            .first()
        )

        if execution:
            config_snapshot = execution.config_snapshot or {}
            # A Sigma eval needs the full pipeline through generate_sigma, so it
            # overrides the blanket eval_run -> skip-sigma behavior used by the
            # extractor evals.
            is_sigma_eval = _bool_from_value(config_snapshot.get("sigma_eval", False))
            skip_sigma = (not is_sigma_eval) and (
                _bool_from_value(config_snapshot.get("skip_sigma_generation", False))
                or _bool_from_value(config_snapshot.get("eval_run", False))
                or _bool_from_value(state.get("skip_sigma_generation", False))
            )

            if skip_sigma:
                logger.info(f"[Workflow {state['execution_id']}] Skipping SIGMA generation (eval run)")
                # Mark execution as completed after extraction
                execution.status = "completed"
                execution.current_step = "extract_agent"
                execution.completed_at = datetime.now()
                db_session.commit()
                # Use state's extraction_result — execution may not have it loaded yet in this path
                extraction_from_state = (
                    state.get("extraction_result") if isinstance(state.get("extraction_result"), dict) else None
                )
                _update_subagent_eval_on_completion(
                    execution, db_session, extraction_result_override=extraction_from_state
                )
                return "end"

        return "generate_sigma"

    # Build workflow graph
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("os_detection", os_detection_node)
    workflow.add_node("junk_filter", junk_filter_node)
    workflow.add_node("rank_article", rank_article_node)
    workflow.add_node("rank_agent_bypass", rank_agent_bypass_node)
    workflow.add_node("extract_agent", extract_agent_node)
    workflow.add_node("generate_sigma", generate_sigma_node)
    workflow.add_node("similarity_search", similarity_search_node)
    workflow.add_node("promote_to_queue", promote_to_queue_node)

    # Define edges
    workflow.set_entry_point("os_detection")
    workflow.add_conditional_edges(
        "os_detection", check_should_continue_after_os_detection, {"junk_filter": "junk_filter", "end": END}
    )
    workflow.add_conditional_edges(
        "junk_filter",
        check_should_continue_after_junk_filter,
        {"rank_article": "rank_article", "rank_agent_bypass": "rank_agent_bypass", "end": END},
    )
    workflow.add_conditional_edges(
        "rank_article", check_should_continue_after_rank, {"extract_agent": "extract_agent", "end": END}
    )
    workflow.add_edge("rank_agent_bypass", "extract_agent")
    workflow.add_conditional_edges(
        "extract_agent", check_should_skip_sigma_for_eval, {"generate_sigma": "generate_sigma", "end": END}
    )
    workflow.add_conditional_edges(
        "generate_sigma", check_sigma_generation, {"similarity_search": "similarity_search", "end": END}
    )
    workflow.add_edge("similarity_search", "promote_to_queue")
    workflow.add_edge("promote_to_queue", END)

    return workflow.compile()


async def run_workflow(article_id: int, db_session: Session, execution_id: int | None = None) -> dict[str, Any]:
    """
    Run agentic workflow for an article.

    Args:
        article_id: ID of article to process
        db_session: Database session

    Returns:
        Workflow execution result
    """
    try:
        # Get article and execution
        article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
        if not article:
            raise ValueError(f"Article {article_id} not found")

        execution = None
        if execution_id is not None:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.id == execution_id)
                .first()
            )

        if not execution:
            execution = (
                db_session.query(AgenticWorkflowExecutionTable)
                .filter(
                    AgenticWorkflowExecutionTable.article_id == article_id,
                    AgenticWorkflowExecutionTable.status.in_(["pending", "running"]),
                )
                .order_by(AgenticWorkflowExecutionTable.created_at.desc())
                .first()
            )

        # Get config service (needed for both paths)
        trigger_service = WorkflowTriggerService(db_session)

        if not execution:
            # Create execution record if it doesn't exist (e.g., when called directly via Celery)
            # NOTE: This should rarely happen for evals since they create execution first.
            # Guard: check eligibility before creating an untracked execution so that low-score
            # articles (e.g. hunt_score < auto_trigger threshold) are never silently re-run when
            # someone dispatches trigger_agentic_workflow without an execution_id.
            import traceback as _tb  # noqa: PLC0415

            _stack = "".join(_tb.format_stack())
            logger.warning(
                "No pending/running execution found for article %d — creating one without execution_id. "
                "This should be rare; the normal path always carries an execution_id. "
                "Call stack:\n%s",
                article_id,
                _stack,
            )
            ok, block_reason = trigger_service._workflow_eligibility(article)
            if not ok:
                logger.warning(
                    "Refusing to create execution for article %d (bare Celery dispatch blocked): %s",
                    article_id,
                    block_reason,
                )
                return {"success": False, "skipped": True, "reason": block_reason}
            config_obj = trigger_service.get_active_config()
            execution = AgenticWorkflowExecutionTable(
                article_id=article_id,
                status="pending",
                config_snapshot={
                    "min_hunt_score": config_obj.min_hunt_score if config_obj else 97.0,
                    "ranking_threshold": config_obj.ranking_threshold if config_obj else 6.0,
                    "similarity_threshold": config_obj.similarity_threshold if config_obj else 0.5,
                    "junk_filter_threshold": config_obj.junk_filter_threshold if config_obj else 0.8,
                    "agent_models": config_obj.agent_models if config_obj else {},
                    "agent_prompts": config_obj.agent_prompts if config_obj else {},
                    "rank_agent_enabled": config_obj.rank_agent_enabled
                    if config_obj and hasattr(config_obj, "rank_agent_enabled")
                    else True,
                    "cmdline_attention_preprocessor_enabled": getattr(
                        config_obj, "cmdline_attention_preprocessor_enabled", True
                    )
                    if config_obj
                    else True,
                    "proc_tree_attention_preprocessor_enabled": getattr(
                        config_obj, "proc_tree_attention_preprocessor_enabled", True
                    )
                    if config_obj
                    else True,
                    "config_id": config_obj.id if config_obj else None,
                    "config_version": config_obj.version if config_obj else None,
                }
                if config_obj
                else None,
            )
            db_session.add(execution)
            db_session.commit()
            db_session.refresh(execution)
            logger.info(f"Created execution record {execution.id} for article {article_id}")
        else:
            logger.info(
                f"Found existing execution {execution.id} for article {article_id}, status: {execution.status}, has config_snapshot: {execution.config_snapshot is not None}"
            )

        # Get config
        config_obj = trigger_service.get_active_config()
        config = (
            {
                "min_hunt_score": config_obj.min_hunt_score if config_obj else 97.0,
                "ranking_threshold": config_obj.ranking_threshold if config_obj else 6.0,
                "similarity_threshold": config_obj.similarity_threshold if config_obj else 0.5,
                "junk_filter_threshold": config_obj.junk_filter_threshold if config_obj else 0.8,
                "agent_models": config_obj.agent_models
                if config_obj and config_obj.agent_models and isinstance(config_obj.agent_models, dict)
                else {},
                "rank_agent_enabled": config_obj.rank_agent_enabled
                if config_obj and hasattr(config_obj, "rank_agent_enabled")
                else True,
                "cmdline_attention_preprocessor_enabled": getattr(
                    config_obj, "cmdline_attention_preprocessor_enabled", True
                )
                if config_obj
                else True,
                "proc_tree_attention_preprocessor_enabled": getattr(
                    config_obj, "proc_tree_attention_preprocessor_enabled", True
                )
                if config_obj
                else True,
            }
            if config_obj
            else {
                "min_hunt_score": 97.0,
                "ranking_threshold": 6.0,
                "similarity_threshold": 0.5,
                "junk_filter_threshold": 0.8,
                "agent_models": {},
                "rank_agent_enabled": True,
                "cmdline_attention_preprocessor_enabled": True,
                "proc_tree_attention_preprocessor_enabled": True,
            }
        )

        # Merge config_snapshot from execution (for eval runs and other overrides)
        # Use deep merge for nested dicts like agent_models, agent_prompts
        if execution.config_snapshot:
            snapshot = execution.config_snapshot
            # Merge top-level values
            for key, value in snapshot.items():
                if key in ("agent_models", "agent_prompts") and isinstance(value, dict):
                    # Deep merge nested dicts - preserve existing values, add/update from snapshot
                    if key in config and isinstance(config[key], dict):
                        config[key] = {**config[key], **value}
                    else:
                        config[key] = value.copy() if isinstance(value, dict) else value
                elif key in ("agent_models", "agent_prompts") and value is None:
                    # Snapshot has None (e.g. default config before preset) - keep existing or use {}
                    config[key] = config.get(key) if isinstance(config.get(key), dict) else {}
                else:
                    # Overwrite other values (eval flags, thresholds, etc.)
                    config[key] = value

            # Ensure evals always skip rank agent regardless of config setting
            skip_rank_agent = _bool_from_value(snapshot.get("skip_rank_agent", False)) or _bool_from_value(
                snapshot.get("eval_run", False)
            )

            if skip_rank_agent:
                config["rank_agent_enabled"] = False
                logger.info(f"[Workflow {execution.id}] Rank agent disabled: skip_rank_agent=True (eval run)")
            elif "rank_agent_enabled" in snapshot:
                # Explicitly use rank_agent_enabled from snapshot if present (for non-eval runs)
                # CRITICAL: Convert to bool to handle string/None values
                snapshot_value = snapshot.get("rank_agent_enabled", True)
                config["rank_agent_enabled"] = _bool_from_value(snapshot_value)
                logger.info(
                    f"[Workflow {execution.id}] Using rank_agent_enabled={config['rank_agent_enabled']} from config_snapshot (raw value: {snapshot_value}, type: {type(snapshot_value).__name__})"
                )
            else:
                # Snapshot doesn't have rank_agent_enabled - keep value from active config
                logger.info(
                    f"[Workflow {execution.id}] rank_agent_enabled not in snapshot, using active config value: {config.get('rank_agent_enabled', True)}"
                )

        state_eval_run_flag = _bool_from_value(config.get("eval_run", False))
        state_skip_rank_flag = _bool_from_value(config.get("skip_rank_agent", False))

        # Auto-load LMStudio models before starting workflow (only when lmstudio is actually used)
        agent_models_for_loading = config.get("agent_models") or {}
        _lmstudio_providers = {
            agent_models_for_loading.get("RankAgent_provider", ""),
            agent_models_for_loading.get("ExtractAgent_provider", ""),
            agent_models_for_loading.get("SigmaAgent_provider", ""),
        }

        # Health-check gate: abort early when LMStudio is configured but unreachable
        if agent_models_for_loading and "lmstudio" in _lmstudio_providers:
            reachable, _ = await _probe_lmstudio()
            if not reachable:
                error_msg = "LMStudio is not reachable. Start LMStudio and load a model before running the workflow."
                logger.error(f"[Workflow {execution.id}] {error_msg}")
                execution.status = "failed"
                execution.error_message = error_msg
                db_session.commit()
                return {
                    "success": False,
                    "execution_id": int(execution.id),
                    "error": error_msg,
                    "ranking_score": None,
                    "discrete_huntables_count": None,
                    "sigma_rules_count": 0,
                    "queued_rules_count": 0,
                }

        if agent_models_for_loading and "lmstudio" in _lmstudio_providers:
            logger.info(f"[Workflow {execution.id}] Auto-loading LMStudio models...")
            load_result = auto_load_workflow_models(
                agent_models_for_loading,
            )
            if load_result["models_loaded"]:
                logger.info(f"[Workflow {execution.id}] ✅ Loaded {len(load_result['models_loaded'])} model(s)")
            if load_result["models_failed"]:
                logger.warning(
                    f"[Workflow {execution.id}] ⚠️ Failed to load {len(load_result['models_failed'])} model(s) - workflow will continue"
                )
            if not load_result.get("lmstudio_available", load_result.get("lmstudio_cli_available")):
                logger.warning(f"[Workflow {execution.id}] LMStudio API not reachable - models must be loaded manually")

        # Initialize state
        execution.status = "running"
        execution.started_at = datetime.now()
        execution.current_step = "os_detection"
        db_session.commit()

        initial_state: WorkflowState = {
            "article_id": article_id,
            "execution_id": execution.id,
            "article": None,  # Don't store ArticleTable in state - load from DB when needed
            "config": config,
            "eval_run": state_eval_run_flag,
            "skip_rank_agent": state_skip_rank_flag,
            "os_detection_result": None,
            "detected_os": None,
            "filtered_content": None,
            "junk_filter_result": None,
            "ranking_score": None,
            "ranking_reasoning": None,
            "should_continue": True,
            "extraction_result": None,
            "discrete_huntables_count": None,
            "sigma_rules": None,
            "similarity_results": None,
            "max_similarity": None,
            "queued_rules": None,
            "error": None,
            "current_step": "os_detection",
            "status": "running",
            "termination_reason": None,
            "termination_details": None,
        }

        # Get config models for context check (use config if available, otherwise env vars)
        config_obj = trigger_service.get_active_config()
        agent_models = config_obj.agent_models if config_obj else None

        # Set execution context for LLM service tracing
        llm_service = LLMService(config_models=agent_models)
        llm_service._current_execution_id = execution.id
        llm_service._current_article_id = article_id

        # Check context length before starting workflow
        # Skip rank agent model check if rank_agent_enabled is False
        rank_agent_enabled = _bool_from_value(config.get("rank_agent_enabled", True))
        logger.info(
            f"[Workflow {execution.id}] Context check: rank_agent_enabled={rank_agent_enabled}, config keys: {list(config.keys())}"
        )
        if rank_agent_enabled:
            try:
                context_check = await llm_service.check_model_context_length()
                logger.info(
                    f"Context length validation passed for workflow execution {execution.id}: "
                    f"{context_check['context_length']} tokens (threshold: {context_check['threshold']})"
                )
            except RuntimeError as e:
                # Update execution status to failed with context length error
                execution.status = "failed"
                execution.error_message = str(e)
                execution.current_step = "context_length_check"
                db_session.commit()
                logger.error(f"Workflow execution {execution.id} failed context length check: {e}")
                raise
        else:
            logger.info(
                f"Workflow execution {execution.id}: Skipping rank agent context length check "
                f"(rank_agent_enabled=False)"
            )

        # Create and run workflow with LangFuse tracing
        workflow_completed = False
        workflow_error = None
        final_state = None

        try:
            with trace_workflow_execution(execution_id=execution.id, article_id=article_id) as trace:
                # Persist Langfuse trace_id immediately so debug links can be direct
                try:
                    if trace:
                        trace_id_value = getattr(trace, "trace_id", None) or getattr(trace, "id", None)
                        if trace_id_value:
                            # Refresh execution to avoid stale state
                            db_session.refresh(execution)
                            log_data = execution.error_log if isinstance(execution.error_log, dict) else {}
                            if not isinstance(log_data, dict):
                                log_data = {}
                            log_data["langfuse_trace_id"] = trace_id_value
                            execution.error_log = log_data
                            db_session.commit()
                            logger.info(
                                "Persisted Langfuse trace_id for execution %s: %s",
                                execution.id,
                                trace_id_value,
                            )
                        else:
                            logger.warning(
                                "Langfuse trace missing id for execution %s; cannot persist",
                                execution.id,
                            )
                except Exception as trace_persist_error:
                    logger.debug(
                        f"Could not persist Langfuse trace_id for execution {execution.id}: {trace_persist_error}"
                    )
                    # Rollback any failed transaction from trace persistence
                    with contextlib.suppress(Exception):
                        db_session.rollback()

                workflow_graph = create_agentic_workflow(db_session)
                final_state = await workflow_graph.ainvoke(initial_state)

                # Update trace with final output (non-critical - wrap in try/except)
                if trace:
                    try:
                        _sigma_rules = final_state.get("sigma_rules", []) or []
                        import json as _json

                        _rules_serialized = _json.dumps(_sigma_rules)
                        # OTel attribute values have a practical size ceiling; if the full
                        # rules payload would exceed ~32KB, store only titles+ids to avoid
                        # silent truncation of the trace output attribute.
                        if len(_rules_serialized) > 32768:
                            _sigma_rules_out = [{"title": r.get("title"), "id": r.get("id")} for r in _sigma_rules]
                        else:
                            _sigma_rules_out = _sigma_rules
                        trace.update(
                            output={
                                "status": "completed" if final_state.get("error") is None else "failed",
                                "ranking_score": final_state.get("ranking_score"),
                                "sigma_rules_count": len(_sigma_rules),
                                "queued_rules_count": len(final_state.get("queued_rules", [])),
                                "final_step": final_state.get("current_step"),
                                "error": final_state.get("error"),
                                "sigma_rules": _sigma_rules_out,
                            }
                        )
                    except Exception as update_error:
                        logger.debug(f"Could not update trace output: {update_error}")

                # Log workflow completion (non-critical - wrap in try/except)
                if trace:
                    try:
                        # Detect total-extractor-failure: LangGraph reaches END without
                        # raising even when all subagents error, so final_state carries
                        # no top-level "error" key despite zero extraction.
                        _all_failed, _extractor_failure_reason = _all_extractors_errored(
                            final_state.get("extraction_result")
                        )
                        _top_level_error = final_state.get("error")
                        _success = _top_level_error is None and not _all_failed
                        _completion_result: dict = {
                            "success": _success,
                            "ranking_score": final_state.get("ranking_score"),
                            "sigma_rules_count": len(final_state.get("sigma_rules", [])),
                            "queued_rules_count": len(final_state.get("queued_rules", [])),
                        }
                        if not _success:
                            _completion_result["failure_reason"] = _extractor_failure_reason or str(_top_level_error)
                        log_workflow_step(
                            trace,
                            "workflow_completed",
                            step_result=_completion_result,
                            error=None if _success else Exception(_completion_result["failure_reason"]),
                            metadata={"final_step": final_state.get("current_step")},
                        )
                    except Exception as log_error:
                        logger.debug(f"Could not log workflow step: {log_error}")

                # Mark workflow as completed if it finished successfully
                # This MUST happen before trace cleanup to ensure status is set correctly
                workflow_completed = True
                workflow_error = final_state.get("error")
        except Exception as trace_error:
            trace_err_msg = str(trace_error).lower()
            is_generator_err = "generator" in trace_err_msg and (
                "didn't stop" in trace_err_msg or "throw" in trace_err_msg or "stop after" in trace_err_msg
            )
            # Trace cleanup/operations failed - log but don't fail execution if workflow succeeded
            if workflow_completed and final_state is not None:
                logger.warning(
                    f"Trace cleanup error for execution {execution.id} (workflow completed successfully): {trace_error}"
                )
                # Suppress
            elif is_generator_err:
                logger.warning(
                    f"Trace/Langfuse generator error during workflow execution {execution.id}: {trace_error} "
                    f"(suppressing and treating as completed/no-rules)."
                )
                workflow_completed = True
                workflow_error = None
                if final_state is None:
                    final_state = initial_state
            else:
                # Workflow didn't complete or trace error happened during workflow execution
                logger.error(f"Trace error during workflow execution {execution.id}: {trace_error}")
                if final_state is None:
                    # Workflow crashed before ainvoke completed. Emit an explicit child
                    # span so the Langfuse trace timeline shows a distinguishable
                    # "crashed on startup" signal rather than a silent root-only trace.
                    if trace:
                        with contextlib.suppress(Exception):
                            log_workflow_step(
                                trace,
                                "workflow_crashed",
                                step_result={"success": False},
                                error=trace_error,
                                metadata={"crashed_before": "ainvoke"},
                            )
                    raise
                # Suppress so status update can proceed

        # Ensure execution status matches final state
        # Refresh execution from database to get latest status
        try:
            db_session.refresh(execution)
        except Exception as refresh_error:
            logger.warning(f"Error refreshing execution: {refresh_error}")
            # Rollback and get fresh copy
            with contextlib.suppress(Exception):
                db_session.rollback()

        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution.id)
            .first()
        )

        if execution:
            # Determine final status based on final state
            # Only mark as failed if there's an actual workflow error (not trace cleanup errors)
            has_error = workflow_error is not None

            # Treat infra failures (LMStudio not ready, context overflow) as hard failures
            # even when the workflow graph returned without raising -- subagent errors are
            # swallowed by the ExtractAgent and the graph reports "no error" while every
            # subagent actually returned zero items due to the infra problem.
            if not has_error and _extraction_is_infra_failure(execution.extraction_result if execution else None):
                has_error = True
                workflow_error = (
                    "Extraction failed: all subagents hit an infra error (LMStudio not ready or context overflow)"
                )

            if has_error:
                # Actual error occurred - mark as failed
                if execution.status != "failed":
                    execution.status = "failed"
                    execution.error_message = workflow_error
                    execution.current_step = final_state.get("current_step", "generate_sigma")
                    db_session.commit()
                    logger.warning(f"[Workflow {execution.id}] Marked as 'failed' due to error: {workflow_error}")
                else:
                    # Already failed, just ensure current_step is correct
                    if not execution.current_step or execution.current_step == "promote_to_queue":
                        execution.current_step = final_state.get("current_step", "generate_sigma")
                        db_session.commit()

                # Reconcile any pending Sigma eval rows so an error-in-state
                # completion (finished ainvoke() without raising) does not strand
                # them in 'pending'. The outer `except` covers raised exceptions;
                # this covers has_error completions that return normally.
                mark_pending_sigma_evals_as_failed(execution, db_session)
            elif execution.status == "running":
                # No error - mark as completed (even if stopped by thresholds)
                execution.status = "completed"
                execution.completed_at = datetime.now()
                execution.current_step = final_state.get("current_step", "rank_article")

                db_session.commit()

                # Update SubagentEvaluationTable if this is an eval run
                # Do this AFTER commit to ensure execution.extraction_result is saved
                # Refresh execution to ensure we have the latest extraction_result
                db_session.refresh(execution)
                _update_subagent_eval_on_completion(execution, db_session)
                score_and_persist_execution(execution, db_session)

                logger.info(f"[Workflow {execution.id}] Marked as 'completed' - workflow finished normally")
            elif execution.status == "completed":
                # Execution already marked as completed - still update eval if needed
                # This handles cases where execution was completed elsewhere
                # Refresh execution to ensure we have the latest extraction_result
                db_session.refresh(execution)
                _update_subagent_eval_on_completion(execution, db_session)
                score_and_persist_execution(execution, db_session)
            elif execution.status == "failed":
                # Already marked as failed - ensure current_step is correct
                step_ok = not execution.current_step or execution.current_step == "promote_to_queue"
                if step_ok and final_state:
                    execution.current_step = final_state.get("current_step", "generate_sigma")
                    db_session.commit()
                    logger.info(
                        f"[Workflow {execution.id}] Updated current_step to "
                        f"{execution.current_step} for failed execution"
                    )

        # Build minimal return dict with ONLY JSON-safe primitives
        # NEVER return ArticleTable or any ORM objects - Celery JSON serializer cannot handle SQLAlchemy models
        # Never return final_state - it contains ArticleTable and other ORM objects
        # Extract execution.id as primitive BEFORE any potential serialization issues
        execution_id_primitive = int(execution.id) if execution else None

        return_dict = {
            "success": final_state.get("error") is None if final_state else False,
            "execution_id": execution_id_primitive,
            "error": str(final_state.get("error")) if final_state and final_state.get("error") else None,
            # Only include safe primitive values from final_state
            "ranking_score": float(final_state.get("ranking_score"))
            if final_state and final_state.get("ranking_score") is not None
            else None,
            "discrete_huntables_count": int(final_state.get("discrete_huntables_count"))
            if final_state and final_state.get("discrete_huntables_count") is not None
            else None,
            "sigma_rules_count": int(len(final_state.get("sigma_rules", [])))
            if final_state and final_state.get("sigma_rules")
            else 0,
            "queued_rules_count": int(len(final_state.get("queued_rules", [])))
            if final_state and final_state.get("queued_rules")
            else 0,
        }

        # Final validation: ensure it's JSON serializable

        try:
            # Test serialization - this will catch any ORM objects
            serialized = json.dumps(return_dict)
            # Verify we can deserialize it too
            json.loads(serialized)
        except (TypeError, ValueError) as e:
            logger.error(f"Return value still contains non-serializable objects: {e}")
            logger.error(f"Return dict contents: {return_dict}")
            # Fallback: return absolute minimal safe dict with only primitives
            return {
                "success": False,
                "execution_id": execution_id_primitive,
                "error": "Serialization error: workflow result contained non-serializable objects",
            }

        return return_dict

    except Exception as e:
        # Rollback any failed transaction
        try:
            db_session.rollback()
        except Exception as rollback_error:
            logger.warning(f"Error rolling back transaction: {rollback_error}")

        # Only mark as failed if this is NOT a trace cleanup error for a completed workflow
        # Check if execution exists and has sigma_rules (indicating workflow succeeded)
        if execution:
            # Refresh execution from database to get latest state including sigma_rules
            try:
                db_session.refresh(execution)
            except Exception as refresh_error:
                logger.warning(f"Error refreshing execution: {refresh_error}")
                # Try to get a fresh copy from database
                execution = (
                    db_session.query(AgenticWorkflowExecutionTable)
                    .filter(AgenticWorkflowExecutionTable.id == execution.id)
                    .first()
                )

            # Check if workflow actually completed successfully despite the error
            if execution and execution.sigma_rules and len(execution.sigma_rules) > 0:
                # Workflow succeeded - don't mark as failed
                logger.warning(
                    f"Outer exception handler caught error for execution {execution.id}, "
                    f"but workflow succeeded (generated {len(execution.sigma_rules)} rules). "
                    f"Error: {e}. Not marking as failed."
                )
                # Update status to completed instead
                execution.status = "completed"
                execution.completed_at = datetime.now()
                execution.error_message = None
                db_session.commit()
                # Don't re-raise - workflow succeeded
                # Extract execution.id as primitive to avoid ORM serialization issues
                execution_id_primitive = int(execution.id) if execution else None
                return {"success": True, "execution_id": execution_id_primitive, "error": None}
            # Check for generator errors - these often occur during trace cleanup
            err_msg = str(e).lower()
            if "generator didn't stop" in err_msg or "generator" in err_msg:
                logger.warning(
                    f"Generator error for execution {execution.id}; treating as completed/no-rules. Error: {e}"
                )
                execution.status = "completed"
                execution.completed_at = datetime.now()
                execution.error_message = None
                if not execution.current_step:
                    execution.current_step = "generate_sigma"
                db_session.commit()
                # Extract execution.id as primitive to avoid ORM serialization issues
                execution_id_primitive = int(execution.id) if execution else None
                return {"success": True, "execution_id": execution_id_primitive, "error": None}
            # Real workflow failure - mark as failed
            logger.error(f"Workflow execution error for article {article_id}: {e}")
            execution.status = "failed"
            execution.error_message = str(e)
            db_session.commit()
            # Reconcile any orphaned pending eval records tied to this execution
            # (e.g. failure before extract_agent completed).
            _mark_pending_subagent_evals_as_failed(execution, db_session)
            mark_pending_sigma_evals_as_failed(execution, db_session)
        else:
            # No execution record - this is a real error
            logger.error(f"Workflow execution error for article {article_id}: {e}")

        # Return error result (sanitized) instead of raising to avoid serialization issues
        # Only re-raise if it's not a generator/trace error
        if "generator" not in str(e).lower() and "trace" not in str(e).lower():
            # Never expose raw exception text to API callers
            error_msg = "Internal workflow error"
            # Extract execution.id as primitive to avoid ORM serialization issues
            execution_id_primitive = int(execution.id) if execution else None
            # Return sanitized error result instead of raising
            return {"success": False, "execution_id": execution_id_primitive, "error": error_msg}
        # Generator/trace error - return success with no rules
        # Extract execution.id as primitive to avoid ORM serialization issues
        execution_id_primitive = int(execution.id) if execution else None
        return {"success": True, "execution_id": execution_id_primitive, "error": None}
