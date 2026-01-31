"""
OS Detection Evaluator.

Evaluates OS Detection Agent performance on test datasets.
"""

import json
import logging
import statistics
from pathlib import Path
from typing import Any

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.services.evaluation.base_evaluator import BaseAgentEvaluator
from src.services.os_detection_service import OSDetectionService

logger = logging.getLogger(__name__)


class OSDetectionEvaluator(BaseAgentEvaluator):
    """
    Evaluator for OS Detection Agent.

    Metrics:
    - Accuracy vs ground truth
    - Confidence scores
    - Multi-OS detection capability
    - Processing time
    """

    def __init__(
        self,
        model_version: str | None = None,
        evaluation_type: str = "baseline",
        workflow_config_version: int | None = None,
    ):
        """Initialize OS Detection evaluator."""
        super().__init__(
            agent_name="OSDetection",
            model_version=model_version,
            evaluation_type=evaluation_type,
            workflow_config_version=workflow_config_version,
        )

    async def evaluate_dataset(
        self, test_data_path: Path, os_detection_service: OSDetectionService | None = None, **kwargs
    ) -> dict[str, Any]:
        """
        Evaluate OS Detection Agent on test dataset.

        Args:
            test_data_path: Path to test dataset JSON file
            os_detection_service: OS detection service instance
            **kwargs: Additional parameters

        Returns:
            Dictionary with evaluation results
        """
        # Load test data
        with open(test_data_path) as f:
            test_data = json.load(f)

        # Initialize services if not provided
        if not os_detection_service:
            os_detection_service = OSDetectionService()

        # Get database session
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        results = []

        try:
            for example in test_data:
                article_id = example.get("article_id")
                expected_os = example.get("expected_os")
                ground_truth_os = example.get("ground_truth_os")

                if not article_id:
                    logger.warning("Skipping example without article_id")
                    continue

                # Get article from database
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()

                if not article:
                    logger.warning(f"Article {article_id} not found, skipping")
                    results.append({"article_id": article_id, "error": "Article not found", "evaluation": None})
                    continue

                # Evaluate article
                try:
                    result = await self._evaluate_article(article, os_detection_service, expected_os, ground_truth_os)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error evaluating article {article_id}: {e}")
                    results.append({"article_id": article_id, "error": str(e), "evaluation": None})
        finally:
            db_session.close()

        self.results = results
        return self.calculate_metrics()

    async def _evaluate_article(
        self,
        article: ArticleTable,
        os_detection_service: OSDetectionService,
        expected_os: str | None = None,
        ground_truth_os: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate OS detection on a single article."""
        import time

        # Run OS detection
        start_time = time.time()
        try:
            detection_result = await os_detection_service.detect_os(content=article.content or "")
            processing_time = time.time() - start_time
        except Exception as e:
            return {"article_id": article.id, "error": str(e), "detection_result": None, "evaluation": None}

        # Extract detected OS and confidence
        # Note: detect_os returns 'operating_system' not 'detected_os'
        detected_os = detection_result.get("operating_system") if isinstance(detection_result, dict) else None
        confidence_str = detection_result.get("confidence") if isinstance(detection_result, dict) else None

        # Convert confidence string to numeric value for metrics
        confidence_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
        confidence = confidence_map.get(confidence_str, 0.5) if confidence_str else None

        # Evaluate
        evaluation = self._evaluate_detection_result(
            detected_os, confidence, expected_os, ground_truth_os, processing_time
        )

        return {
            "article_id": article.id,
            "title": article.title,
            "url": article.canonical_url or "",
            "detection_result": detection_result,
            "evaluation": evaluation,
            "expected_os": expected_os,
            "ground_truth_os": ground_truth_os,
        }

    def _evaluate_detection_result(
        self,
        detected_os: str | None,
        confidence: float | None,
        expected_os: str | None,
        ground_truth_os: str | None,
        processing_time: float,
    ) -> dict[str, Any]:
        """Evaluate a single detection result."""
        evaluation = {
            "detected_os": detected_os,
            "confidence": confidence,
            "has_detection": detected_os is not None,
            "has_confidence": confidence is not None,
            "processing_time": processing_time,
            "accuracy": None,
            "multi_os_detected": False,
        }

        # Check accuracy against expected
        if expected_os is not None:
            if isinstance(detected_os, str):
                # Normalize for comparison
                detected_normalized = detected_os.lower().strip()
                expected_normalized = expected_os.lower().strip()
                evaluation["accuracy"] = detected_normalized == expected_normalized
            elif isinstance(detected_os, list):
                # Multi-OS detection
                detected_normalized = [os.lower().strip() for os in detected_os]
                expected_normalized = expected_os.lower().strip()
                evaluation["accuracy"] = expected_normalized in detected_normalized
                evaluation["multi_os_detected"] = len(detected_os) > 1

        # Check accuracy against ground truth
        if ground_truth_os is not None:
            if isinstance(detected_os, str):
                detected_normalized = detected_os.lower().strip()
                ground_truth_normalized = ground_truth_os.lower().strip()
                evaluation["ground_truth_accuracy"] = detected_normalized == ground_truth_normalized
            elif isinstance(detected_os, list):
                detected_normalized = [os.lower().strip() for os in detected_os]
                ground_truth_normalized = ground_truth_os.lower().strip()
                evaluation["ground_truth_accuracy"] = ground_truth_normalized in detected_normalized
                evaluation["multi_os_detected"] = len(detected_os) > 1

        return evaluation

    def calculate_metrics(self) -> dict[str, Any]:
        """Calculate aggregate metrics from results."""
        if not self.results:
            return {}

        total = len(self.results)
        errors = sum(1 for r in self.results if r.get("error"))
        valid_results = [r for r in self.results if r.get("evaluation") and not r.get("error")]

        if not valid_results:
            return {
                "total_articles": total,
                "errors": errors,
                "valid_results": 0,
                "error_rate": errors / total if total > 0 else 0,
            }

        evaluations = [r["evaluation"] for r in valid_results]

        # Accuracy metrics
        accuracies = [e["accuracy"] for e in evaluations if e.get("accuracy") is not None]
        ground_truth_accuracies = [
            e["ground_truth_accuracy"] for e in evaluations if e.get("ground_truth_accuracy") is not None
        ]

        # Confidence scores
        confidences = [e["confidence"] for e in evaluations if e.get("confidence") is not None]

        # Multi-OS detection
        multi_os_count = sum(1 for e in evaluations if e.get("multi_os_detected"))

        # Processing times
        processing_times = [e.get("processing_time", 0) for e in evaluations]

        metrics = {
            "total_articles": total,
            "errors": errors,
            "valid_results": len(valid_results),
            "error_rate": errors / total if total > 0 else 0,
            # Accuracy
            "accuracy": sum(accuracies) / len(accuracies) if accuracies else None,
            "ground_truth_accuracy": sum(ground_truth_accuracies) / len(ground_truth_accuracies)
            if ground_truth_accuracies
            else None,
            # Confidence
            "avg_confidence": statistics.mean(confidences) if confidences else None,
            "min_confidence": min(confidences) if confidences else None,
            "max_confidence": max(confidences) if confidences else None,
            # Multi-OS capability
            "multi_os_detection_rate": multi_os_count / len(valid_results) if valid_results else 0,
            # Processing time
            "avg_processing_time": statistics.mean(processing_times) if processing_times else None,
            "min_processing_time": min(processing_times) if processing_times else None,
            "max_processing_time": max(processing_times) if processing_times else None,
        }

        self.metrics = metrics
        return metrics
