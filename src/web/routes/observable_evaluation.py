"""
Observable extraction model evaluation API endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.database.manager import DatabaseManager
from src.web.dependencies import logger

router = APIRouter(prefix="/api/observables/evaluation", tags=["Observable Evaluation"])


@router.post("/run")
async def api_run_observable_evaluation(body: dict[str, Any] | None = None):
    """
    Run evaluation for an observable extraction model.

    Request body:
    - model_name: Name of the model (e.g., "CMD")
    - model_version: Version identifier
    - observable_type: Type of observable (e.g., "CMD", "PROC_LINEAGE")
    - usages: List of dataset usages to evaluate (["eval"], ["gold"], or ["eval", "gold"])
    - model_path: Optional path to model (if None, auto-detects)
    - overlap_threshold: Minimum token overlap for eval true positive (default: 0.5)
    """
    body = body or {}
    model_name = body.get("model_name", "CMD")
    model_version = body.get("model_version")
    observable_type = body.get("observable_type", "CMD")
    usages = body.get("usages", ["eval", "gold"])
    model_path = body.get("model_path")
    overlap_threshold = body.get("overlap_threshold", 0.5)

    if not model_version:
        raise HTTPException(status_code=400, detail="model_version is required")

    if observable_type not in ["CMD", "PROC_LINEAGE"]:
        raise HTTPException(status_code=400, detail=f"Unsupported observable_type: {observable_type}")

    if not isinstance(usages, list) or not all(u in ("eval", "gold") for u in usages):
        raise HTTPException(status_code=400, detail="usages must be a list containing 'eval' and/or 'gold'")

    try:
        from src.services.observable_evaluation.pipeline import ObservableEvaluationPipeline

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            pipeline = ObservableEvaluationPipeline(session)
            result = pipeline.run_evaluation(
                model_name=model_name,
                model_version=model_version,
                observable_type=observable_type,
                usages=usages,
                model_path=model_path,
                overlap_threshold=overlap_threshold,
            )

            # Check if any evaluations failed
            evaluations = result.get("evaluations", {})
            has_errors = any(isinstance(metrics, dict) and "error" in metrics for metrics in evaluations.values())

            if has_errors:
                error_messages = [
                    f"{usage}: {metrics.get('error', 'Unknown error')}"
                    for usage, metrics in evaluations.items()
                    if isinstance(metrics, dict) and "error" in metrics
                ]
                raise HTTPException(status_code=400, detail=f"Evaluation failed: {'; '.join(error_messages)}")

            return {
                "success": True,
                "result": result,
            }
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Observable evaluation error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics")
async def api_get_observable_metrics(
    model_name: str | None = None,
    model_version: str | None = None,
    observable_type: str | None = None,
    usage: str | None = None,
    limit: int = 100,
):
    """
    Retrieve observable model metrics from the database.

    Query parameters:
    - model_name: Filter by model name
    - model_version: Filter by model version
    - observable_type: Filter by observable type
    - usage: Filter by dataset usage ("eval" or "gold")
    - limit: Maximum number of results (default: 100)
    """
    try:
        from src.services.observable_evaluation.pipeline import ObservableEvaluationPipeline

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            pipeline = ObservableEvaluationPipeline(session)
            metrics = pipeline.get_metrics(
                model_name=model_name,
                model_version=model_version,
                observable_type=observable_type,
                usage=usage,
                limit=limit,
            )

            return {
                "success": True,
                "metrics": metrics,
                "count": len(metrics),
            }
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Error retrieving observable metrics: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/aggregated")
async def api_get_aggregated_metrics(
    model_name: str | None = None,
    model_version: str | None = None,
    observable_type: str | None = None,
):
    """
    Get aggregated metrics grouped by model version and usage.

    Returns metrics organized by version and dataset usage (eval/gold).
    """
    try:
        from src.services.observable_evaluation.pipeline import ObservableEvaluationPipeline

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            pipeline = ObservableEvaluationPipeline(session)
            all_metrics = pipeline.get_metrics(
                model_name=model_name,
                model_version=model_version,
                observable_type=observable_type,
                limit=1000,  # Get more for aggregation
            )

            # Group by model_version and usage
            aggregated: dict[str, dict[str, dict[str, Any]]] = {}

            for metric in all_metrics:
                version = metric["model_version"]
                usage = metric["dataset_usage"]
                metric_name = metric["metric_name"]
                metric_value = metric["metric_value"]

                if version not in aggregated:
                    aggregated[version] = {"eval": {}, "gold": {}}

                # Store as float for numeric metrics, preserve integers for counts
                if isinstance(metric_value, (int, float)):
                    aggregated[version][usage][metric_name] = float(metric_value)
                else:
                    aggregated[version][usage][metric_name] = metric_value

            return {
                "success": True,
                "aggregated": aggregated,
            }
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Error aggregating observable metrics: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/failures")
async def api_get_evaluation_failures(
    model_name: str | None = None,
    model_version: str | None = None,
    observable_type: str | None = None,
    failure_type: str | None = None,
    limit: int = 100,
):
    """
    Get failure taxonomy for inspection.

    Returns failure records grouped by failure type, showing which articles
    had which types of failures.
    """
    try:
        from src.database.models import ObservableEvaluationFailureTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            from sqlalchemy import select

            query = select(ObservableEvaluationFailureTable)

            if model_name:
                query = query.where(ObservableEvaluationFailureTable.model_name == model_name)
            if model_version:
                query = query.where(ObservableEvaluationFailureTable.model_version == model_version)
            if observable_type:
                query = query.where(ObservableEvaluationFailureTable.observable_type == observable_type)
            if failure_type:
                query = query.where(ObservableEvaluationFailureTable.failure_type == failure_type)

            query = query.order_by(ObservableEvaluationFailureTable.computed_at.desc()).limit(limit)

            results = session.execute(query).scalars().all()

            # Group by failure type
            failures_by_type = defaultdict(list)
            for r in results:
                failures_by_type[r.failure_type].append(
                    {
                        "article_id": r.article_id,
                        "failure_count": r.failure_count,
                        "zero_fp_pass": r.zero_fp_pass,
                        "total_predictions": r.total_predictions,
                        "total_gold_spans": r.total_gold_spans,
                        "computed_at": r.computed_at.isoformat() if r.computed_at else None,
                    }
                )

            return {
                "success": True,
                "failures_by_type": dict(failures_by_type),
                "total_failures": len(results),
            }
        finally:
            session.close()

    except Exception as exc:
        logger.error(f"Error retrieving failure taxonomy: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
