"""
Evaluator for observable extraction models.

Computes eval and gold metrics per article, comparing sets of predicted spans
to sets of annotated spans within each article.
"""

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.models import (
    ArticleAnnotationTable,
    ArticleTable,
    ObservableEvaluationFailureTable,
)
from src.services.observable_evaluation.model_inference import ObservableModelInference
from src.services.observable_evaluation.span_normalization import (
    compute_span_length_delta,
    compute_token_overlap,
    is_exact_match,
    normalize_span,
)

logger = logging.getLogger(__name__)


class ObservableModelEvaluator:
    """Evaluator for observable extraction models."""

    def __init__(
        self,
        model_name: str,
        model_version: str,
        observable_type: str,
        overlap_threshold: float = 0.5,
    ):
        """
        Initialize the evaluator.

        Args:
            model_name: Name of the model (e.g., "CMD")
            model_version: Version identifier
            observable_type: Type of observable (e.g., "CMD", "PROC_LINEAGE")
            overlap_threshold: Minimum token overlap for eval true positive (default: 0.5)
        """
        self.model_name = model_name
        self.model_version = model_version
        self.observable_type = observable_type
        self.overlap_threshold = overlap_threshold
        self.inference_service = None

    def _load_model(self, model_path: str | None = None) -> bool:
        """Load the model for inference."""
        if self.inference_service is None:
            if model_path is None:
                model_path_obj = ObservableModelInference.find_model_path(self.model_name, self.model_version)
                if model_path_obj is None:
                    logger.error(f"Could not find model path for {self.model_name} v{self.model_version}")
                    return False
                model_path = str(model_path_obj)

            self.inference_service = ObservableModelInference(
                model_path=model_path,
                model_name=self.model_name,
                model_version=self.model_version,
            )

        return self.inference_service.load_model()

    def evaluate(
        self,
        session: Session,
        usage: str,
        model_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate the model on annotations with the specified usage.

        Metrics are computed per article, comparing sets of predicted spans
        to sets of annotated spans within each article.

        Args:
            session: Database session
            usage: Dataset usage ("eval" or "gold")
            model_path: Optional path to model (if None, auto-detects)

        Returns:
            Dictionary containing computed metrics
        """
        if usage not in ("eval", "gold"):
            raise ValueError(f"Invalid usage: {usage}. Must be 'eval' or 'gold'")

        # Load model
        if not self._load_model(model_path):
            # Try to find latest available model if specific version not found
            if model_path is None:
                logger.warning(
                    f"Model {self.model_name} v{self.model_version} not found. Attempting to find latest available model..."
                )
                latest_path = ObservableModelInference.find_model_path(self.model_name, model_version=None)
                if latest_path:
                    logger.info(f"Found latest model at {latest_path}, attempting to use it...")
                    if self._load_model(str(latest_path)):
                        logger.info(f"Successfully loaded latest model from {latest_path}")
                    else:
                        raise RuntimeError(
                            f"Failed to load model {self.model_name} v{self.model_version}. "
                            f"Also tried latest model at {latest_path} but it failed to load. "
                            f"Model may not have been trained yet. Check training logs."
                        )
                else:
                    raise RuntimeError(
                        f"Failed to load model {self.model_name} v{self.model_version}. "
                        f"No trained models found. Please train a model first."
                    )
            else:
                raise RuntimeError(
                    f"Failed to load model {self.model_name} v{self.model_version} from {model_path}. "
                    f"Model may not have been trained yet. Check training logs."
                )

        # Load annotations grouped by article
        article_annotations = self._load_annotations_by_article(session, usage)
        if not article_annotations:
            logger.warning(f"No {usage} annotations found for {self.observable_type}")
            return self._empty_metrics(usage)

        # Run evaluation
        if usage == "eval":
            return self._compute_eval_metrics(session, article_annotations)
        # gold
        return self._compute_gold_metrics(session, article_annotations)

    def _load_annotations_by_article(self, session: Session, usage: str) -> dict[int, list[ArticleAnnotationTable]]:
        """
        Load annotations grouped by article.

        For gold usage, also includes articles with zero gold annotations
        (negative space - these articles should be evaluated for hallucinations).
        """
        query = select(ArticleAnnotationTable).where(
            ArticleAnnotationTable.annotation_type == self.observable_type,
            ArticleAnnotationTable.usage == usage,
        )
        annotations = list(session.execute(query).scalars().all())

        # Group by article
        article_annotations = defaultdict(list)
        for ann in annotations:
            article_annotations[ann.article_id].append(ann)

        # For gold: also include articles that were marked as gold but have zero annotations
        # (This handles negative space - articles evaluated but with no gold observables)
        # Note: This requires articles to be explicitly marked in some way, or we track
        # articles that were evaluated. For now, we only evaluate articles with annotations.
        # Future enhancement: track evaluated articles separately.

        return dict(article_annotations)

    def _compute_eval_metrics(
        self,
        session: Session,
        article_annotations: dict[int, list[ArticleAnnotationTable]],
    ) -> dict[str, Any]:
        """
        Compute eval metrics per article using relaxed normalization.

        Metrics are computed by comparing sets of predicted spans to sets of
        annotated spans within each article.
        """
        # Per-article metrics
        article_metrics = []
        total_true_positives = 0
        total_false_positives = 0
        total_false_negatives = 0
        total_overlap_scores = []
        total_length_deltas = []
        documents_with_fp = 0
        total_documents = len(article_annotations)

        for article_id, annotations in article_annotations.items():
            # Get article text
            article = session.get(ArticleTable, article_id)
            if not article or not article.content:
                continue

            text = article.content
            gold_spans = [ann.selected_text for ann in annotations]

            # Run model inference
            predicted_spans_raw = self.inference_service.extract(text)
            predicted_spans = [span.get("text", "") for span in predicted_spans_raw]

            # Align predictions to annotations using relaxed normalization
            matched_predictions = set()
            matched_annotations = set()
            article_tp = 0
            article_fp = 0
            article_fn = 0

            for ann_idx, annotation in enumerate(annotations):
                ann_text = annotation.selected_text
                ann_normalized = normalize_span(ann_text, mode="relaxed")

                best_match_idx = None
                best_overlap = 0.0

                for pred_idx, pred_text in enumerate(predicted_spans):
                    if pred_idx in matched_predictions:
                        continue

                    pred_normalized = normalize_span(pred_text, mode="relaxed")
                    overlap = compute_token_overlap(pred_normalized, ann_normalized, mode="relaxed")

                    if overlap > best_overlap and overlap >= self.overlap_threshold:
                        best_overlap = overlap
                        best_match_idx = pred_idx

                if best_match_idx is not None:
                    article_tp += 1
                    total_true_positives += 1
                    matched_predictions.add(best_match_idx)
                    matched_annotations.add(ann_idx)
                    total_overlap_scores.append(best_overlap)
                    total_length_deltas.append(
                        compute_span_length_delta(predicted_spans[best_match_idx], ann_text, mode="relaxed")
                    )
                else:
                    article_fn += 1
                    total_false_negatives += 1

            # Count false positives (unmatched predictions)
            for pred_idx in range(len(predicted_spans)):
                if pred_idx not in matched_predictions:
                    article_fp += 1
                    total_false_positives += 1

            if article_fp > 0:
                documents_with_fp += 1

            article_metrics.append(
                {
                    "article_id": article_id,
                    "tp": article_tp,
                    "fp": article_fp,
                    "fn": article_fn,
                    "gold_count": len(annotations),
                    "pred_count": len(predicted_spans),
                }
            )

        # Compute aggregate metrics
        precision = (
            total_true_positives / (total_true_positives + total_false_positives)
            if (total_true_positives + total_false_positives) > 0
            else 0.0
        )
        recall = (
            total_true_positives / (total_true_positives + total_false_negatives)
            if (total_true_positives + total_false_negatives) > 0
            else 0.0
        )
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        avg_token_overlap = sum(total_overlap_scores) / len(total_overlap_scores) if total_overlap_scores else 0.0
        avg_length_delta = sum(total_length_deltas) / len(total_length_deltas) if total_length_deltas else 0.0
        fp_rate_per_doc = documents_with_fp / total_documents if total_documents > 0 else 0.0

        return {
            "usage": "eval",
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "token_overlap_f1": avg_token_overlap,
            "avg_span_length_delta": avg_length_delta,
            "false_positive_rate_per_document": fp_rate_per_doc,
            "sample_count": total_true_positives + total_false_negatives,
            "total_articles": total_documents,
            "true_positives": total_true_positives,
            "false_positives": total_false_positives,
            "false_negatives": total_false_negatives,
            "article_metrics": article_metrics,  # Per-article breakdown
        }

    def _compute_gold_metrics(
        self,
        session: Session,
        article_annotations: dict[int, list[ArticleAnnotationTable]],
    ) -> dict[str, Any]:
        """
        Compute gold metrics per article using strict normalization.

        Gold metrics are computed at the article level:
        - Zero-FP Pass Rate: percentage of articles with zero false positives
        - Exact Match Rate: percentage of gold spans with exact matches
        - Hallucination Rate: includes predictions on articles with zero gold observables
        """
        # Per-article tracking
        article_results = []
        failure_taxonomy = defaultdict(lambda: defaultdict(int))  # failure_type -> article_id -> count

        total_gold_spans = 0
        total_exact_matches = 0
        total_over_extractions = 0
        total_under_extractions = 0
        total_hallucinations = 0
        total_merged_commands = 0

        articles_with_zero_fp = 0
        articles_with_zero_gold = 0
        total_articles = len(article_annotations)

        # Track worst-case indicators
        max_merged_commands_per_article = 0
        articles_failing_zero_fp = []

        for article_id, annotations in article_annotations.items():
            # Get article text
            article = session.get(ArticleTable, article_id)
            if not article or not article.content:
                continue

            text = article.content
            gold_spans = [ann.selected_text for ann in annotations]
            total_gold_spans += len(gold_spans)

            # Handle negative space: articles with zero gold observables
            if len(gold_spans) == 0:
                articles_with_zero_gold += 1
                # Run inference to check for hallucinations
                predicted_spans_raw = self.inference_service.extract(text)
                predicted_spans = [span.get("text", "") for span in predicted_spans_raw]

                # All predictions on gold-empty articles are hallucinations
                article_hallucinations = len(predicted_spans)
                total_hallucinations += article_hallucinations

                if article_hallucinations > 0:
                    articles_failing_zero_fp.append(article_id)
                    failure_taxonomy["hallucination_on_empty"][article_id] = article_hallucinations

                article_results.append(
                    {
                        "article_id": article_id,
                        "gold_count": 0,
                        "pred_count": article_hallucinations,
                        "exact_matches": 0,
                        "hallucinations": article_hallucinations,
                        "zero_fp_pass": article_hallucinations == 0,
                    }
                )
                continue

            # Run model inference
            predicted_spans_raw = self.inference_service.extract(text)
            predicted_spans = [span.get("text", "") for span in predicted_spans_raw]

            # For gold: one gold span allows at most one prediction (strict matching)
            matched_predictions = set()
            article_exact_matches = 0
            article_over_extractions = 0
            article_under_extractions = 0
            article_hallucinations = 0
            article_merged_commands = 0

            # Match each gold span to at most one prediction
            for annotation in annotations:
                ann_text = annotation.selected_text
                ann_normalized = normalize_span(ann_text, mode="strict")

                # Find best matching prediction (exact match required for gold)
                best_match_idx = None
                best_match_text = None

                for pred_idx, pred_text in enumerate(predicted_spans):
                    if pred_idx in matched_predictions:
                        continue

                    pred_normalized = normalize_span(pred_text, mode="strict")

                    # Check for exact match (strict normalization)
                    if is_exact_match(pred_normalized, ann_normalized, mode="strict"):
                        best_match_idx = pred_idx
                        best_match_text = pred_text
                        break

                if best_match_idx is not None:
                    article_exact_matches += 1
                    total_exact_matches += 1
                    matched_predictions.add(best_match_idx)

                    # Check for over/under extraction (strict comparison)
                    pred_normalized = normalize_span(best_match_text, mode="strict")
                    if len(pred_normalized) > len(ann_normalized):
                        article_over_extractions += 1
                        total_over_extractions += 1
                    elif len(pred_normalized) < len(ann_normalized):
                        article_under_extractions += 1
                        total_under_extractions += 1
                else:
                    # No exact match - check for potential merged commands
                    # (prediction spans multiple gold commands)
                    for pred_idx, pred_text in enumerate(predicted_spans):
                        if pred_idx in matched_predictions:
                            continue
                        pred_normalized = normalize_span(pred_text, mode="strict")
                        # Heuristic: if prediction is significantly longer, might be merged
                        if len(pred_normalized) > len(ann_normalized) * 1.5:
                            article_merged_commands += 1
                            total_merged_commands += 1
                            failure_taxonomy["merged_commands"][article_id] += 1
                            break

            # Count hallucinations (unmatched predictions)
            for pred_idx in range(len(predicted_spans)):
                if pred_idx not in matched_predictions:
                    article_hallucinations += 1
                    total_hallucinations += 1

            # Check for truncated spans (predictions shorter than gold)
            for annotation in annotations:
                ann_text = annotation.selected_text
                ann_normalized = normalize_span(ann_text, mode="strict")
                for pred_text in predicted_spans:
                    pred_normalized = normalize_span(pred_text, mode="strict")
                    # If prediction is significantly shorter, might be truncated
                    if len(pred_normalized) < len(ann_normalized) * 0.7:
                        failure_taxonomy["truncated_span"][article_id] += 1
                        break

            # Check for argument hallucination (predictions with extra args not in gold)
            # This is detected when prediction has extra tokens not in any gold span
            for pred_text in predicted_spans:
                pred_normalized = normalize_span(pred_text, mode="strict")
                pred_tokens = set(pred_normalized.split())
                found_match = False
                for ann_text in gold_spans:
                    ann_normalized = normalize_span(ann_text, mode="strict")
                    ann_tokens = set(ann_normalized.split())
                    if pred_tokens.issubset(ann_tokens) or ann_tokens.issubset(pred_tokens):
                        found_match = True
                        break
                if not found_match and len(pred_tokens) > 3:  # Only flag substantial predictions
                    failure_taxonomy["argument_hallucination"][article_id] += 1

            # Article-level zero-FP check
            article_zero_fp = article_hallucinations == 0
            if article_zero_fp:
                articles_with_zero_fp += 1
            else:
                articles_failing_zero_fp.append(article_id)

            # Track worst-case indicators
            if article_merged_commands > max_merged_commands_per_article:
                max_merged_commands_per_article = article_merged_commands

            article_results.append(
                {
                    "article_id": article_id,
                    "gold_count": len(gold_spans),
                    "pred_count": len(predicted_spans),
                    "exact_matches": article_exact_matches,
                    "over_extractions": article_over_extractions,
                    "under_extractions": article_under_extractions,
                    "hallucinations": article_hallucinations,
                    "merged_commands": article_merged_commands,
                    "zero_fp_pass": article_zero_fp,
                }
            )

        # Compute rates (per gold span for some, per article for others)
        exact_match_rate = total_exact_matches / total_gold_spans if total_gold_spans > 0 else 0.0
        over_extraction_rate = total_over_extractions / total_gold_spans if total_gold_spans > 0 else 0.0
        under_extraction_rate = total_under_extractions / total_gold_spans if total_gold_spans > 0 else 0.0
        hallucination_rate = total_hallucinations / total_gold_spans if total_gold_spans > 0 else 0.0
        multi_command_merge_rate = total_merged_commands / total_gold_spans if total_gold_spans > 0 else 0.0

        # Article-level metrics
        zero_fp_pass_rate = articles_with_zero_fp / total_articles if total_articles > 0 else 0.0

        # Store failure taxonomy
        self._store_failure_taxonomy(session, failure_taxonomy, article_results)

        return {
            "usage": "gold",
            "exact_match_rate": exact_match_rate,
            "over_extraction_rate": over_extraction_rate,
            "under_extraction_rate": under_extraction_rate,
            "hallucination_rate": hallucination_rate,
            "multi_command_merge_rate": multi_command_merge_rate,
            "zero_fp_pass_rate": zero_fp_pass_rate,
            "sample_count": total_gold_spans,
            "total_articles": total_articles,
            "exact_matches": total_exact_matches,
            "over_extractions": total_over_extractions,
            "under_extractions": total_under_extractions,
            "hallucinations": total_hallucinations,
            "multi_command_merges": total_merged_commands,
            "articles_with_zero_fp": articles_with_zero_fp,
            "articles_failing_zero_fp": len(articles_failing_zero_fp),
            "articles_failing_zero_fp_ids": articles_failing_zero_fp[:20],  # Limit for response size
            "max_merged_commands_per_article": max_merged_commands_per_article,
            "articles_with_zero_gold": articles_with_zero_gold,
            "article_results": article_results,  # Per-article breakdown
        }

    def _store_failure_taxonomy(
        self,
        session: Session,
        failure_taxonomy: dict[str, dict[int, int]],
        article_results: list[dict[str, Any]],
    ) -> None:
        """Store failure taxonomy in database for inspection."""
        from datetime import datetime

        for failure_type, article_counts in failure_taxonomy.items():
            for article_id, count in article_counts.items():
                # Find article result for additional context
                article_result = next((r for r in article_results if r["article_id"] == article_id), None)

                failure_record = ObservableEvaluationFailureTable(
                    model_name=self.model_name,
                    model_version=self.model_version,
                    observable_type=self.observable_type,
                    article_id=article_id,
                    failure_type=failure_type,
                    failure_count=count,
                    zero_fp_pass=article_result["zero_fp_pass"] if article_result else True,
                    total_predictions=article_result["pred_count"] if article_result else 0,
                    total_gold_spans=article_result["gold_count"] if article_result else 0,
                    computed_at=datetime.now(),
                )
                session.add(failure_record)

        session.commit()
        logger.info(f"Stored failure taxonomy: {sum(len(v) for v in failure_taxonomy.values())} failure records")

    def _empty_metrics(self, usage: str) -> dict[str, Any]:
        """Return empty metrics structure."""
        if usage == "eval":
            return {
                "usage": "eval",
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
                "token_overlap_f1": 0.0,
                "avg_span_length_delta": 0.0,
                "false_positive_rate_per_document": 0.0,
                "sample_count": 0,
                "total_articles": 0,
            }
        return {
            "usage": "gold",
            "exact_match_rate": 0.0,
            "over_extraction_rate": 0.0,
            "under_extraction_rate": 0.0,
            "hallucination_rate": 0.0,
            "multi_command_merge_rate": 0.0,
            "zero_fp_pass_rate": 0.0,
            "sample_count": 0,
            "total_articles": 0,
            "articles_failing_zero_fp": 0,
            "max_merged_commands_per_article": 0,
        }
