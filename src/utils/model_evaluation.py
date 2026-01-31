"""
Model Evaluation System for ML Content Filter.

This module provides functionality to evaluate ML models on a standardized
test set of annotated chunks from the article_annotations table.
"""

import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """
    Evaluates ML models on standardized test set of annotated chunks.

    Uses annotated chunks from article_annotations table to provide
    consistent evaluation metrics across different model versions.
    """

    def __init__(self, eval_data_path: str = "outputs/evaluation_data/eval_set.csv"):
        """
        Initialize evaluator with path to evaluation dataset.

        Args:
            eval_data_path: Path to CSV file containing evaluation chunks
        """
        self.eval_data_path = eval_data_path
        self.eval_data = None
        self._load_eval_data()

    def _load_eval_data(self) -> None:
        """Load evaluation data from CSV file."""
        try:
            if not os.path.exists(self.eval_data_path):
                raise FileNotFoundError(f"Evaluation data not found: {self.eval_data_path}")

            logger.info(f"Loading evaluation data from {self.eval_data_path}")
            self.eval_data = pd.read_csv(self.eval_data_path)

            # Validate data
            if len(self.eval_data) == 0:
                raise ValueError("Evaluation dataset is empty")

            # Check required columns
            required_cols = ["annotation_id", "chunk_text", "label"]
            missing_cols = [col for col in required_cols if col not in self.eval_data.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")

            # Validate labels
            valid_labels = {"huntable", "not_huntable"}
            invalid_labels = set(self.eval_data["label"].unique()) - valid_labels
            if invalid_labels:
                raise ValueError(f"Invalid labels found: {invalid_labels}")

            # Validate chunk lengths
            chunk_lengths = self.eval_data["chunk_text"].str.len()
            non_1000_chunks = chunk_lengths[chunk_lengths != 1000]
            if len(non_1000_chunks) > 0:
                logger.warning(f"Found {len(non_1000_chunks)} chunks with non-1000 character length")

            logger.info(f"Loaded {len(self.eval_data)} evaluation chunks")
            logger.info(f"Label distribution: {self.eval_data['label'].value_counts().to_dict()}")

        except Exception as e:
            logger.error(f"Failed to load evaluation data: {e}")
            raise

    def evaluate_model(self, content_filter) -> dict[str, Any]:
        """
        Evaluate a ContentFilter model on the evaluation dataset.

        Args:
            content_filter: ContentFilter instance with trained model

        Returns:
            Dict containing evaluation metrics and misclassified chunks
        """
        if self.eval_data is None:
            raise ValueError("Evaluation data not loaded")

        logger.info("Starting model evaluation...")

        # Get predictions for all chunks
        predictions = []
        confidences = []
        misclassified_chunks = []

        for idx, row in self.eval_data.iterrows():
            chunk_text = row["chunk_text"]
            true_label = row["label"]
            annotation_id = row["annotation_id"]

            # Get model prediction
            is_huntable, confidence = content_filter.predict_huntability(chunk_text)
            predicted_label = "huntable" if is_huntable else "not_huntable"

            predictions.append(predicted_label)
            confidences.append(confidence)

            # Track misclassified chunks
            if predicted_label != true_label:
                misclassified_chunks.append(
                    {
                        "annotation_id": annotation_id,
                        "article_id": row["article_id"],
                        "true_label": true_label,
                        "predicted_label": predicted_label,
                        "confidence": confidence,
                        "chunk_preview": chunk_text[:100] + "..." if len(chunk_text) > 100 else chunk_text,
                    }
                )

        # Calculate metrics
        metrics = self._calculate_metrics(self.eval_data["label"].tolist(), predictions, confidences)

        # Add misclassified chunks info
        metrics["misclassified_chunks"] = misclassified_chunks
        metrics["total_eval_chunks"] = len(self.eval_data)
        metrics["misclassified_count"] = len(misclassified_chunks)

        logger.info(f"Evaluation complete. Accuracy: {metrics['accuracy']:.3f}")
        logger.info(f"Misclassified: {len(misclassified_chunks)}/{len(self.eval_data)} chunks")

        return metrics

    def _calculate_metrics(self, y_true: list[str], y_pred: list[str], confidences: list[float]) -> dict[str, Any]:
        """
        Calculate comprehensive evaluation metrics.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            confidences: Prediction confidences

        Returns:
            Dict containing all evaluation metrics
        """
        # Convert to binary for sklearn metrics
        y_true_binary = [1 if label == "huntable" else 0 for label in y_true]
        y_pred_binary = [1 if label == "huntable" else 0 for label in y_pred]

        # Overall metrics
        accuracy = accuracy_score(y_true_binary, y_pred_binary)

        # Per-class metrics
        precision = precision_score(y_true_binary, y_pred_binary, average=None, zero_division=0)
        recall = recall_score(y_true_binary, y_pred_binary, average=None, zero_division=0)
        f1 = f1_score(y_true_binary, y_pred_binary, average=None, zero_division=0)

        # Confusion matrix
        cm = confusion_matrix(y_true_binary, y_pred_binary)

        # Confidence statistics
        confidences = np.array(confidences)
        avg_confidence = float(np.mean(confidences))
        std_confidence = float(np.std(confidences))

        # Confidence by class
        huntable_confidences = [conf for conf, pred in zip(confidences, y_pred_binary) if pred == 1]
        not_huntable_confidences = [conf for conf, pred in zip(confidences, y_pred_binary) if pred == 0]

        metrics = {
            # Overall metrics
            "accuracy": float(accuracy),
            "avg_confidence": avg_confidence,
            "std_confidence": std_confidence,
            # Per-class metrics (index 0 = not_huntable, index 1 = huntable)
            "precision_huntable": float(precision[1]) if len(precision) > 1 else 0.0,
            "precision_not_huntable": float(precision[0]) if len(precision) > 0 else 0.0,
            "recall_huntable": float(recall[1]) if len(recall) > 1 else 0.0,
            "recall_not_huntable": float(recall[0]) if len(recall) > 0 else 0.0,
            "f1_score_huntable": float(f1[1]) if len(f1) > 1 else 0.0,
            "f1_score_not_huntable": float(f1[0]) if len(f1) > 0 else 0.0,
            # Confusion matrix (TN, FP, FN, TP)
            "confusion_matrix": {
                "true_negative": int(cm[0, 0]) if cm.shape == (2, 2) else 0,
                "false_positive": int(cm[0, 1]) if cm.shape == (2, 2) else 0,
                "false_negative": int(cm[1, 0]) if cm.shape == (2, 2) else 0,
                "true_positive": int(cm[1, 1]) if cm.shape == (2, 2) else 0,
            },
            # Confidence statistics
            "huntable_avg_confidence": float(np.mean(huntable_confidences)) if huntable_confidences else 0.0,
            "not_huntable_avg_confidence": float(np.mean(not_huntable_confidences))
            if not_huntable_confidences
            else 0.0,
            # Label distribution
            "label_distribution": {
                "huntable": int(sum(y_true_binary)),
                "not_huntable": int(len(y_true_binary) - sum(y_true_binary)),
            },
        }

        return metrics

    def get_eval_data_summary(self) -> dict[str, Any]:
        """
        Get summary of evaluation dataset.

        Returns:
            Dict containing dataset statistics
        """
        if self.eval_data is None:
            raise ValueError("Evaluation data not loaded")

        return {
            "total_chunks": len(self.eval_data),
            "label_distribution": self.eval_data["label"].value_counts().to_dict(),
            "chunk_lengths": {
                "min": int(self.eval_data["chunk_text"].str.len().min()),
                "max": int(self.eval_data["chunk_text"].str.len().max()),
                "mean": float(self.eval_data["chunk_text"].str.len().mean()),
            },
            "unique_articles": int(self.eval_data["article_id"].nunique()),
            "data_path": self.eval_data_path,
        }

    def find_misclassified_chunks(self, content_filter, label_filter: str | None = None) -> list[dict[str, Any]]:
        """
        Find specific chunks that are misclassified by the model.

        Args:
            content_filter: ContentFilter instance
            label_filter: Optional filter by true label ('huntable' or 'not_huntable')

        Returns:
            List of misclassified chunk details
        """
        if self.eval_data is None:
            raise ValueError("Evaluation data not loaded")

        misclassified = []

        for idx, row in self.eval_data.iterrows():
            if label_filter and row["label"] != label_filter:
                continue

            chunk_text = row["chunk_text"]
            true_label = row["label"]

            is_huntable, confidence = content_filter.predict_huntability(chunk_text)
            predicted_label = "huntable" if is_huntable else "not_huntable"

            if predicted_label != true_label:
                misclassified.append(
                    {
                        "annotation_id": row["annotation_id"],
                        "article_id": row["article_id"],
                        "true_label": true_label,
                        "predicted_label": predicted_label,
                        "confidence": confidence,
                        "chunk_text": chunk_text,
                        "chunk_preview": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                    }
                )

        return misclassified
