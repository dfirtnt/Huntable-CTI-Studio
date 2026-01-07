"""
Evaluation pipeline for observable extraction models.

Orchestrates the full evaluation workflow: load annotations, run inference,
compute metrics, and persist results.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from sqlalchemy.orm import Session

from src.database.models import ObservableModelMetricsTable
from src.services.observable_evaluation.evaluator import ObservableModelEvaluator

logger = logging.getLogger(__name__)


class ObservableEvaluationPipeline:
    """Pipeline for evaluating observable extraction models."""
    
    def __init__(self, session: Session):
        """
        Initialize the pipeline.
        
        Args:
            session: Database session
        """
        self.session = session
    
    def run_evaluation(
        self,
        model_name: str,
        model_version: str,
        observable_type: str,
        usages: List[str] = None,
        model_path: Optional[str] = None,
        overlap_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Run evaluation for a model on specified dataset usages.
        
        Args:
            model_name: Name of the model (e.g., "CMD")
            model_version: Version identifier
            observable_type: Type of observable (e.g., "CMD", "PROC_LINEAGE")
            usages: List of dataset usages to evaluate ("eval", "gold", or both)
            model_path: Optional path to model (if None, auto-detects)
            overlap_threshold: Minimum token overlap for eval true positive
            
        Returns:
            Dictionary with evaluation results and persisted metric IDs
        """
        if usages is None:
            usages = ["eval", "gold"]
        
        evaluator = ObservableModelEvaluator(
            model_name=model_name,
            model_version=model_version,
            observable_type=observable_type,
            overlap_threshold=overlap_threshold,
        )
        
        results = {
            "model_name": model_name,
            "model_version": model_version,
            "observable_type": observable_type,
            "evaluations": {},
            "metric_ids": [],
        }
        
        for usage in usages:
            if usage not in ("eval", "gold"):
                logger.warning(f"Skipping invalid usage: {usage}")
                continue
            
            try:
                logger.info(f"Evaluating {model_name} v{model_version} on {observable_type} {usage} dataset...")
                metrics = evaluator.evaluate(self.session, usage, model_path)
                
                # Persist metrics
                metric_ids = self._persist_metrics(
                    model_name=model_name,
                    model_version=model_version,
                    observable_type=observable_type,
                    usage=usage,
                    metrics=metrics,
                )
                
                results["evaluations"][usage] = metrics
                results["metric_ids"].extend(metric_ids)
                
                logger.info(f"Completed {usage} evaluation. Sample count: {metrics.get('sample_count', 0)}")
                
            except Exception as e:
                logger.error(f"Error evaluating {usage} dataset: {e}", exc_info=True)
                results["evaluations"][usage] = {"error": str(e)}
        
        return results
    
    def _persist_metrics(
        self,
        model_name: str,
        model_version: str,
        observable_type: str,
        usage: str,
        metrics: Dict[str, Any],
    ) -> List[int]:
        """
        Persist metrics to the database.
        
        Args:
            model_name: Name of the model
            model_version: Version identifier
            observable_type: Type of observable
            usage: Dataset usage ("eval" or "gold")
            metrics: Dictionary of computed metrics
            
        Returns:
            List of inserted metric IDs
        """
        metric_ids = []
        sample_count = metrics.get("sample_count", 0)
        computed_at = datetime.utcnow()
        
        if usage == "eval":
            # Eval metrics
            metric_mappings = {
                "precision": "precision",
                "recall": "recall",
                "f1_score": "f1_score",
                "token_overlap_f1": "token_overlap_f1",
                "avg_span_length_delta": "avg_span_length_delta",
                "false_positive_rate_per_document": "false_positive_rate_per_document",
                "total_articles": "total_articles",
            }
        else:  # gold
            # Gold metrics (including worst-case indicators)
            metric_mappings = {
                "exact_match_rate": "exact_match_rate",
                "over_extraction_rate": "over_extraction_rate",
                "under_extraction_rate": "under_extraction_rate",
                "hallucination_rate": "hallucination_rate",
                "multi_command_merge_rate": "multi_command_merge_rate",
                "zero_fp_pass_rate": "zero_fp_pass_rate",
                "total_articles": "total_articles",
                "articles_failing_zero_fp": "articles_failing_zero_fp",
                "max_merged_commands_per_article": "max_merged_commands_per_article",
                "articles_with_zero_gold": "articles_with_zero_gold",
            }
        
        for metric_key, metric_name in metric_mappings.items():
            if metric_key not in metrics:
                continue
            
            metric_value = metrics[metric_key]
            if metric_value is None:
                continue
            
            metric_row = ObservableModelMetricsTable(
                model_name=model_name,
                model_version=model_version,
                observable_type=observable_type,
                dataset_usage=usage,
                metric_name=metric_name,
                metric_value=float(metric_value),
                sample_count=sample_count,
                computed_at=computed_at,
            )
            
            self.session.add(metric_row)
            self.session.flush()
            metric_ids.append(metric_row.id)
        
        self.session.commit()
        logger.info(f"Persisted {len(metric_ids)} metrics for {model_name} v{model_version} ({observable_type}, {usage})")
        
        return metric_ids
    
    def get_metrics(
        self,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        observable_type: Optional[str] = None,
        usage: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve metrics from the database.
        
        Args:
            model_name: Filter by model name
            model_version: Filter by model version
            observable_type: Filter by observable type
            usage: Filter by dataset usage ("eval" or "gold")
            limit: Maximum number of results
            
        Returns:
            List of metric dictionaries
        """
        from sqlalchemy import select
        
        query = select(ObservableModelMetricsTable)
        
        if model_name:
            query = query.where(ObservableModelMetricsTable.model_name == model_name)
        if model_version:
            query = query.where(ObservableModelMetricsTable.model_version == model_version)
        if observable_type:
            query = query.where(ObservableModelMetricsTable.observable_type == observable_type)
        if usage:
            query = query.where(ObservableModelMetricsTable.dataset_usage == usage)
        
        query = query.order_by(ObservableModelMetricsTable.computed_at.desc()).limit(limit)
        
        results = self.session.execute(query).scalars().all()
        
        return [
            {
                "id": r.id,
                "model_name": r.model_name,
                "model_version": r.model_version,
                "observable_type": r.observable_type,
                "dataset_usage": r.dataset_usage,
                "metric_name": r.metric_name,
                "metric_value": r.metric_value,
                "sample_count": r.sample_count,
                "computed_at": r.computed_at.isoformat() if r.computed_at else None,
            }
            for r in results
        ]

