"""MCP tools for eval bundle export and diagnosis."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from src.database.async_manager import AsyncDatabaseManager
from src.database.manager import DatabaseManager
from src.database.models import SubagentEvaluationTable
from src.huntable_mcp.tools.write_support import MCP_SERVICE_ACTOR, record_mcp_audit
from src.services import eval_diagnosis_service
from src.services.audit_service import (
    ACTION_EVAL_BUNDLE_DIAGNOSED,
    ACTION_EVAL_RUN_REQUESTED,
    STATUS_ATTEMPTED,
    STATUS_FAILURE,
    STATUS_SUCCESS,
)
from src.services.eval_bundle_service import EvalBundleService
from src.services.eval_diagnosis_service import (
    DiagnosisValidationError,
    EvalDiagnosisService,
    compute_diagnosis_evidence_sha256,
)
from src.services.subagent_eval_launch_service import (
    MAX_EVAL_EXECUTIONS_ENV,
    MAX_REPLICATES,
    MAX_THROTTLE_SECONDS,
    EvalDispatchError,
    EvalLaunchError,
    EvalLaunchPlan,
    NoActiveConfigError,
    ensure_broker_reachable,
    launch_subagent_eval,
    plan_subagent_eval,
)
from src.utils.subagent_utils import (
    SUBAGENT_TO_EXTRACT_AGENT,
    build_subagent_lookup_values,
    normalize_subagent_name,
)

logger = logging.getLogger(__name__)

# Bundle/eval agent names keyed by subagent alias; hunt_queries_edr is a legacy
# alias of the HuntQueries extractor that still appears in stored eval rows.
_SUBAGENT_TO_BUNDLE_AGENT = {**SUBAGENT_TO_EXTRACT_AGENT, "hunt_queries_edr": "HuntQueriesExtract"}

_MAX_BULK_BUNDLES = 100
_CONFIG_VERSION_PATTERN = re.compile(r"^v?(?P<version>\d+)(?P<label>[a-z])?$", re.IGNORECASE)


def _json_response(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _load_saved_diagnoses(execution_id: int, agent_name: str | None = None) -> list[dict[str, Any]]:
    """Saved diagnoses newest-first, tagged with their bare filename (never a host path)."""
    diagnoses: list[dict[str, Any]] = []
    for path, diagnosis in eval_diagnosis_service.load_saved_diagnoses(execution_id, agent_name=agent_name):
        diagnosis.setdefault("_source_file", path.name)
        diagnoses.append(diagnosis)
    return diagnoses


def _resolve_subagent_query(subagent: str) -> tuple[str, list[str]]:
    canonical, lookup_values = build_subagent_lookup_values(subagent)
    if not lookup_values:
        normalized_raw = str(subagent).strip()
        lookup_values = {normalized_raw} if normalized_raw else {subagent}
    canonical_value = canonical or (next(iter(lookup_values)) if lookup_values else subagent)
    return canonical_value, list(lookup_values)


def _parse_config_version(config_version: int | str) -> tuple[int, str, int | None]:
    """Resolve a version and optional replicate letter (``v5114a`` => run 0)."""
    if isinstance(config_version, bool):
        raise ValueError("config_version must be an integer or a label such as v5114a")
    if isinstance(config_version, int):
        if config_version < 1:
            raise ValueError("config_version must be at least 1")
        return config_version, str(config_version), None

    raw = str(config_version).strip()
    match = _CONFIG_VERSION_PATTERN.fullmatch(raw)
    if not match:
        raise ValueError("config_version must be an integer or a label such as v5114a")
    version = int(match.group("version"))
    if version < 1:
        raise ValueError("config_version must be at least 1")
    label = match.group("label")
    return version, raw, (ord(label.lower()) - ord("a") if label else None)


def _bundle_selection(subagent: str | None) -> tuple[str | None, set[str], str | None]:
    """Return canonical alias, DB lookup values, and bundle agent for a selector."""
    if subagent is None:
        aliases = set(_SUBAGENT_TO_BUNDLE_AGENT)
        lookup_values = set()
        for alias in aliases:
            _, values = _resolve_subagent_query(alias)
            lookup_values.update(values)
        lookup_values.add("hunt_queries_edr")
        return None, lookup_values, None

    canonical, lookup_values = _resolve_subagent_query(subagent)
    lookup_set = set(lookup_values)
    if canonical == "hunt_queries":
        lookup_set.add("hunt_queries_edr")
    agent_name = _SUBAGENT_TO_BUNDLE_AGENT.get(canonical)
    return canonical, lookup_set, agent_name


def _new_sync_session():
    db_manager = DatabaseManager()
    return db_manager.get_session()


def _validate_launch_args(
    subagent: str,
    article_urls: list[str] | None,
    replicates: int,
    concurrency_throttle_seconds: float,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return (canonical_subagent, None) or (None, error payload) without touching the DB."""
    canonical = normalize_subagent_name(subagent)
    if canonical not in SUBAGENT_TO_EXTRACT_AGENT:
        return None, {
            "error": f"Unsupported subagent for eval launch: {subagent}",
            "supported_subagents": list(SUBAGENT_TO_EXTRACT_AGENT),
        }
    if isinstance(replicates, bool) or not isinstance(replicates, int) or not 1 <= replicates <= MAX_REPLICATES:
        return None, {"error": f"replicates must be an integer between 1 and {MAX_REPLICATES}"}
    if (
        isinstance(concurrency_throttle_seconds, bool)
        or not isinstance(concurrency_throttle_seconds, (int, float))
        or not 0 <= concurrency_throttle_seconds <= MAX_THROTTLE_SECONDS
    ):
        return None, {"error": f"concurrency_throttle_seconds must be between 0 and {MAX_THROTTLE_SECONDS:g}"}
    if article_urls is not None and (
        not isinstance(article_urls, list)
        or not article_urls
        or not all(isinstance(url, str) and url.strip() for url in article_urls)
    ):
        return None, {"error": "article_urls must be omitted (full committed set) or a non-empty list of URL strings"}
    return canonical, None


def _eval_status_summary(records: list[Any]) -> dict[str, Any]:
    """Progress and metrics for a cohort, using the same formula as the HTTP status route."""
    total = len(records)
    completed = sum(1 for r in records if r.status == "completed")
    failed = sum(1 for r in records if r.status == "failed")
    pending = sum(1 for r in records if r.status == "pending")
    completed_records = [r for r in records if r.status == "completed" and r.score is not None]
    if completed_records:
        perfect_matches = sum(1 for r in completed_records if r.score == 0)
        accuracy: float | None = perfect_matches / len(completed_records)
        mean_score: float | None = sum(r.score for r in completed_records) / len(completed_records)
    else:
        perfect_matches = 0
        accuracy = None
        mean_score = None
    return {
        "progress": {"completed": completed, "failed": failed, "pending": pending, "total": total},
        "metrics": {"accuracy": accuracy, "mean_score": mean_score, "perfect_matches": perfect_matches},
        "is_complete": total > 0 and pending == 0,
    }


def _select_replicate(records: list[Any], run_index: int) -> list[Any]:
    """Keep the nth row per (article, subagent), the same grouping get_eval_run uses."""
    grouped: dict[tuple[int | None, str], list[Any]] = {}
    for record in records:
        grouped.setdefault((record.article_id, record.subagent_name), []).append(record)
    return [group[run_index] for group in grouped.values() if len(group) > run_index]


def _billing_line(plan: EvalLaunchPlan) -> str:
    if plan.is_local_provider:
        return f"Provider {plan.provider} is local; this run bills no tokens."
    return (
        f"Tokens WILL be billed to provider {plan.provider or 'unknown'} "
        f"(model {plan.model or 'unknown'}) for {plan.total_executions} extractor run(s)."
    )


def _launch_plan_payload(plan: EvalLaunchPlan) -> dict[str, Any]:
    return {**plan.to_dict(), "billing": _billing_line(plan)}


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register eval bundle and diagnosis tools on the MCP server."""

    @mcp.tool()
    async def get_eval_bundle(
        execution_id: int,
        agent_name: str,
        attempt: int | None = None,
        slim: bool = False,
        include_langfuse: bool = True,
        inline_large_text: bool = False,
        max_inline_chars: int = 200000,
    ) -> str:
        """Return a full eval_bundle_v1 JSON bundle for a workflow execution.

        Args:
            execution_id: Workflow execution ID.
            agent_name: Agent name, e.g. CmdlineExtract, ProcTreeExtract, rank_article, generate_sigma.
            attempt: Optional 1-indexed attempt number. If omitted, uses the most relevant/latest attempt.
            slim: Strip bulky duplicate fields. Defaults false so MCP callers can retrieve the full bundle.
            include_langfuse: Fetch Langfuse request/response data when available.
            inline_large_text: Inline large article/prompt text fields.
            max_inline_chars: Maximum characters to inline before truncating article text.
        """
        db_session = _new_sync_session()
        try:
            bundle = EvalBundleService(db_session).generate_bundle(
                execution_id=execution_id,
                agent_name=agent_name,
                attempt=attempt,
                inline_large_text=inline_large_text,
                max_inline_chars=max_inline_chars,
                fetch_langfuse=include_langfuse,
                slim=slim,
            )
            return _json_response(bundle)
        except Exception as e:
            logger.error("MCP get_eval_bundle failed for execution %s: %s", execution_id, e, exc_info=True)
            return _json_response({"error": str(e), "execution_id": execution_id, "agent_name": agent_name})
        finally:
            db_session.close()

    @mcp.tool()
    async def get_eval_diagnosis_context(
        execution_id: int,
        agent_name: str,
        slim: bool = True,
        include_langfuse: bool = True,
    ) -> str:
        """Return the evidence packet for diagnosing one eval run.

        Read-only. No LLM is called server-side and no provider API key is used:
        the packet bundles the eval bundle, the extractor standard, the agent
        contract, scoring context, and the diagnosis instructions/schema so the
        calling agent does the reasoning. Persist the result with
        save_eval_diagnosis.

        Args:
            execution_id: Workflow execution ID.
            agent_name: Agent name, e.g. CmdlineExtract.
            slim: Use a slim eval bundle to keep the packet within MCP result limits.
            include_langfuse: Fetch Langfuse request/response data when available.
        """
        db_session = _new_sync_session()
        try:
            bundle = EvalBundleService(db_session).generate_bundle(
                execution_id=execution_id,
                agent_name=agent_name,
                fetch_langfuse=include_langfuse,
                slim=slim,
            )
            context = EvalDiagnosisService().build_context(bundle=bundle, agent_name=agent_name)
            return _json_response(context)
        except Exception as e:
            logger.error("MCP get_eval_diagnosis_context failed for execution %s: %s", execution_id, e, exc_info=True)
            return _json_response({"error": str(e), "execution_id": execution_id, "agent_name": agent_name})
        finally:
            db_session.close()

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def save_eval_diagnosis(
        execution_id: int,
        agent_name: str,
        diagnosis: dict[str, Any] | str,
        evidence_sha256: str,
        authored_by: str | None = None,
        confirmed_by_user: bool = False,
        slim: bool = True,
        include_langfuse: bool = True,
    ) -> str:
        """Persist an agent-authored eval diagnosis to data/diagnoses.

        Caller-attested write. The caller must obtain explicit user approval
        for this single save and pass confirmed_by_user=true. The server cannot
        independently prove the human interaction. The tool validates
        the diagnosis against the schema returned by get_eval_diagnosis_context,
        verifies that evidence_sha256 still matches the reviewed context packet,
        writes one JSON file, and audits attempted plus terminal persistence
        states. Validation errors require fresh confirmation before retrying.

        Args:
            execution_id: Workflow execution ID the diagnosis applies to.
            agent_name: Agent name, e.g. CmdlineExtract.
            diagnosis: Diagnosis JSON object (or JSON string) matching the schema.
            evidence_sha256: Digest returned by get_eval_diagnosis_context for the reviewed packet.
            authored_by: Optional label for the agent/model that authored it.
            confirmed_by_user: True only after explicit approval for this save call.
            slim: Must match the context-packet retrieval option.
            include_langfuse: Must match the context-packet retrieval option.
        """
        if not confirmed_by_user:
            return _json_response(
                {
                    "saved": False,
                    "confirmation_required": True,
                    "execution_id": execution_id,
                    "agent_name": agent_name,
                    "message": (
                        "Explicit user confirmation is required before saving this diagnosis. "
                        "After approval, retry once with confirmed_by_user=true."
                    ),
                }
            )

        if isinstance(diagnosis, str):
            try:
                diagnosis = json.loads(diagnosis)
            except json.JSONDecodeError as e:
                return _json_response({"error": f"diagnosis is not valid JSON: {e}", "execution_id": execution_id})

        db_session = _new_sync_session()
        try:
            bundle = EvalBundleService(db_session).generate_bundle(
                execution_id=execution_id,
                agent_name=agent_name,
                fetch_langfuse=include_langfuse,
                slim=slim,
            )
        except Exception as e:
            logger.error("save_eval_diagnosis could not load eval bundle: %s", e, exc_info=True)
            return _json_response(
                {
                    "error": f"could not load eval bundle; diagnosis was not saved: {e}",
                    "execution_id": execution_id,
                    "agent_name": agent_name,
                }
            )
        finally:
            db_session.close()

        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha256 or ""):
            return _json_response(
                {
                    "error": "evidence_sha256 must be the 64-character digest from get_eval_diagnosis_context",
                    "execution_id": execution_id,
                    "agent_name": agent_name,
                    "saved": False,
                }
            )
        current_evidence_sha256 = compute_diagnosis_evidence_sha256(bundle, agent_name)
        if evidence_sha256 != current_evidence_sha256:
            return _json_response(
                {
                    "error": "Diagnosis context is stale or does not match this execution and agent",
                    "execution_id": execution_id,
                    "agent_name": agent_name,
                    "saved": False,
                    "context_refresh_required": True,
                    "current_evidence_sha256": current_evidence_sha256,
                }
            )

        diagnosis_service = EvalDiagnosisService()
        try:
            normalized = diagnosis_service.normalize(
                diagnosis,
                agent_name=agent_name,
                execution_id=execution_id,
                bundle=bundle,
                evidence_sha256=evidence_sha256,
                authored_by=authored_by,
            )
        except DiagnosisValidationError as e:
            return _json_response(
                {
                    "error": f"Invalid diagnosis: {e}",
                    "execution_id": execution_id,
                    "agent_name": agent_name,
                    "hint": "Fix the field and call save_eval_diagnosis again. Nothing was written.",
                }
            )

        pending_path: Path | None = None
        final_path: Path | None = None
        path: Path | None = None
        attempted_audit_committed = False
        published = False
        diagnosis_sha256 = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        audit_metadata = {
            "execution_id": execution_id,
            "agent_name": agent_name,
            "diagnosis_id": normalized["diagnosis_id"],
            "diagnosis_sha256": diagnosis_sha256,
            "evidence_sha256": evidence_sha256,
            "failure_category": normalized["failure_category"],
            "source": normalized["source"],
            "authored_by": normalized["authored_by"],
            "confirmation_attested_by_caller": True,
        }
        try:
            pending_path, final_path = diagnosis_service.prepare_diagnosis_file(normalized)
            async with db.get_session() as session:
                await record_mcp_audit(
                    session,
                    ACTION_EVAL_BUNDLE_DIAGNOSED,
                    "workflow_execution",
                    execution_id,
                    f"Preparing approved agent diagnosis for execution {execution_id} ({agent_name})",
                    {**audit_metadata, "storage_state": "prepared"},
                    status=STATUS_ATTEMPTED,
                )
                await session.commit()
            attempted_audit_committed = True
            path = diagnosis_service.publish_diagnosis_file(pending_path, final_path)
            pending_path = None
            published = True
            async with db.get_session() as session:
                await record_mcp_audit(
                    session,
                    ACTION_EVAL_BUNDLE_DIAGNOSED,
                    "workflow_execution",
                    execution_id,
                    f"Saved agent diagnosis for execution {execution_id} ({agent_name})",
                    {**audit_metadata, "storage_state": "published", "path": str(path)},
                    status=STATUS_SUCCESS,
                )
                await session.commit()
        except Exception as e:
            logger.error("MCP save_eval_diagnosis failed for execution %s: %s", execution_id, e, exc_info=True)
            cleanup_error = None
            if pending_path is not None:
                try:
                    pending_path.unlink(missing_ok=True)
                except OSError as cleanup_exception:
                    cleanup_error = str(cleanup_exception)
                    logger.critical("Could not remove pending diagnosis file %s: %s", pending_path, cleanup_exception)
            if published and path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError as cleanup_exception:
                    cleanup_error = str(cleanup_exception)
                    logger.critical(
                        "Could not remove incompletely audited diagnosis file %s: %s", path, cleanup_exception
                    )
            failure_audit_error = None
            if attempted_audit_committed:
                try:
                    async with db.get_session() as session:
                        await record_mcp_audit(
                            session,
                            ACTION_EVAL_BUNDLE_DIAGNOSED,
                            "workflow_execution",
                            execution_id,
                            f"Failed to finalize agent diagnosis for execution {execution_id} ({agent_name})",
                            {**audit_metadata, "storage_state": "failed", "error_type": type(e).__name__},
                            status=STATUS_FAILURE,
                        )
                        await session.commit()
                except Exception as audit_exception:
                    failure_audit_error = str(audit_exception)
                    logger.critical("Could not audit diagnosis finalization failure: %s", audit_exception)
            payload = {"error": str(e), "execution_id": execution_id, "agent_name": agent_name, "saved": False}
            if cleanup_error:
                payload["cleanup_error"] = cleanup_error
                payload["orphaned_path"] = str(pending_path)
            if failure_audit_error:
                payload["failure_audit_error"] = failure_audit_error
            return _json_response(payload)

        return _json_response(
            {
                "saved": True,
                "path": str(path),
                "diagnosis": normalized,
            }
        )

    @mcp.tool()
    async def list_eval_diagnoses(execution_id: int, agent_name: str | None = None) -> str:
        """Return saved diagnosis runs for an execution, newest first."""
        diagnoses = _load_saved_diagnoses(execution_id, agent_name=agent_name)
        return _json_response(
            {
                "execution_id": execution_id,
                "agent_name": agent_name,
                "count": len(diagnoses),
                "diagnoses": diagnoses,
            }
        )

    @mcp.tool()
    async def export_diagnosed_eval_bundles(
        config_version: int,
        subagent: str,
        slim: bool = False,
        include_langfuse: bool = False,
        max_bundles: int = 20,
    ) -> str:
        """Return eval bundles for completed runs that already have saved diagnoses.

        Args:
            config_version: Workflow config version to export.
            subagent: Subagent alias, e.g. cmdline, process_lineage, network_indicators.
            slim: Strip bulky duplicate fields. Defaults false for full bundles.
            include_langfuse: Fetch Langfuse request/response data when available.
            max_bundles: Maximum bundle records to include; hard-capped at 100.
        """
        if max_bundles < 1:
            return _json_response({"error": "max_bundles must be at least 1"})
        capped_max = min(max_bundles, _MAX_BULK_BUNDLES)

        db_session = _new_sync_session()
        try:
            canonical_subagent, lookup_values = _resolve_subagent_query(subagent)
            if canonical_subagent == "hunt_queries":
                lookup_values = sorted(set(lookup_values) | {"hunt_queries_edr"})
            agent_name = _SUBAGENT_TO_BUNDLE_AGENT.get(canonical_subagent)
            if not agent_name:
                return _json_response({"error": f"Unsupported subagent for bundle export: {subagent}"})

            records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.subagent_name.in_(lookup_values),
                    SubagentEvaluationTable.workflow_config_version == config_version,
                    SubagentEvaluationTable.workflow_execution_id.isnot(None),
                    SubagentEvaluationTable.status == "completed",
                )
                .order_by(SubagentEvaluationTable.article_id.asc(), SubagentEvaluationTable.id.asc())
                .all()
            )

            bundle_service = EvalBundleService(db_session)
            exported = []
            skipped = []
            diagnosed_records = 0

            for record in records:
                execution_id = record.workflow_execution_id
                diagnoses = _load_saved_diagnoses(execution_id, agent_name=agent_name)
                if not diagnoses:
                    continue
                diagnosed_records += 1
                if len(exported) >= capped_max:
                    skipped.append(
                        {
                            "record_id": record.id,
                            "execution_id": execution_id,
                            "reason": f"max_bundles={capped_max} reached",
                        }
                    )
                    continue
                try:
                    bundle = bundle_service.generate_bundle(
                        execution_id=execution_id,
                        agent_name=agent_name,
                        attempt=None,
                        fetch_langfuse=include_langfuse,
                        slim=slim,
                    )
                    exported.append(
                        {
                            "record_id": record.id,
                            "article_id": record.article_id,
                            "execution_id": execution_id,
                            "agent_name": agent_name,
                            "diagnosis_count": len(diagnoses),
                            "diagnoses": diagnoses,
                            "bundle": bundle,
                        }
                    )
                except Exception as e:
                    logger.warning("Skipping diagnosed bundle for execution %s: %s", execution_id, e)
                    skipped.append(
                        {
                            "record_id": record.id,
                            "execution_id": execution_id,
                            "reason": str(e),
                        }
                    )

            return _json_response(
                {
                    "schema_version": "mcp_diagnosed_eval_bundles_v1",
                    "config_version": config_version,
                    "subagent": canonical_subagent,
                    "agent_name": agent_name,
                    "slim": slim,
                    "include_langfuse": include_langfuse,
                    "diagnosed_records": diagnosed_records,
                    "exported_count": len(exported),
                    "skipped_count": len(skipped),
                    "max_bundles": capped_max,
                    "items": exported,
                    "skipped": skipped,
                    "note": "MCP returns JSON instead of the web UI ZIP download.",
                }
            )
        except Exception as e:
            logger.error("MCP export_diagnosed_eval_bundles failed: %s", e, exc_info=True)
            return _json_response({"error": str(e), "config_version": config_version, "subagent": subagent})
        finally:
            db_session.close()

    @mcp.tool()
    async def get_eval_bundles_by_config(
        config_version: int | str,
        subagent: str | None = None,
        slim: bool = False,
        include_langfuse: bool = False,
        max_bundles: int = 100,
    ) -> str:
        """Return completed eval bundles for a config run, optionally filtered by subagent.

        config_version accepts an integer or an operator label such as ``v5114a``;
        the numeric portion is matched against subagent_evaluations.workflow_config_version.
        Without subagent, all supported extractor evals are included. Results are JSON,
        not a ZIP, and max_bundles prevents an unexpectedly large MCP response.
        """
        if max_bundles < 1:
            return _json_response({"error": "max_bundles must be at least 1"})
        capped_max = min(max_bundles, _MAX_BULK_BUNDLES)
        try:
            resolved_version, selector, run_index = _parse_config_version(config_version)
        except ValueError as e:
            return _json_response({"error": str(e), "config_version": config_version})

        db_session = _new_sync_session()
        try:
            canonical_subagent, lookup_values, selected_agent = _bundle_selection(subagent)
            if subagent is not None and not selected_agent:
                return _json_response({"error": f"Unsupported subagent for bundle export: {subagent}"})

            query = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.workflow_config_version == resolved_version,
                SubagentEvaluationTable.workflow_execution_id.isnot(None),
                SubagentEvaluationTable.status == "completed",
            )
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            records = query.order_by(
                SubagentEvaluationTable.article_id.asc(),
                SubagentEvaluationTable.subagent_name.asc(),
                SubagentEvaluationTable.created_at.asc(),
                SubagentEvaluationTable.id.asc(),
            ).all()
            if run_index is not None:
                grouped: dict[tuple[int | None, str], list[Any]] = {}
                for record in records:
                    grouped.setdefault((record.article_id, record.subagent_name), []).append(record)
                records = [group[run_index] for group in grouped.values() if len(group) > run_index]

            bundle_service = EvalBundleService(db_session)
            items: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for record in records:
                if len(items) >= capped_max:
                    skipped.append({"record_id": record.id, "reason": f"max_bundles={capped_max} reached"})
                    continue
                agent_name = selected_agent or _SUBAGENT_TO_BUNDLE_AGENT.get(
                    _resolve_subagent_query(record.subagent_name)[0]
                )
                if not agent_name:
                    skipped.append({"record_id": record.id, "reason": "unsupported bundle agent"})
                    continue
                try:
                    items.append(
                        {
                            "record_id": record.id,
                            "article_id": record.article_id,
                            "execution_id": record.workflow_execution_id,
                            "subagent": _resolve_subagent_query(record.subagent_name)[0],
                            "agent_name": agent_name,
                            "bundle": bundle_service.generate_bundle(
                                execution_id=record.workflow_execution_id,
                                agent_name=agent_name,
                                attempt=None,
                                fetch_langfuse=include_langfuse,
                                slim=slim,
                            ),
                        }
                    )
                except (ValueError, AttributeError) as e:
                    skipped.append(
                        {"record_id": record.id, "execution_id": record.workflow_execution_id, "reason": str(e)}
                    )

            return _json_response(
                {
                    "schema_version": "mcp_eval_bundles_by_config_v1",
                    "config_version": resolved_version,
                    "config_selector": selector,
                    "run_index": run_index,
                    "subagent": canonical_subagent,
                    "agent_name": selected_agent,
                    "slim": slim,
                    "include_langfuse": include_langfuse,
                    "matched_records": len(records),
                    "exported_count": len(items),
                    "skipped_count": len(skipped),
                    "max_bundles": capped_max,
                    "items": items,
                    "skipped": skipped,
                }
            )
        except Exception as e:
            logger.error("MCP get_eval_bundles_by_config failed for %s: %s", config_version, e, exc_info=True)
            return _json_response({"error": str(e), "config_version": config_version})
        finally:
            db_session.close()

    @mcp.tool()
    async def get_article_eval_bundle(
        article_id: int,
        subagent: str | None = None,
        config_version: int | str | None = None,
        slim: bool = False,
        include_langfuse: bool = False,
        include_trace: bool = False,
    ) -> str:
        """Return eval bundle(s) for one article, with the workflow trace when requested."""
        try:
            resolved_version = None
            selector = None
            run_index = None
            if config_version is not None:
                resolved_version, selector, run_index = _parse_config_version(config_version)
        except ValueError as e:
            return _json_response({"error": str(e), "config_version": config_version})

        db_session = _new_sync_session()
        try:
            canonical_subagent, lookup_values, selected_agent = _bundle_selection(subagent)
            if subagent is not None and not selected_agent:
                return _json_response({"error": f"Unsupported subagent for bundle export: {subagent}"})

            query = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.article_id == article_id,
                SubagentEvaluationTable.workflow_execution_id.isnot(None),
                SubagentEvaluationTable.status == "completed",
            )
            if resolved_version is not None:
                query = query.filter(SubagentEvaluationTable.workflow_config_version == resolved_version)
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            records = query.order_by(
                SubagentEvaluationTable.created_at.asc(),
                SubagentEvaluationTable.id.asc(),
            ).all()
            if run_index is not None:
                records_by_subagent: dict[str, list[Any]] = {}
                for record in records:
                    records_by_subagent.setdefault(record.subagent_name, []).append(record)
                records = [group[run_index] for group in records_by_subagent.values() if len(group) > run_index]
            if not records:
                return _json_response({"error": "No completed eval records found", "article_id": article_id})

            bundle_service = EvalBundleService(db_session)
            items = []
            for record in records:
                agent_name = selected_agent or _SUBAGENT_TO_BUNDLE_AGENT.get(
                    _resolve_subagent_query(record.subagent_name)[0]
                )
                if not agent_name:
                    continue
                item: dict[str, Any] = {
                    "record_id": record.id,
                    "article_id": record.article_id,
                    "execution_id": record.workflow_execution_id,
                    "config_version": record.workflow_config_version,
                    "subagent": _resolve_subagent_query(record.subagent_name)[0],
                    "agent_name": agent_name,
                    "bundle": bundle_service.generate_bundle(
                        execution_id=record.workflow_execution_id,
                        agent_name=agent_name,
                        attempt=None,
                        fetch_langfuse=include_langfuse,
                        slim=slim,
                    ),
                }
                if include_trace:
                    from src.web.routes.workflow_executions import _build_workflow_trace_bundle

                    item["trace"] = _build_workflow_trace_bundle(
                        db_session=db_session,
                        execution_id=record.workflow_execution_id,
                        include_eval_bundles=True,
                        fetch_langfuse=include_langfuse,
                        slim=slim,
                    )
                items.append(item)

            return _json_response(
                {
                    "schema_version": "mcp_article_eval_bundle_v1",
                    "article_id": article_id,
                    "config_version": resolved_version,
                    "config_selector": selector,
                    "run_index": run_index,
                    "subagent": canonical_subagent,
                    "include_trace": include_trace,
                    "count": len(items),
                    "items": items,
                }
            )
        except Exception as e:
            logger.error("MCP get_article_eval_bundle failed for article %s: %s", article_id, e, exc_info=True)
            return _json_response({"error": str(e), "article_id": article_id})
        finally:
            db_session.close()

    @mcp.tool()
    async def get_workflow_execution_trace(
        execution_id: int,
        include_eval_bundles: bool = False,
        slim: bool = True,
        include_langfuse: bool = False,
    ) -> str:
        """Return the workflow_execution_trace_v1 for one execution.

        Eval bundles are excluded by default because combining a full trace and
        eval bundle can exceed common MCP result-size limits. Use get_eval_bundle
        separately for the agent-specific bundle.
        """
        db_session = _new_sync_session()
        try:
            from src.web.routes.workflow_executions import _build_workflow_trace_bundle

            trace = _build_workflow_trace_bundle(
                db_session=db_session,
                execution_id=execution_id,
                include_eval_bundles=include_eval_bundles,
                fetch_langfuse=include_langfuse,
                slim=slim,
            )
            return _json_response(trace)
        except Exception as e:
            logger.error("MCP get_workflow_execution_trace failed for %s: %s", execution_id, e, exc_info=True)
            return _json_response({"error": str(e), "execution_id": execution_id})
        finally:
            db_session.close()

    @mcp.tool()
    async def get_eval_run(
        run: str,
        article_id: int | None = None,
        subagent: str | None = None,
    ) -> str:
        """Convenience entry point for eval retrieval with safe defaults.

        Pass a run label such as ``v5139a``. Optionally pass article_id and/or
        subagent. This is the recommended entry point for the
        huntable-eval-retrieval skill. It uses slim bundles, excludes Langfuse,
        and caps a config-wide response at three bundles to stay below MCP
        result limits. For a trace, use the execution_id from the result with
        get_workflow_execution_trace.
        """
        if article_id is None:
            return await get_eval_bundles_by_config(
                config_version=run,
                subagent=subagent,
                slim=True,
                include_langfuse=False,
                max_bundles=3,
            )
        return await get_article_eval_bundle(
            article_id=article_id,
            subagent=subagent,
            config_version=run,
            slim=True,
            include_langfuse=False,
            include_trace=False,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    async def run_subagent_eval(
        subagent: str,
        article_urls: list[str] | None = None,
        replicates: int = 1,
        concurrency_throttle_seconds: float = 5.0,
        confirmed_by_user: bool = False,
    ) -> str:
        """Plan, then launch, a subagent eval run against the active workflow config.

        Caller-attested write that spends provider tokens. Call it first with
        confirmed_by_user=false: it returns the plan (config version, provider,
        model, execution count, per-URL status, billing line) and writes
        nothing. Show that plan to the user, obtain explicit approval for this
        launch, then call again with confirmed_by_user=true. Approval never
        carries over: every launch call needs its own confirmed_by_user=true.
        Tokens are billed to the extractor's configured provider unless it is
        lmstudio.

        URLs with a committed fixture but no DB article row are reported as
        skipped, never run inside the MCP server. After a launch, poll
        get_subagent_eval_status with the returned run_label, then retrieve
        bundles with get_eval_run.

        Args:
            subagent: Canonical alias (cmdline, process_lineage, hunt_queries,
                registry_artifacts, windows_services, scheduled_tasks,
                network_indicators) or the extractor name. The hunt_queries_edr
                and hunt_queries_sigma variants are rejected.
            article_urls: URLs to run, duplicates allowed. Omit for the full
                committed set from config/eval_articles.yaml.
            replicates: Runs per URL, 1..50, expanded server-side.
            concurrency_throttle_seconds: Extra spacing between dispatches, 0..60.
            confirmed_by_user: True only after explicit approval for this launch call.
        """
        canonical, invalid = _validate_launch_args(subagent, article_urls, replicates, concurrency_throttle_seconds)
        if invalid is not None:
            return _json_response({**invalid, "launched": False})
        assert canonical is not None

        db_session = _new_sync_session()
        try:
            try:
                plan = plan_subagent_eval(
                    db_session,
                    canonical,
                    article_urls=article_urls,
                    replicates=replicates,
                    allow_inline_execution=False,
                )
            except NoActiveConfigError as e:
                return _json_response({"error": str(e), "launched": False})
            except EvalLaunchError as e:
                return _json_response({"error": str(e), "launched": False})

            plan_payload = _launch_plan_payload(plan)
            if plan.total_executions == 0:
                return _json_response(
                    {
                        **plan_payload,
                        "launched": False,
                        "error": (
                            "Nothing to run: no planned URL has both a committed fixture and a DB article row. "
                            "See rows[].status."
                        ),
                    }
                )
            if plan.exceeds_cap:
                return _json_response(
                    {
                        **plan_payload,
                        "launched": False,
                        "error": (
                            f"Requested {plan.total_executions} eval executions; "
                            f"{MAX_EVAL_EXECUTIONS_ENV}={plan.max_executions} caps a single launch"
                        ),
                    }
                )
            if not confirmed_by_user:
                return _json_response(
                    {
                        **plan_payload,
                        "launched": False,
                        "confirmation_required": True,
                        "message": (
                            "Explicit user confirmation is required before launching this eval run. "
                            f"{_billing_line(plan)} "
                            "Show the plan to the user; after approval, retry once with confirmed_by_user=true."
                        ),
                    }
                )

            try:
                ensure_broker_reachable()
            except EvalDispatchError as e:
                return _json_response({**plan_payload, "launched": False, "error": str(e)})

            try:
                result = await launch_subagent_eval(
                    db_session,
                    plan,
                    concurrency_throttle_seconds=float(concurrency_throttle_seconds),
                    initiated_by=MCP_SERVICE_ACTOR,
                )
            except EvalDispatchError as e:
                logger.error("MCP run_subagent_eval dispatch failed for %s: %s", canonical, e, exc_info=True)
                return _json_response({**plan_payload, "launched": False, "rows_committed": True, "error": str(e)})
            except EvalLaunchError as e:
                return _json_response({**plan_payload, "launched": False, "error": str(e)})
        finally:
            db_session.close()

        audit_metadata = {**result.audit_metadata(), "confirmation_attested_by_caller": True}
        audit_error: str | None = None
        try:
            async with db.get_session() as session:
                await record_mcp_audit(
                    session,
                    ACTION_EVAL_RUN_REQUESTED,
                    "evaluation",
                    plan.subagent,
                    f"Launched {result.total_executions} subagent eval executions for {plan.subagent} "
                    f"({plan.run_label}) via MCP",
                    audit_metadata,
                )
                await session.commit()
        except Exception as e:
            audit_error = str(e)
            logger.critical("Could not audit MCP eval launch for %s (%s): %s", canonical, plan.run_label, e)

        payload: dict[str, Any] = {
            **plan_payload,
            **result.to_dict(),
            "launched": True,
            "confirmation_attested_by_caller": True,
            "next_steps": (
                f"Poll get_subagent_eval_status(run='{plan.run_label}', subagent='{plan.subagent}') until every "
                f"execution completes, then call get_eval_run(run='{plan.run_label}', subagent='{plan.subagent}')."
            ),
        }
        if audit_error:
            payload["audit_error"] = audit_error
        return _json_response(payload)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    async def get_subagent_eval_status(run: str, subagent: str | None = None) -> str:
        """Cheap progress poll for an eval run, keyed by run label.

        Accepts the same labels as get_eval_run (``5139``, ``v5139``, ``v5139a``)
        and returns pending, completed and failed counts plus accuracy and mean
        score for the (config version, subagent) cohort, the same numbers as
        GET /api/evaluations/subagent-eval-status without needing an eval
        record id. A lettered label narrows the cohort to that replicate
        (``a`` is the first run per article). Without subagent, every
        extractor's rows for the version are aggregated and a per-subagent
        breakdown is included. Poll this after run_subagent_eval until
        is_complete, then call get_eval_run for bundles. Read-only.

        Args:
            run: Run label or config version, e.g. v5139 or v5139a.
            subagent: Optional subagent alias, e.g. cmdline. Omit to aggregate all extractors.
        """
        try:
            resolved_version, selector, run_index = _parse_config_version(run)
        except ValueError as e:
            return _json_response({"error": str(e), "run": run})

        canonical_subagent, lookup_values, selected_agent = _bundle_selection(subagent)
        if subagent is not None and not selected_agent:
            return _json_response({"error": f"Unsupported subagent for eval status: {subagent}", "run": run})

        db_session = _new_sync_session()
        try:
            query = db_session.query(SubagentEvaluationTable).filter(
                SubagentEvaluationTable.workflow_config_version == resolved_version
            )
            if lookup_values:
                query = query.filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            records = query.order_by(
                SubagentEvaluationTable.article_id.asc(),
                SubagentEvaluationTable.subagent_name.asc(),
                SubagentEvaluationTable.created_at.asc(),
                SubagentEvaluationTable.id.asc(),
            ).all()
            if run_index is not None:
                records = _select_replicate(records, run_index)

            payload: dict[str, Any] = {
                "schema_version": "mcp_subagent_eval_status_v1",
                "run": selector,
                "config_version": resolved_version,
                "run_index": run_index,
                "subagent": canonical_subagent,
                "agent_name": selected_agent,
                **_eval_status_summary(records),
            }
            if canonical_subagent is None:
                by_subagent: dict[str, list[Any]] = {}
                for record in records:
                    by_subagent.setdefault(_resolve_subagent_query(record.subagent_name)[0], []).append(record)
                payload["per_subagent"] = {
                    name: _eval_status_summary(rows) for name, rows in sorted(by_subagent.items())
                }
            if not records:
                payload["message"] = (
                    f"No eval records for {selector}"
                    + (f" ({canonical_subagent})" if canonical_subagent else "")
                    + ". Check the run label, or launch with run_subagent_eval."
                )
            elif payload["is_complete"]:
                payload["next_steps"] = (
                    f"Run complete. Retrieve bundles with get_eval_run(run='{selector}'"
                    + (f", subagent='{canonical_subagent}'" if canonical_subagent else "")
                    + ")."
                )
            return _json_response(payload)
        except Exception as e:
            logger.error("MCP get_subagent_eval_status failed for %s: %s", run, e, exc_info=True)
            return _json_response({"error": str(e), "run": run})
        finally:
            db_session.close()
