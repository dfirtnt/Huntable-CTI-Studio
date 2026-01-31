"""
ML Model Versioning System for tracking and comparing model performance.

This module provides functionality to:
- Save model versions with performance metrics
- Compare model versions before/after retraining
- Run comparison tests on holdout data
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import MLModelVersionTable

logger = logging.getLogger(__name__)


class MLModelVersionManager:
    """Manages ML model versions and performance comparisons."""

    def __init__(self, db_manager: AsyncDatabaseManager):
        self.db_manager = db_manager

    async def save_model_version(
        self,
        metrics: dict[str, Any],
        _training_config: dict[str, Any],
        feedback_count: int = 0,
        model_file_path: str = None,
    ) -> int:
        """
        Save a new model version with performance metrics.

        Args:
            metrics: Training metrics from ContentFilter.train_model()
            _training_config: Configuration used for training (reserved for future use)
            feedback_count: Number of feedback samples used in training
            model_file_path: Path to the saved model file

        Returns:
            int: The ID of the saved model version
        """
        try:
            async with self.db_manager.get_session() as session:
                # Get next version number
                latest_version = await self.get_latest_version()
                next_version = (latest_version.version_number + 1) if latest_version else 1

                # Create new model version record
                model_version = MLModelVersionTable(
                    version_number=next_version,
                    trained_at=datetime.now(),
                    training_data_size=metrics.get("training_data_size", 0),
                    feedback_samples_count=feedback_count,
                    accuracy=metrics.get("accuracy"),
                    precision_huntable=metrics.get("precision_huntable"),
                    precision_not_huntable=metrics.get("precision_not_huntable"),
                    recall_huntable=metrics.get("recall_huntable"),
                    recall_not_huntable=metrics.get("recall_not_huntable"),
                    f1_score_huntable=metrics.get("f1_score_huntable"),
                    f1_score_not_huntable=metrics.get("f1_score_not_huntable"),
                    model_params=metrics.get("model_params", {}),
                    training_duration_seconds=metrics.get("training_duration_seconds"),
                    model_file_path=model_file_path,
                )

                session.add(model_version)
                await session.commit()
                await session.refresh(model_version)

                logger.info(f"Saved model version {next_version} with accuracy {metrics.get('accuracy', 0):.3f}")
                return model_version.id

        except Exception as e:
            logger.error(f"Error saving model version: {e}")
            raise

    async def get_latest_version(self) -> MLModelVersionTable | None:
        """Get the latest model version."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(MLModelVersionTable).order_by(desc(MLModelVersionTable.version_number)).limit(1)
                )
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting latest version: {e}")
            return None

    async def get_version_by_id(self, version_id: int) -> MLModelVersionTable | None:
        """Get a specific model version by ID."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(select(MLModelVersionTable).where(MLModelVersionTable.id == version_id))
                return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting version {version_id}: {e}")
            return None

    async def save_evaluation_metrics(self, version_id: int, eval_metrics: dict[str, Any]) -> bool:
        """
        Save evaluation metrics to a model version.

        Args:
            version_id: ID of the model version
            eval_metrics: Dictionary containing evaluation metrics

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(select(MLModelVersionTable).where(MLModelVersionTable.id == version_id))
                model_version = result.scalar_one_or_none()

                if not model_version:
                    logger.error(f"Model version {version_id} not found")
                    return False

                # Update evaluation metrics
                model_version.eval_accuracy = eval_metrics.get("accuracy")
                model_version.eval_precision_huntable = eval_metrics.get("precision_huntable")
                model_version.eval_precision_not_huntable = eval_metrics.get("precision_not_huntable")
                model_version.eval_recall_huntable = eval_metrics.get("recall_huntable")
                model_version.eval_recall_not_huntable = eval_metrics.get("recall_not_huntable")
                model_version.eval_f1_score_huntable = eval_metrics.get("f1_score_huntable")
                model_version.eval_f1_score_not_huntable = eval_metrics.get("f1_score_not_huntable")
                model_version.eval_confusion_matrix = eval_metrics.get("confusion_matrix")
                model_version.evaluated_at = datetime.now()

                await session.commit()

                logger.info(f"Saved evaluation metrics for model version {version_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving evaluation metrics: {e}")
            return False

    async def get_version_with_eval(self, version_id: int) -> MLModelVersionTable | None:
        """Get a model version with evaluation metrics included."""
        return await self.get_version_by_id(version_id)

    async def get_all_versions(self, limit: int = 50) -> list[MLModelVersionTable]:
        """Get all model versions, ordered by version number descending."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(MLModelVersionTable).order_by(desc(MLModelVersionTable.version_number)).limit(limit)
                )
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting all versions: {e}")
            return []

    async def compare_versions(self, old_version_id: int, new_version_id: int) -> dict[str, Any]:
        """
        Compare two model versions and generate a comparison report.

        Args:
            old_version_id: ID of the older model version
            new_version_id: ID of the newer model version

        Returns:
            Dict containing comparison metrics and analysis
        """
        try:
            old_version = await self.get_version_by_id(old_version_id)
            new_version = await self.get_version_by_id(new_version_id)

            if not old_version or not new_version:
                raise ValueError("One or both model versions not found")

            # Calculate improvements
            accuracy_improvement = new_version.accuracy - old_version.accuracy if old_version.accuracy else 0
            precision_huntable_improvement = (
                new_version.precision_huntable - old_version.precision_huntable if old_version.precision_huntable else 0
            )
            recall_huntable_improvement = (
                new_version.recall_huntable - old_version.recall_huntable if old_version.recall_huntable else 0
            )

            comparison = {
                "old_version": {
                    "id": old_version.id,
                    "version_number": old_version.version_number,
                    "trained_at": old_version.trained_at.isoformat(),
                    "accuracy": old_version.accuracy,
                    "precision_huntable": old_version.precision_huntable,
                    "precision_not_huntable": old_version.precision_not_huntable,
                    "recall_huntable": old_version.recall_huntable,
                    "recall_not_huntable": old_version.recall_not_huntable,
                    "f1_score_huntable": old_version.f1_score_huntable,
                    "f1_score_not_huntable": old_version.f1_score_not_huntable,
                    "training_data_size": old_version.training_data_size,
                    "feedback_samples_count": old_version.feedback_samples_count,
                },
                "new_version": {
                    "id": new_version.id,
                    "version_number": new_version.version_number,
                    "trained_at": new_version.trained_at.isoformat(),
                    "accuracy": new_version.accuracy,
                    "precision_huntable": new_version.precision_huntable,
                    "precision_not_huntable": new_version.precision_not_huntable,
                    "recall_huntable": new_version.recall_huntable,
                    "recall_not_huntable": new_version.recall_not_huntable,
                    "f1_score_huntable": new_version.f1_score_huntable,
                    "f1_score_not_huntable": new_version.f1_score_not_huntable,
                    "training_data_size": new_version.training_data_size,
                    "feedback_samples_count": new_version.feedback_samples_count,
                },
                "improvements": {
                    "accuracy_change": accuracy_improvement,
                    "accuracy_change_percent": (accuracy_improvement / old_version.accuracy * 100)
                    if old_version.accuracy
                    else 0,
                    "precision_huntable_change": precision_huntable_improvement,
                    "recall_huntable_change": recall_huntable_improvement,
                    "training_data_increase": new_version.training_data_size - old_version.training_data_size,
                    "feedback_samples_added": new_version.feedback_samples_count - old_version.feedback_samples_count,
                },
                "summary": {
                    "overall_improvement": accuracy_improvement > 0,
                    "key_improvements": [],
                    "areas_of_concern": [],
                },
            }

            # Generate summary insights
            if accuracy_improvement > 0.01:
                comparison["summary"]["key_improvements"].append(
                    f"Accuracy improved by {accuracy_improvement:.3f} ({comparison['improvements']['accuracy_change_percent']:.1f}%)"
                )
            elif accuracy_improvement < -0.01:
                comparison["summary"]["areas_of_concern"].append(
                    f"Accuracy decreased by {abs(accuracy_improvement):.3f}"
                )

            if precision_huntable_improvement > 0.01:
                comparison["summary"]["key_improvements"].append(
                    f"Precision for huntable content improved by {precision_huntable_improvement:.3f}"
                )
            elif precision_huntable_improvement < -0.01:
                comparison["summary"]["areas_of_concern"].append(
                    f"Precision for huntable content decreased by {abs(precision_huntable_improvement):.3f}"
                )

            if new_version.feedback_samples_count > old_version.feedback_samples_count:
                comparison["summary"]["key_improvements"].append(
                    f"Added {new_version.feedback_samples_count - old_version.feedback_samples_count} feedback samples"
                )

            return comparison

        except Exception as e:
            logger.error(f"Error comparing versions: {e}")
            raise

    async def run_comparison_test(
        self, old_model_path: str, new_model_path: str, test_articles: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Run a comparison test by classifying the same articles with both models.

        Args:
            old_model_path: Path to the old model file
            new_model_path: Path to the new model file
            test_articles: List of articles to test with

        Returns:
            Dict containing comparison test results
        """
        try:
            from src.utils.content_filter import ContentFilter

            # Load both models
            old_filter = ContentFilter(model_path=old_model_path)
            new_filter = ContentFilter(model_path=new_model_path)

            if not old_filter.load_model() or not new_filter.load_model():
                raise ValueError("Failed to load one or both models")

            # Test each article with both models
            results = []
            prediction_changes = []

            for article in test_articles:
                content = article.get("content", "")
                if not content:
                    continue

                # Get predictions from both models
                old_result = old_filter.filter_content(content, min_confidence=0.7)
                new_result = new_filter.filter_content(content, min_confidence=0.7)

                # Compare predictions
                prediction_changed = old_result.is_huntable != new_result.is_huntable

                result = {
                    "article_id": article.get("id"),
                    "article_title": article.get("title", "")[:100],
                    "old_prediction": old_result.is_huntable,
                    "old_confidence": old_result.confidence,
                    "new_prediction": new_result.is_huntable,
                    "new_confidence": new_result.confidence,
                    "prediction_changed": prediction_changed,
                    "old_cost_savings": old_result.cost_savings,
                    "new_cost_savings": new_result.cost_savings,
                }

                results.append(result)

                if prediction_changed:
                    prediction_changes.append(result)

            # Calculate summary statistics
            total_articles = len(results)
            changed_predictions = len(prediction_changes)
            change_rate = (changed_predictions / total_articles * 100) if total_articles > 0 else 0

            # Calculate average confidence changes
            old_avg_confidence = sum(r["old_confidence"] for r in results) / total_articles if total_articles > 0 else 0
            new_avg_confidence = sum(r["new_confidence"] for r in results) / total_articles if total_articles > 0 else 0

            return {
                "total_articles_tested": total_articles,
                "prediction_changes": changed_predictions,
                "change_rate_percent": change_rate,
                "old_avg_confidence": old_avg_confidence,
                "new_avg_confidence": new_avg_confidence,
                "confidence_improvement": new_avg_confidence - old_avg_confidence,
                "detailed_results": results,
                "prediction_changes_detail": prediction_changes,
            }

        except Exception as e:
            logger.error(f"Error running comparison test: {e}")
            raise

    async def update_comparison_results(self, version_id: int, comparison_results: dict[str, Any]) -> bool:
        """Update a model version with comparison results."""
        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(select(MLModelVersionTable).where(MLModelVersionTable.id == version_id))
                model_version = result.scalar_one_or_none()

                if model_version:
                    model_version.comparison_results = comparison_results
                    await session.commit()
                    return True
                return False

        except Exception as e:
            logger.error(f"Error updating comparison results: {e}")
            return False
