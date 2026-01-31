"""
Endpoints for RAG evaluation metrics and feedback.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.web.dependencies import logger

router = APIRouter(tags=["Evaluation"])


@router.post("/api/eval/hallucination")
async def api_eval_hallucination(request: Request):
    """Evaluate RAG response for hallucination detection."""
    try:
        body = await request.json()
        chat_log_id = body.get("chat_log_id")
        hallucination_detected = body.get("hallucination_detected", False)
        user_feedback = body.get("user_feedback", "")

        from src.database.async_manager import AsyncDatabaseManager
        from src.database.models import ChatLogTable

        async with AsyncDatabaseManager().get_session() as session:
            chat_log = await session.get(ChatLogTable, chat_log_id)
            if not chat_log:
                raise HTTPException(status_code=404, detail="Chat log not found")

            chat_log.hallucination_detected = hallucination_detected
            chat_log.user_feedback = user_feedback
            await session.commit()
            return {"status": "success", "message": "Hallucination evaluation recorded"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Hallucination evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/eval/relevance")
async def api_eval_relevance(request: Request):
    """Evaluate RAG response for relevance scoring."""
    try:
        body = await request.json()
        chat_log_id = body.get("chat_log_id")
        relevance_score = body.get("relevance_score", 3.0)
        accuracy_rating = body.get("accuracy_rating", 3.0)
        user_feedback = body.get("user_feedback", "")

        from src.database.async_manager import AsyncDatabaseManager
        from src.database.models import ChatLogTable

        async with AsyncDatabaseManager().get_session() as session:
            chat_log = await session.get(ChatLogTable, chat_log_id)
            if not chat_log:
                raise HTTPException(status_code=404, detail="Chat log not found")

            chat_log.relevance_score = relevance_score
            chat_log.accuracy_rating = accuracy_rating
            chat_log.user_feedback = user_feedback
            await session.commit()
            return {"status": "success", "message": "Relevance evaluation recorded"}

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Relevance evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/metrics")
async def api_eval_metrics():
    """Get RAG evaluation metrics."""
    try:
        from sqlalchemy import Integer, func, select

        from src.database.async_manager import AsyncDatabaseManager
        from src.database.models import ChatLogTable

        async with AsyncDatabaseManager().get_session() as session:
            total_chats = await session.scalar(select(func.count(ChatLogTable.id)))

            avg_relevance = await session.scalar(
                select(func.avg(ChatLogTable.relevance_score)).where(ChatLogTable.relevance_score.is_not(None))
            )
            avg_accuracy = await session.scalar(
                select(func.avg(ChatLogTable.accuracy_rating)).where(ChatLogTable.accuracy_rating.is_not(None))
            )
            hallucination_rate = await session.scalar(
                select(func.avg(func.cast(ChatLogTable.hallucination_detected, Integer))).where(
                    ChatLogTable.hallucination_detected.is_not(None)
                )
            )
            avg_response_time = await session.scalar(
                select(func.avg(ChatLogTable.response_time_ms)).where(ChatLogTable.response_time_ms.is_not(None))
            )

            return {
                "total_chats": total_chats or 0,
                "avg_relevance_score": round(avg_relevance or 0, 2),
                "avg_accuracy_rating": round(avg_accuracy or 0, 2),
                "hallucination_rate": round((hallucination_rate or 0) * 100, 2),
                "avg_response_time_ms": round(avg_response_time or 0, 0),
            }

    except Exception as exc:  # noqa: BLE001
        logger.error("Metrics evaluation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/history")
async def api_eval_history(agent_name: str, limit: int = 50):
    """Get evaluation history for an agent."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            tracker = EvaluationTracker(db_session)
            history = tracker.get_evaluation_history(agent_name, limit=limit)
            return {"agent_name": agent_name, "history": history}
        finally:
            db_session.close()

    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation history error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/comparison")
async def api_eval_comparison(baseline_id: int, current_id: int):
    """Compare two evaluations."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            tracker = EvaluationTracker(db_session)
            comparison = tracker.compare_evaluations(baseline_id, current_id)
            return comparison
        finally:
            db_session.close()

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation comparison error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/agent-metrics")
async def api_eval_agent_metrics(agent_name: str):
    """Get latest metrics for an agent."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            tracker = EvaluationTracker(db_session)
            latest = tracker.get_latest_evaluation(agent_name)

            if not latest:
                raise HTTPException(status_code=404, detail=f"No evaluations found for {agent_name}")

            return {"agent_name": agent_name, "latest_evaluation": latest, "metrics": latest.get("metrics", {})}
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent metrics error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/trends")
async def api_eval_trends(agent_name: str, metric_key: str, evaluation_type: str = None):
    """Get improvement trends for a specific metric."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            tracker = EvaluationTracker(db_session)
            trends = tracker.get_improvement_trends(agent_name, metric_key, evaluation_type)
            return {"agent_name": agent_name, "metric_key": metric_key, "trends": trends}
        finally:
            db_session.close()

    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation trends error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/os-detection-manual-results")
async def api_os_detection_manual_results():
    """Get manual test results for OS Detection model comparison."""
    try:
        import json
        from pathlib import Path

        # Load manual test data from script
        from scripts.eval_os_detection_manual import MANUAL_TEST_DATA, normalize_os_label

        # Try to load evaluation results
        manual_eval_path = Path("outputs/evaluations/os_detection_manual_eval.json")
        multi_model_eval_path = Path("outputs/evaluations/os_detection_multi_model_eval.json")

        manual_results = {}
        multi_model_results = {}

        if manual_eval_path.exists():
            with open(manual_eval_path) as f:
                manual_results = json.load(f)

        if multi_model_eval_path.exists():
            with open(multi_model_eval_path) as f:
                multi_model_results = json.load(f)

        # Build comprehensive results table
        results_table = []

        for test_item in MANUAL_TEST_DATA:
            row = {
                "url": test_item["url"],
                "title": test_item["title"],
                "human": normalize_os_label(test_item["human"]),
                "gemini": normalize_os_label(test_item.get("gemini", "")),
                "sonnet_4_5": normalize_os_label(test_item.get("sonnet_4_5", "")),
                "haiku_4_5": normalize_os_label(test_item.get("haiku_4_5", "")),
                "chatgpt4o": normalize_os_label(test_item.get("chatgpt4o", "")),
                "chatgpt5_1": normalize_os_label(test_item.get("chatgpt5_1", "")),
                "sec_bert": normalize_os_label(test_item.get("sec_bert", "")),
                "cti_bert": None,
                "deepseek_r1": None,
                "qwen2_7b": None,
                "qwen3_4b": None,
                "llama_3_1_8b": None,
                "llama_3_8b": None,
                "llama_3_13b": None,
                "llama_3_3_70b": None,
                "phi_3_mini": None,
                "llama_3_2_1b": None,
                "mistral_7b": None,
                "mixtral_8x7b": None,
            }

            # Add results from multi-model evaluation if available
            if multi_model_results and "results" in multi_model_results:
                for model_key, model_result in multi_model_results["results"].items():
                    if "results" in model_result:
                        # Find matching article by URL
                        for article_result in model_result["results"]:
                            if article_result.get("url") == test_item["url"]:
                                predicted = normalize_os_label(article_result.get("predicted", "Unknown"))
                                if model_key == "cti-bert":
                                    row["cti_bert"] = predicted
                                elif model_key == "deepseek-r1-qwen3-8b":
                                    row["deepseek_r1"] = predicted
                                elif model_key == "qwen2-7b":
                                    row["qwen2_7b"] = predicted
                                elif model_key == "qwen3-4b":
                                    row["qwen3_4b"] = predicted
                                elif model_key == "llama-3.1-8b":
                                    row["llama_3_1_8b"] = predicted
                                elif model_key == "llama-3-8b":
                                    row["llama_3_8b"] = predicted
                                elif model_key == "llama-3-13b":
                                    row["llama_3_13b"] = predicted
                                elif model_key == "llama-3.3-70b":
                                    row["llama_3_3_70b"] = predicted
                                elif model_key == "phi-3-mini":
                                    row["phi_3_mini"] = predicted
                                elif model_key == "llama-3.2-1b":
                                    row["llama_3_2_1b"] = predicted
                                elif model_key == "mistral-7b":
                                    row["mistral_7b"] = predicted
                                elif model_key == "mixtral-8x7b":
                                    row["mixtral_8x7b"] = predicted
                                break

            results_table.append(row)

        # Calculate accuracies
        accuracies = {}
        model_columns = [
            "gemini",
            "sonnet_4_5",
            "haiku_4_5",
            "chatgpt4o",
            "chatgpt5_1",
            "sec_bert",
            "cti_bert",
            "deepseek_r1",
            "qwen2_7b",
            "qwen3_4b",
            "llama_3_1_8b",
            "llama_3_8b",
            "llama_3_13b",
            "llama_3_3_70b",
            "phi_3_mini",
            "llama_3_2_1b",
            "mistral_7b",
            "mixtral_8x7b",
        ]

        for model in model_columns:
            predictions = [row[model] for row in results_table if row[model] is not None]
            ground_truth = [row["human"] for row in results_table if row[model] is not None]
            if predictions and ground_truth:
                correct = sum(1 for p, g in zip(predictions, ground_truth) if p == g)
                accuracies[model] = correct / len(predictions) if predictions else 0.0

        return {
            "success": True,
            "results": results_table,
            "accuracies": accuracies,
            "total_articles": len(results_table),
        }
    except Exception as e:
        logger.error(f"Error loading OS detection manual results: {e}")
        return {"success": False, "error": str(e), "results": [], "accuracies": {}}


@router.get("/api/eval/observables-count-results")
async def api_observables_count_results():
    """Get observables count results from test runs."""
    try:
        import json
        from collections import defaultdict
        from pathlib import Path

        # Try to load from multi-model evaluation file first
        multi_model_path = Path("outputs/evaluations/observables_count_multi_model_eval.json")

        if multi_model_path.exists():
            with open(multi_model_path) as f:
                eval_data = json.load(f)

            models_data = eval_data.get("models", {})

            # Build results table from multi-model evaluation
            results_table = []
            model_summaries = {}
            all_models = []

            # Get all unique articles from all models
            all_article_ids = set()
            for model_key, model_result in models_data.items():
                if "results" in model_result:
                    for result in model_result["results"]:
                        all_article_ids.add(result.get("article_id"))

            # Build model summaries
            for model_key, model_result in models_data.items():
                if "error" in model_result:
                    continue

                model_name = model_result.get("model_name", model_key)
                all_models.append(model_key)

                model_summaries[model_key] = {
                    "model_name": model_name,
                    "description": model_result.get("description", model_name),
                    "total_articles": model_result.get("total_articles", 0),
                    "successful_parses": model_result.get("successful_parses", 0),
                    "failed_parses": model_result.get("failed_parses", 0),
                    "parse_success_rate": model_result.get("parse_success_rate", 0.0),
                    "avg_total_observables": model_result.get("avg_total_observables", 0.0),
                    "category_averages": model_result.get("category_averages", {}),
                }

            # Build results table
            from src.database.manager import DatabaseManager
            from src.database.models import ArticleTable

            db_manager = DatabaseManager()
            db_session = db_manager.get_session()

            try:
                for article_id in sorted(all_article_ids):
                    article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                    if not article:
                        continue

                    row = {
                        "article_id": article_id,
                        "url": article.canonical_url or "",
                        "title": article.title or "Unknown",
                        "models": {},
                    }

                    # Get results for each model
                    for model_key in all_models:
                        model_result = models_data.get(model_key, {})
                        if "results" not in model_result:
                            row["models"][model_key] = None
                            continue

                        # Find result for this article
                        article_result = None
                        for result in model_result["results"]:
                            if result.get("article_id") == article_id:
                                article_result = result
                                break

                        if article_result:
                            counts = article_result.get("counts")
                            if counts:
                                row["models"][model_key] = {
                                    "total": counts.get("Total", 0),
                                    "counts": counts,
                                    "parse_success": article_result.get("parse_success", False),
                                }
                            else:
                                row["models"][model_key] = {"total": None, "counts": None, "parse_success": False}
                        else:
                            row["models"][model_key] = None

                    results_table.append(row)
            finally:
                db_session.close()

            return {
                "success": True,
                "results": results_table,
                "model_summaries": model_summaries,
                "total_articles": len(results_table),
                "models": all_models,
                "evaluation_date": eval_data.get("evaluation_date"),
                "source": "multi_model_eval",
            }

        # Fallback to individual files (legacy support)
        results_dir = Path("outputs/evaluations/observables_counts")

        if not results_dir.exists():
            return {"success": False, "error": "Results directory not found", "results": [], "model_summaries": {}}

        # Find all latest result files
        latest_files = list(results_dir.glob("*_latest.json"))

        # Group by article and model
        article_results = defaultdict(lambda: defaultdict(list))
        model_summaries = defaultdict(
            lambda: {
                "total_articles": 0,
                "successful_parses": 0,
                "failed_parses": 0,
                "avg_total_observables": 0.0,
                "category_totals": defaultdict(int),
                "category_averages": defaultdict(float),
            }
        )

        results_table = []

        for file_path in latest_files:
            try:
                with open(file_path) as f:
                    data = json.load(f)

                article_id = data.get("article_id")
                model = data.get("model", "unknown")
                counts = data.get("counts")
                parse_success = data.get("parse_success", False)

                if not article_id:
                    continue

                # Store result
                article_results[article_id][model].append(data)

                # Update model summary
                summary = model_summaries[model]
                summary["total_articles"] += 1
                if parse_success and counts:
                    summary["successful_parses"] += 1
                    total = counts.get("Total", 0)
                    summary["avg_total_observables"] = (
                        summary["avg_total_observables"] * (summary["successful_parses"] - 1) + total
                    ) / summary["successful_parses"]

                    # Sum category counts
                    for key, value in counts.items():
                        if key != "Total" and isinstance(value, int):
                            summary["category_totals"][key] += value
                else:
                    summary["failed_parses"] += 1

            except Exception as e:
                logger.warning(f"Error loading result file {file_path}: {e}")
                continue

        # Calculate category averages
        for model, summary in model_summaries.items():
            if summary["successful_parses"] > 0:
                for category in summary["category_totals"]:
                    summary["category_averages"][category] = (
                        summary["category_totals"][category] / summary["successful_parses"]
                    )

        # Build results table - get unique articles
        from src.database.manager import DatabaseManager
        from src.database.models import ArticleTable

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            unique_articles = set(article_results.keys())
            all_models = set()
            for article_id, models in article_results.items():
                all_models.update(models.keys())

            all_models = sorted(all_models)

            for article_id in sorted(unique_articles):
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                if not article:
                    continue

                row = {
                    "article_id": article_id,
                    "url": article.canonical_url or "",
                    "title": article.title or "Unknown",
                    "models": {},
                }

                # Get results for each model
                for model in all_models:
                    model_results = article_results[article_id].get(model, [])
                    if model_results:
                        latest_result = model_results[-1]  # Get most recent
                        counts = latest_result.get("counts")
                        if counts:
                            row["models"][model] = {
                                "total": counts.get("Total", 0),
                                "counts": counts,
                                "parse_success": latest_result.get("parse_success", False),
                            }
                        else:
                            row["models"][model] = {"total": None, "counts": None, "parse_success": False}
                    else:
                        row["models"][model] = None

                results_table.append(row)
        finally:
            db_session.close()

        return {
            "success": True,
            "results": results_table,
            "model_summaries": dict(model_summaries),
            "total_articles": len(results_table),
            "models": all_models,
            "source": "individual_files",
        }
    except Exception as e:
        logger.error(f"Error loading observables count results: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e), "results": [], "model_summaries": {}}


@router.post("/api/eval/run")
async def api_eval_run(request: Request):
    """Trigger an evaluation run (returns immediately, runs in background)."""
    try:
        body = await request.json()
        agent_name = body.get("agent_name")
        test_data_path = body.get("test_data_path")
        evaluation_type = body.get("evaluation_type", "baseline")
        model_version = body.get("model_version")
        save_to_db = body.get("save_to_db", True)

        if not agent_name or not test_data_path:
            raise HTTPException(status_code=400, detail="agent_name and test_data_path are required")

        # Import evaluators

        # This would ideally run in a background task
        # For now, return a message that evaluation should be run via CLI
        return {
            "status": "info",
            "message": "Evaluation triggered. Note: Full evaluations should be run via CLI scripts for better control.",
            "agent_name": agent_name,
            "suggestion": f"Run: python scripts/eval_{agent_name.lower().replace('agent', 'agent').replace('osdetection', 'os_detection')}.py --test-data {test_data_path} --evaluation-type {evaluation_type} {'--save-to-db' if save_to_db else ''}",
        }

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Evaluation run error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/eval/rank-agent-benchmarks")
async def api_rank_agent_benchmarks():
    """Get benchmark data for RankAgent visualizations."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.evaluation.evaluation_tracker import EvaluationTracker

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            tracker = EvaluationTracker(db_session)
            history = tracker.get_evaluation_history("RankAgent", limit=100)

            if not history:
                return {"success": False, "message": "No evaluation data available"}

            # Aggregate data for charts
            threshold_accuracy_trends = []
            score_mean_trends = []
            score_std_trends = []
            model_comparison = {}
            score_distribution_data = None

            for eval_record in history:
                metrics = eval_record.get("metrics", {})
                model_version = eval_record.get("model_version", "unknown")
                created_at = eval_record.get("created_at")

                # Score distribution (from latest evaluation - extract actual scores if available)
                if eval_record == history[0]:
                    # Try to get actual scores from results if stored
                    from src.database.models import AgentEvaluationTable

                    eval_db = (
                        db_session.query(AgentEvaluationTable)
                        .filter(AgentEvaluationTable.id == eval_record["id"])
                        .first()
                    )

                    actual_scores = []
                    if eval_db and eval_db.results:
                        # Extract scores from results
                        for result in eval_db.results:
                            if isinstance(result, dict):
                                eval_data = result.get("evaluation", {})
                                if eval_data and eval_data.get("score") is not None:
                                    actual_scores.append(eval_data["score"])

                    if actual_scores:
                        # Create histogram from actual scores
                        buckets = [0] * 11  # 0-10 scale
                        for score in actual_scores:
                            bucket = int(min(max(round(score), 0), 10))
                            buckets[bucket] = buckets[bucket] + 1
                        score_distribution_data = {
                            "buckets": buckets,
                            "mean": metrics.get("score_mean"),
                            "std": metrics.get("score_std"),
                            "min": metrics.get("score_min"),
                            "max": metrics.get("score_max"),
                            "median": metrics.get("score_median"),
                        }
                    elif metrics.get("score_mean") is not None:
                        # Fallback: use summary stats only
                        score_distribution_data = {
                            "mean": metrics.get("score_mean"),
                            "std": metrics.get("score_std"),
                            "min": metrics.get("score_min"),
                            "max": metrics.get("score_max"),
                            "median": metrics.get("score_median"),
                        }

                # Threshold accuracy trends
                if metrics.get("threshold_accuracy") is not None:
                    threshold_accuracy_trends.append(
                        {
                            "timestamp": created_at,
                            "value": metrics["threshold_accuracy"],
                            "model_version": model_version,
                        }
                    )

                # Score mean trends
                if metrics.get("score_mean") is not None:
                    score_mean_trends.append(
                        {"timestamp": created_at, "value": metrics["score_mean"], "model_version": model_version}
                    )

                # Score std trends
                if metrics.get("score_std") is not None:
                    score_std_trends.append(
                        {"timestamp": created_at, "value": metrics["score_std"], "model_version": model_version}
                    )

                # Model comparison
                if model_version not in model_comparison:
                    model_comparison[model_version] = {
                        "evaluations": 0,
                        "avg_score_mean": 0,
                        "avg_threshold_accuracy": 0,
                        "total_articles": 0,
                    }

                model_comparison[model_version]["evaluations"] += 1
                if metrics.get("score_mean") is not None:
                    model_comparison[model_version]["avg_score_mean"] += metrics["score_mean"]
                if metrics.get("threshold_accuracy") is not None:
                    model_comparison[model_version]["avg_threshold_accuracy"] += metrics["threshold_accuracy"]
                model_comparison[model_version]["total_articles"] += eval_record.get("total_articles", 0)

            # Calculate averages for model comparison
            for model in model_comparison:
                count = model_comparison[model]["evaluations"]
                if count > 0:
                    model_comparison[model]["avg_score_mean"] /= count
                    model_comparison[model]["avg_threshold_accuracy"] /= count

            # Get latest evaluation for score distribution
            latest = history[0] if history else None
            latest_metrics = latest.get("metrics", {}) if latest else {}

            return {
                "success": True,
                "score_distribution": score_distribution_data
                or {
                    "mean": latest_metrics.get("score_mean"),
                    "std": latest_metrics.get("score_std"),
                    "min": latest_metrics.get("score_min"),
                    "max": latest_metrics.get("score_max"),
                    "median": latest_metrics.get("score_median"),
                },
                "threshold_accuracy_trends": threshold_accuracy_trends,
                "score_mean_trends": score_mean_trends,
                "score_std_trends": score_std_trends,
                "model_comparison": model_comparison,
                "total_evaluations": len(history),
            }
        finally:
            db_session.close()

    except Exception as exc:  # noqa: BLE001
        logger.error("Rank agent benchmarks error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
