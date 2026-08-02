"""MCP tools for eval bundle export and diagnosis."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from src.database.async_manager import AsyncDatabaseManager
from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable, SubagentEvaluationTable
from src.services import eval_diagnosis_service
from src.services.eval_bundle_service import EvalBundleService
from src.services.eval_diagnosis_service import EvalDiagnosisService
from src.services.llm_service import LLMService
from src.utils.subagent_utils import build_subagent_lookup_values

logger = logging.getLogger(__name__)

_SUBAGENT_TO_BUNDLE_AGENT = {
    "cmdline": "CmdlineExtract",
    "process_lineage": "ProcTreeExtract",
    "hunt_queries": "HuntQueriesExtract",
    "hunt_queries_edr": "HuntQueriesExtract",
    "registry_artifacts": "RegistryExtract",
    "windows_services": "ServicesExtract",
    "scheduled_tasks": "ScheduledTasksExtract",
    "network_indicators": "NetworkIndicatorExtract",
}

_MAX_BULK_BUNDLES = 100
_CONFIG_VERSION_PATTERN = re.compile(r"^v?(?P<version>\d+)(?P<label>[a-z])?$", re.IGNORECASE)


def _json_response(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _resolve_provider_model(db_session, provider: str | None, model_name: str | None) -> tuple[str, str | None]:
    resolved_provider = provider or "openai"
    resolved_model = model_name if model_name is not None else "gpt-4o"

    try:
        result = db_session.execute(
            select(AppSettingsTable).where(AppSettingsTable.key.in_(["DIAGNOSIS_PROVIDER", "DIAGNOSIS_MODEL"]))
        )
        settings_map = {setting.key: setting.value for setting in result.scalars().all()}
        if provider is None and settings_map.get("DIAGNOSIS_PROVIDER"):
            resolved_provider = settings_map["DIAGNOSIS_PROVIDER"]
        if model_name is None and settings_map.get("DIAGNOSIS_MODEL"):
            resolved_model = settings_map["DIAGNOSIS_MODEL"]
    except Exception as e:
        logger.warning("Could not load diagnosis settings, using MCP defaults: %s", e)

    return resolved_provider, resolved_model


def _load_saved_diagnoses(execution_id: int, agent_name: str | None = None) -> list[dict[str, Any]]:
    diagnoses_dir = eval_diagnosis_service.DIAGNOSES_DIR
    matches = sorted(
        diagnoses_dir.glob(f"{execution_id}_*.json") if diagnoses_dir.exists() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    diagnoses: list[dict[str, Any]] = []
    for path in matches:
        try:
            diagnosis = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Skipping unreadable diagnosis file %s: %s", path, e)
            continue
        if agent_name and diagnosis.get("agent_name") != agent_name:
            continue
        diagnosis.setdefault("_source_file", str(path))
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


def register(mcp: FastMCP, db: AsyncDatabaseManager) -> None:
    """Register eval bundle and diagnosis tools on the MCP server."""
    _ = db

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
    async def diagnose_eval_bundle(
        execution_id: int,
        agent_name: str,
        provider: str | None = None,
        model_name: str | None = None,
        save: bool = True,
        slim: bool = True,
        include_langfuse: bool = True,
    ) -> str:
        """Run the same LLM-powered eval diagnosis used by the web Diagnose button.

        Args:
            execution_id: Workflow execution ID.
            agent_name: Agent name, e.g. CmdlineExtract.
            provider: Optional provider override. If omitted, uses DIAGNOSIS_PROVIDER setting or openai.
            model_name: Optional model override. If omitted, uses DIAGNOSIS_MODEL setting or gpt-4o.
            save: Persist the diagnosis JSON to data/diagnoses for history and UI badges.
            slim: Use a slim eval bundle for diagnosis token efficiency.
            include_langfuse: Fetch Langfuse request/response data when available.
        """
        db_session = _new_sync_session()
        try:
            resolved_provider, resolved_model = _resolve_provider_model(db_session, provider, model_name)
            bundle = EvalBundleService(db_session).generate_bundle(
                execution_id=execution_id,
                agent_name=agent_name,
                fetch_langfuse=include_langfuse,
                slim=slim,
            )
            diagnosis_service = EvalDiagnosisService(LLMService(config_models={}))
            diagnosis = await diagnosis_service.diagnose_bundle(
                bundle=bundle,
                agent_name=agent_name,
                provider=resolved_provider,
                model_name=resolved_model,
            )
            if save:
                path = diagnosis_service.save_diagnosis(diagnosis)
                diagnosis["_saved_path"] = str(path)
            return _json_response(diagnosis)
        except Exception as e:
            logger.error("MCP diagnose_eval_bundle failed for execution %s: %s", execution_id, e, exc_info=True)
            return _json_response({"error": str(e), "execution_id": execution_id, "agent_name": agent_name})
        finally:
            db_session.close()

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
