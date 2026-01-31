"""
Model management endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(prefix="/api/model", tags=["Model"])


@router.get("/retrain-status")
async def api_model_retrain_status():
    """Get current retraining status."""
    try:
        import os

        status_file = "outputs/training_data/retrain_status.json"

        if os.path.exists(status_file):
            import json

            with open(status_file) as f:
                status_data = json.load(f)

            # If retraining is complete, include model version info and evaluation metrics
            if status_data.get("status") == "complete":
                try:
                    from src.database.async_manager import AsyncDatabaseManager
                    from src.utils.model_versioning import MLModelVersionManager

                    # We're already in an async context, so just await directly
                    db_manager = AsyncDatabaseManager()
                    version_manager = MLModelVersionManager(db_manager)
                    latest_version = await version_manager.get_latest_version()
                    await db_manager.close()
                    if latest_version:
                        status_data.update(
                            {
                                "new_version": latest_version.version_number,
                                "training_accuracy": latest_version.accuracy,
                                "training_duration": f"{latest_version.training_duration_seconds:.1f}s"
                                if latest_version.training_duration_seconds
                                else "Unknown",
                                "training_samples": latest_version.training_data_size,
                            }
                        )

                        # Include evaluation metrics if available (evaluated_at set by save_evaluation_metrics)
                        cm = (
                            latest_version.eval_confusion_matrix
                            if isinstance(latest_version.eval_confusion_matrix, dict)
                            else None
                        )
                        if latest_version.evaluated_at is not None:
                            total_chunks = None
                            misclassified = None
                            if cm:
                                tp = cm.get("true_positive") or 0
                                tn = cm.get("true_negative") or 0
                                fp = cm.get("false_positive") or 0
                                fn = cm.get("false_negative") or 0
                                total_chunks = tp + tn + fp + fn
                                misclassified = fp + fn
                            status_data["evaluation_metrics"] = {
                                "accuracy": latest_version.eval_accuracy,
                                "precision_huntable": latest_version.eval_precision_huntable,
                                "precision_not_huntable": latest_version.eval_precision_not_huntable,
                                "recall_huntable": latest_version.eval_recall_huntable,
                                "recall_not_huntable": latest_version.eval_recall_not_huntable,
                                "f1_score_huntable": latest_version.eval_f1_score_huntable,
                                "f1_score_not_huntable": latest_version.eval_f1_score_not_huntable,
                                "total_eval_chunks": total_chunks,
                                "misclassified_count": misclassified,
                                "confusion_matrix": cm,
                            }
                except Exception as e:
                    logger.warning(f"Could not get latest model version: {e}")

            return status_data
        return {"status": "idle", "progress": 0, "message": "No retraining in progress"}

    except Exception as e:
        logger.error(f"Error getting retrain status: {e}")
        return {"status": "error", "progress": 0, "message": f"Error: {str(e)}"}


@router.post("/retrain")
async def api_model_retrain():
    """Trigger model retraining using collected user feedback."""
    try:
        import json
        import os
        import subprocess
        import threading

        # Check if we have feedback or annotations available for retraining
        async with async_db_manager.get_session() as session:
            from sqlalchemy import text

            # Check for unused feedback
            feedback_query = text("""
            SELECT COUNT(*) as feedback_count
            FROM chunk_classification_feedback
            WHERE used_for_training = FALSE
            """)

            result = await session.execute(feedback_query)
            feedback_count = result.scalar() or 0

            # Check for unused annotations
            annotation_query = text("""
            SELECT COUNT(*) as annotation_count
            FROM article_annotations
            WHERE LENGTH(selected_text) >= 950
            AND LENGTH(selected_text) <= 1050
            AND used_for_training = FALSE
            """)

            result = await session.execute(annotation_query)
            annotation_count = result.scalar() or 0

        total_available = feedback_count + annotation_count

        if total_available == 0:
            return {"success": False, "message": "No feedback or annotations available for retraining"}

        # Run the retraining script
        retrain_script = "scripts/retrain_with_feedback.py"
        if not os.path.exists(retrain_script):
            return {"success": False, "message": "Retraining script not found"}

        # Create status file
        status_file = "outputs/training_data/retrain_status.json"
        os.makedirs(os.path.dirname(status_file), exist_ok=True)

        def update_status(status, progress, message, data=None):
            status_data = {"status": status, "progress": progress, "message": message}
            if data:
                status_data.update(data)
            with open(status_file, "w") as f:
                json.dump(status_data, f)

        # Start with initial status
        update_status(
            "starting",
            10,
            f"Starting retraining process with {total_available} training samples...",
            {
                "training_samples": total_available,
                "feedback_count": feedback_count,
                "annotation_count": annotation_count,
            },
        )

        def run_retrain():
            try:
                update_status("loading", 20, "Loading training data...")

                # Execute retraining script
                result = subprocess.run(
                    ["python3", retrain_script, "--verbose"], capture_output=True, text=True, timeout=300
                )

                if result.returncode == 0:
                    # Get the latest model version after successful retraining
                    try:
                        from src.database.async_manager import AsyncDatabaseManager
                        from src.utils.async_tools import run_sync
                        from src.utils.model_versioning import MLModelVersionManager

                        # run_retrain() is called from a thread, so we need to use run_sync
                        async def get_latest_version():
                            db_manager = AsyncDatabaseManager()
                            version_manager = MLModelVersionManager(db_manager)
                            latest_version = await version_manager.get_latest_version()
                            await db_manager.close()
                            return latest_version

                        latest_version = run_sync(get_latest_version(), allow_running_loop=False)

                        if latest_version:
                            # Return detailed metrics for the frontend
                            retrain_data = {
                                "new_version": latest_version.version_number,
                                "training_accuracy": latest_version.accuracy or 0.0,
                                "validation_accuracy": latest_version.accuracy or 0.0,  # Using accuracy as validation
                                "training_duration": f"{latest_version.training_duration_seconds:.1f}s"
                                if latest_version.training_duration_seconds
                                else "Unknown",
                                "training_samples": total_available,  # Use the count we calculated earlier
                                "feedback_samples": feedback_count,
                                "annotation_samples": annotation_count,
                            }
                            update_status(
                                "complete",
                                100,
                                f"Retraining completed successfully! New model: v{latest_version.version_number}",
                                retrain_data,
                            )
                        else:
                            update_status(
                                "complete",
                                100,
                                "Retraining completed successfully",
                                {
                                    "training_samples": total_available,
                                    "feedback_samples": feedback_count,
                                    "annotation_samples": annotation_count,
                                },
                            )
                    except Exception as e:
                        logger.warning(f"Could not get latest model version: {e}")
                        update_status(
                            "complete",
                            100,
                            "Retraining completed successfully",
                            {
                                "training_samples": total_available,
                                "feedback_samples": feedback_count,
                                "annotation_samples": annotation_count,
                            },
                        )
                else:
                    update_status("error", 0, f"Retraining failed: {result.stderr}")

            except Exception as e:
                update_status("error", 0, f"Retraining error: {str(e)}")
            finally:
                # Clean up status file after 30 seconds
                import time

                time.sleep(30)
                if os.path.exists(status_file):
                    os.remove(status_file)

        # Start retraining in background thread to avoid blocking the web server
        retrain_thread = threading.Thread(target=run_retrain)
        retrain_thread.daemon = True
        retrain_thread.start()

        # Return immediately with status
        return {
            "success": True,
            "message": f"Retraining started with {total_available} training samples",
            "status": "started",
            "training_samples": total_available,
            "feedback_samples": feedback_count,
            "annotation_samples": annotation_count,
        }

    except Exception as e:
        logger.error(f"Error starting retraining: {e}")
        return {"success": False, "message": f"Failed to start retraining: {str(e)}"}


@router.get("/versions")
async def api_get_model_versions():
    """Get all ML model versions with metrics."""
    try:
        from src.utils.model_versioning import MLModelVersionManager

        version_manager = MLModelVersionManager(async_db_manager)
        versions = await version_manager.get_all_versions(limit=50)

        # Convert to serializable format
        versions_data = []
        for version in versions:
            versions_data.append(
                {
                    "id": version.id,
                    "version_number": version.version_number,
                    "trained_at": version.trained_at.isoformat(),
                    "accuracy": version.accuracy,
                    "precision_huntable": version.precision_huntable,
                    "precision_not_huntable": version.precision_not_huntable,
                    "recall_huntable": version.recall_huntable,
                    "recall_not_huntable": version.recall_not_huntable,
                    "f1_score_huntable": version.f1_score_huntable,
                    "f1_score_not_huntable": version.f1_score_not_huntable,
                    "training_data_size": version.training_data_size,
                    "feedback_samples_count": version.feedback_samples_count,
                    "training_duration_seconds": version.training_duration_seconds,
                    "has_comparison": version.comparison_results is not None,
                    # Evaluation metrics
                    "eval_accuracy": version.eval_accuracy,
                    "eval_precision_huntable": version.eval_precision_huntable,
                    "eval_precision_not_huntable": version.eval_precision_not_huntable,
                    "eval_recall_huntable": version.eval_recall_huntable,
                    "eval_recall_not_huntable": version.eval_recall_not_huntable,
                    "eval_f1_score_huntable": version.eval_f1_score_huntable,
                    "eval_f1_score_not_huntable": version.eval_f1_score_not_huntable,
                    "eval_confusion_matrix": version.eval_confusion_matrix,
                    "evaluated_at": version.evaluated_at.isoformat() if version.evaluated_at else None,
                    "has_evaluation": version.evaluated_at is not None,
                }
            )

        return {"success": True, "versions": versions_data, "total_versions": len(versions_data)}

    except Exception as e:
        logger.error(f"Error getting model versions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model versions: {str(e)}") from e


@router.post("/evaluate")
async def api_model_evaluate():
    """Evaluate the current model on annotated test chunks."""
    try:
        from src.utils.content_filter import ContentFilter
        from src.utils.model_evaluation import ModelEvaluator
        from src.utils.model_versioning import MLModelVersionManager

        # Load current model
        content_filter = ContentFilter()
        if not content_filter.load_model():
            return {"success": False, "message": "Failed to load current model"}

        # Initialize evaluator
        evaluator = ModelEvaluator()

        # Run evaluation
        logger.info("Starting model evaluation on test set...")
        eval_metrics = evaluator.evaluate_model(content_filter)

        # Save metrics to latest model version
        version_manager = MLModelVersionManager(async_db_manager)
        latest_version = await version_manager.get_latest_version()

        if latest_version:
            success = await version_manager.save_evaluation_metrics(latest_version.id, eval_metrics)
            if not success:
                logger.warning("Failed to save evaluation metrics to database")
        else:
            logger.warning("No model versions found to save evaluation metrics")

        # Prepare response
        response_data = {
            "success": True,
            "message": "Model evaluation completed successfully",
            "metrics": {
                "accuracy": eval_metrics["accuracy"],
                "precision_huntable": eval_metrics["precision_huntable"],
                "precision_not_huntable": eval_metrics["precision_not_huntable"],
                "recall_huntable": eval_metrics["recall_huntable"],
                "recall_not_huntable": eval_metrics["recall_not_huntable"],
                "f1_score_huntable": eval_metrics["f1_score_huntable"],
                "f1_score_not_huntable": eval_metrics["f1_score_not_huntable"],
                "confusion_matrix": eval_metrics["confusion_matrix"],
                "avg_confidence": eval_metrics["avg_confidence"],
                "total_chunks": eval_metrics["total_eval_chunks"],
                "misclassified_count": eval_metrics["misclassified_count"],
            },
            "misclassified_chunks": eval_metrics["misclassified_chunks"][:10],  # Limit to first 10 for response
            "eval_summary": evaluator.get_eval_data_summary(),
        }

        logger.info(f"Evaluation complete. Accuracy: {eval_metrics['accuracy']:.3f}")
        return response_data

    except FileNotFoundError as e:
        logger.error(f"Evaluation data not found: {e}")
        return {"success": False, "message": "Evaluation dataset not found. Please run annotation export first."}
    except Exception as e:
        logger.error(f"Model evaluation failed: {e}")
        return {"success": False, "message": f"Evaluation failed: {str(e)}"}


@router.get("/classification-timeline")
async def api_get_classification_timeline():
    """Get classification breakdown data across model versions for time series chart."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_service import ChunkAnalysisService

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisService(sync_db)

            # Get all model versions with their classification data
            timeline_data = []

            # Get all model versions from database
            from src.utils.model_versioning import MLModelVersionManager

            version_manager = MLModelVersionManager(async_db_manager)
            model_versions = await version_manager.get_all_versions()

            # Get all available model versions from chunk analysis data
            available_model_versions = service.get_available_model_versions()

            for model_version_str in available_model_versions:
                # Find corresponding database version (if any)
                db_version = None
                for version in model_versions:
                    # Try to match by version number or date
                    if f"v{version.version_number}" == model_version_str or (
                        version.trained_at and model_version_str.endswith(version.trained_at.strftime("%Y%m%d"))
                    ):
                        db_version = version
                        break

                # Get classification stats for this model version
                stats = service.get_chunk_analysis_results(
                    model_version=model_version_str,
                    limit=50000,  # High limit to get all data for this version
                )

                if stats:
                    # Calculate breakdown for this version
                    total_chunks = len(stats)
                    agreement = sum(
                        1 for s in stats if s.get("ml_prediction", False) and s.get("hunt_prediction", False)
                    )
                    ml_only = sum(
                        1 for s in stats if s.get("ml_prediction", False) and not s.get("hunt_prediction", False)
                    )
                    hunt_only = sum(
                        1 for s in stats if s.get("hunt_prediction", False) and not s.get("ml_prediction", False)
                    )
                    neither = total_chunks - agreement - ml_only - hunt_only

                    # Convert to percentages for better trend analysis
                    agreement_pct = (agreement / total_chunks * 100) if total_chunks > 0 else 0
                    ml_only_pct = (ml_only / total_chunks * 100) if total_chunks > 0 else 0
                    hunt_only_pct = (hunt_only / total_chunks * 100) if total_chunks > 0 else 0
                    neither_pct = (neither / total_chunks * 100) if total_chunks > 0 else 0

                    timeline_data.append(
                        {
                            "model_version": model_version_str,
                            "version_number": db_version.version_number if db_version else 0,
                            "trained_at": db_version.trained_at.isoformat()
                            if db_version and db_version.trained_at
                            else None,
                            "total_chunks": total_chunks,
                            "agreement": agreement_pct,
                            "ml_only": ml_only_pct,
                            "hunt_only": hunt_only_pct,
                            "neither": neither_pct,
                            "accuracy": db_version.accuracy if db_version and db_version.accuracy else 0,
                        }
                    )

            # Sort by version number
            timeline_data.sort(key=lambda x: x["version_number"])

            return {
                "success": True,
                "timeline": timeline_data,
                "message": f"Retrieved classification timeline for {len(timeline_data)} model versions",
            }

        finally:
            sync_db.close()

    except Exception as e:
        logger.error(f"Error getting classification timeline: {e}")
        return {"success": False, "timeline": [], "message": f"Failed to get classification timeline: {str(e)}"}


@router.get("/eval-chunk-count")
async def api_get_eval_chunk_count():
    """Get count of chunks in evaluation dataset."""
    try:
        import os

        import pandas as pd

        eval_data_path = "outputs/evaluation_data/eval_set.csv"

        if os.path.exists(eval_data_path):
            df = pd.read_csv(eval_data_path)
            count = len(df)
        else:
            count = 0

        return {"success": True, "count": count, "message": f"Evaluation dataset contains {count} chunks"}

    except Exception as e:
        logger.error(f"Error getting evaluation chunk count: {e}")
        return {"success": False, "count": 0, "message": f"Error: {str(e)}"}


@router.get("/feedback-count")
async def api_get_feedback_count():
    """Get count of available user feedback samples and annotations for retraining."""
    try:
        feedback_count = 0
        annotation_count = 0

        # Count feedback from database
        async with async_db_manager.get_session() as session:
            from sqlalchemy import text

            # Count unused feedback from database
            feedback_query = text("""
            SELECT COUNT(*) as feedback_count
            FROM chunk_classification_feedback
            WHERE used_for_training = FALSE
            """)

            result = await session.execute(feedback_query)
            feedback_count = result.scalar() or 0

            # Count annotations from database
            annotation_query = text("""
            SELECT COUNT(*) as annotation_count
            FROM article_annotations
            WHERE LENGTH(selected_text) >= 950
            AND LENGTH(selected_text) <= 1050
            AND used_for_training = FALSE
            """)

            result = await session.execute(annotation_query)
            annotation_count = result.scalar() or 0

            # Get total feedback count
            total_feedback_query = text("""
            SELECT COUNT(*) as total_feedback_count
            FROM chunk_classification_feedback
            """)
            result = await session.execute(total_feedback_query)
            total_feedback_count = result.scalar() or 0

            # Get total annotation count
            total_annotation_query = text("""
            SELECT COUNT(*) as total_annotation_count
            FROM article_annotations
            WHERE LENGTH(selected_text) >= 950
            AND LENGTH(selected_text) <= 1050
            """)
            result = await session.execute(total_annotation_query)
            total_annotation_count = result.scalar() or 0

        total_count = feedback_count + annotation_count

        return {
            "success": True,
            "count": total_count,
            "feedback_count": feedback_count,
            "annotation_count": annotation_count,
            "total_feedback_count": total_feedback_count,
            "total_annotation_count": total_annotation_count,
            "message": f"Found {total_count} training samples available ({feedback_count} feedback + {annotation_count} annotations)",
        }

    except Exception as e:
        logger.error(f"Error getting feedback count: {e}")
        return {"success": False, "count": 0, "message": f"Failed to get feedback count: {str(e)}"}


@router.get("/compare/{version_id}")
async def api_get_model_comparison(version_id: int):
    """Get comparison results for a specific model version vs its predecessor."""
    try:
        from src.utils.model_versioning import MLModelVersionManager

        version_manager = MLModelVersionManager(async_db_manager)

        # Get the version
        version = await version_manager.get_version_by_id(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Model version not found")

        # If comparison results are already stored, return them
        if version.comparison_results:
            return {
                "success": True,
                "comparison": version.comparison_results,
                "version_id": version_id,
                "version_number": version.version_number,
            }

        # Otherwise, try to find the previous version and generate comparison
        if not version.compared_with_version:
            # Find the previous version
            all_versions = await version_manager.get_all_versions(limit=10)
            current_version_num = version.version_number

            # Find the previous version
            previous_version = None
            for v in all_versions:
                if v.version_number == current_version_num - 1:
                    previous_version = v
                    break

            if previous_version:
                # Set the comparison reference
                async with async_db_manager.get_session() as session:
                    from sqlalchemy import update

                    from src.database.models import MLModelVersionTable

                    await session.execute(
                        update(MLModelVersionTable)
                        .where(MLModelVersionTable.id == version_id)
                        .values(compared_with_version=previous_version.id)
                    )
                    await session.commit()

                # Now generate the comparison
                comparison = await version_manager.compare_versions(previous_version.id, version_id)

                # Store the comparison results
                await version_manager.update_comparison_results(version_id, comparison)

                return {
                    "success": True,
                    "comparison": comparison,
                    "version_id": version_id,
                    "version_number": version.version_number,
                }
            return {"success": False, "message": "No previous version to compare with"}
        # Use existing comparison reference
        comparison = await version_manager.compare_versions(version.compared_with_version, version_id)

        # Store the comparison results
        await version_manager.update_comparison_results(version_id, comparison)

        return {
            "success": True,
            "comparison": comparison,
            "version_id": version_id,
            "version_number": version.version_number,
        }

    except Exception as e:
        logger.error(f"Error getting model comparison: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model comparison: {str(e)}") from e


@router.get("/feedback-comparison")
async def api_get_feedback_comparison():
    """Get before/after confidence levels for chunks that received user feedback."""
    try:
        import os

        import pandas as pd

        from src.utils.content_filter import ContentFilter

        # Load feedback data
        feedback_file = "outputs/training_data/chunk_classification_feedback.csv"
        if not os.path.exists(feedback_file):
            return {"success": False, "message": "No feedback data found"}

        feedback_df = pd.read_csv(feedback_file)
        if feedback_df.empty:
            return {"success": False, "message": "No feedback data available"}

        # Get the latest model version and previous version
        from src.utils.model_versioning import MLModelVersionManager

        version_manager = MLModelVersionManager(async_db_manager)
        latest_version = await version_manager.get_latest_version()

        if not latest_version:
            return {"success": False, "message": "No model versions found"}

        # Get previous version for comparison
        all_versions = await version_manager.get_all_versions(limit=2)
        if len(all_versions) < 2:
            return {"success": False, "message": "Need at least 2 model versions to show changes"}

        previous_version = all_versions[1]  # Second most recent

        # Load current model (latest version)
        content_filter = ContentFilter()
        if not content_filter.load_model():
            return {"success": False, "message": "Failed to load current model"}

        # Filter feedback to only include entries from the last model version (after previous version was trained)
        import pytz

        previous_trained_at = previous_version.trained_at

        # Convert timestamp strings to datetime for comparison (handle timezone)
        feedback_df["timestamp_dt"] = pd.to_datetime(feedback_df["timestamp"], utc=True)

        # Ensure previous_trained_at is timezone-aware
        if previous_trained_at.tzinfo is None:
            previous_trained_at = previous_trained_at.replace(tzinfo=pytz.UTC)

        # Only include feedback provided after the previous model was trained
        recent_feedback = feedback_df[feedback_df["timestamp_dt"] > previous_trained_at]

        if recent_feedback.empty:
            return {"success": False, "message": "No feedback provided since the last model version"}

        # Deduplicate feedback by article_id + chunk_id to get unique chunks you provided feedback on
        unique_feedback = recent_feedback.drop_duplicates(subset=["article_id", "chunk_id"], keep="last")

        # Only show chunks where the user actually provided feedback (not just chunks processed during retraining)
        # Filter out chunks with 0.0 confidence as these are likely not actual feedback chunks
        actual_feedback_chunks = unique_feedback[unique_feedback["model_confidence"] > 0.01]

        if actual_feedback_chunks.empty:
            return {"success": False, "message": "No valid feedback chunks found (all have 0.0% confidence)"}

        unique_feedback = actual_feedback_chunks

        # Test each unique feedback chunk with current model
        feedback_comparisons = []

        for _, row in unique_feedback.iterrows():
            chunk_text = row["chunk_text"]
            stored_old_confidence = row["model_confidence"]
            old_classification = row["model_classification"]
            user_classification = row["user_classification"]
            is_correct = row["is_correct"]

            # Get new prediction with current model
            new_is_huntable, new_confidence = content_filter.predict_huntability(chunk_text)
            new_classification = "Huntable" if new_is_huntable else "Not Huntable"

            # Extract huntable probability from model for new prediction
            import numpy as np

            features = content_filter.extract_features(chunk_text, include_new_features=False)
            feature_vector = np.array(list(features.values())).reshape(1, -1)
            probabilities = content_filter.model.predict_proba(feature_vector)[0]
            new_huntable_probability = float(probabilities[1])  # Index 1 is "Huntable"

            # Calculate old huntable probability from stored data
            if old_classification == "Huntable":
                old_huntable_probability = stored_old_confidence
            else:
                old_huntable_probability = 1.0 - stored_old_confidence

            # Calculate change in huntable probability
            huntable_probability_change = new_huntable_probability - old_huntable_probability

            # Only include chunks with meaningful huntable probability changes (> 1% or < -1%)
            if abs(huntable_probability_change) > 0.01:
                feedback_comparisons.append(
                    {
                        "article_id": row["article_id"],
                        "chunk_id": row["chunk_id"],
                        "chunk_text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                        "old_classification": old_classification,
                        "old_confidence": float(stored_old_confidence),
                        "old_huntable_probability": float(old_huntable_probability),
                        "new_classification": new_classification,
                        "new_confidence": float(new_confidence),
                        "new_huntable_probability": float(new_huntable_probability),
                        "confidence_change": float(new_confidence - stored_old_confidence),
                        "huntable_probability_change": float(huntable_probability_change),
                        "user_classification": user_classification,
                        "is_correct": is_correct,
                        "timestamp": row["timestamp"],
                    }
                )

        # Sort by huntable probability change (biggest improvements first)
        feedback_comparisons.sort(key=lambda x: x["huntable_probability_change"], reverse=True)

        return {
            "success": True,
            "feedback_comparisons": feedback_comparisons,
            "total_feedback_chunks": len(feedback_comparisons),
            "model_version": latest_version.version_number,
            "previous_model_version": previous_version.version_number,
            "comparison_period": f"Since model version {previous_version.version_number} (trained {previous_trained_at.strftime('%Y-%m-%d %H:%M')})",
        }

    except Exception as e:
        logger.error(f"Error getting feedback comparison: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get feedback comparison: {str(e)}") from e
