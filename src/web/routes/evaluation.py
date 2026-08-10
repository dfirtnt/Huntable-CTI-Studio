"""
Evaluation history, agent metrics, and benchmark result endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(tags=["Evaluation"])


@router.get("/api/eval/os-detection-manual-results")
def api_os_detection_manual_results():
    """Get manual test results for OS Detection model comparison."""
    try:
        import json
        from pathlib import Path

        # Load manual test data from script
        from scripts.eval_os_detection_manual import MANUAL_TEST_DATA, normalize_os_label

        # Try to load evaluation results
        multi_model_eval_path = Path("outputs/evaluations/os_detection_multi_model_eval.json")

        multi_model_results = {}

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
        return {"success": False, "error": "Internal server error", "results": [], "accuracies": {}}


@router.get("/api/eval/observables-count-results")
def api_observables_count_results():
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
        return {"success": False, "error": "Internal server error", "results": [], "model_summaries": {}}


