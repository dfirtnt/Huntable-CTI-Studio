"""
Evaluation Tracker Service.

Provides functionality to query evaluation history, generate comparisons,
and track improvements over time.
"""

import logging
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.database.models import AgentEvaluationTable

logger = logging.getLogger(__name__)


def _compare_metrics(baseline_metrics: dict[str, Any], current_metrics: dict[str, Any]) -> dict[str, Any]:
    """Compare two metrics dicts, bucketing numeric differences into improvements/degradations/unchanged."""
    comparison: dict[str, Any] = {
        "baseline": baseline_metrics,
        "current": current_metrics,
        "improvements": {},
        "degradations": {},
        "unchanged": {},
    }

    def _compare_dicts(baseline: dict, current: dict, prefix: str = "") -> None:
        for key in set(list(baseline.keys()) + list(current.keys())):
            full_key = f"{prefix}.{key}" if prefix else key
            b_val = baseline.get(key)
            c_val = current.get(key)
            if isinstance(b_val, dict) and isinstance(c_val, dict):
                _compare_dicts(b_val, c_val, full_key)
            elif isinstance(b_val, (int, float)) and isinstance(c_val, (int, float)):
                diff = c_val - b_val
                pct = (diff / b_val * 100) if b_val != 0 else 0
                entry = {"baseline": b_val, "current": c_val, "diff": diff, "pct_change": pct}
                if abs(diff) < 0.001:
                    comparison["unchanged"][full_key] = entry
                elif diff > 0:
                    comparison["improvements"][full_key] = entry
                else:
                    comparison["degradations"][full_key] = entry

    _compare_dicts(baseline_metrics or {}, current_metrics or {})
    return comparison


class EvaluationTracker:
    """
    Tracks and compares agent evaluations over time.
    """

    def __init__(self, db_session: Session):
        """
        Initialize evaluation tracker.

        Args:
            db_session: Database session
        """
        self.db_session = db_session

    def get_evaluation_history(self, agent_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get evaluation history for an agent.

        Args:
            agent_name: Name of the agent
            limit: Maximum number of evaluations to return

        Returns:
            List of evaluation records
        """
        evaluations = (
            self.db_session.query(AgentEvaluationTable)
            .filter(AgentEvaluationTable.agent_name == agent_name)
            .order_by(desc(AgentEvaluationTable.created_at))
            .limit(limit)
            .all()
        )

        return [
            {
                "id": eval.id,
                "agent_name": eval.agent_name,
                "evaluation_type": eval.evaluation_type,
                "model_version": eval.model_version,
                "workflow_config_version": eval.workflow_config_version,
                "test_dataset_path": eval.test_dataset_path,
                "total_articles": eval.total_articles,
                "metrics": eval.metrics,
                "created_at": eval.created_at.isoformat() if eval.created_at else None,
                "evaluated_at": eval.evaluated_at.isoformat() if eval.evaluated_at else None,
            }
            for eval in evaluations
        ]

    def get_latest_evaluation(self, agent_name: str, evaluation_type: str | None = None) -> dict[str, Any] | None:
        """
        Get latest evaluation for an agent.

        Args:
            agent_name: Name of the agent
            evaluation_type: Optional filter by evaluation type

        Returns:
            Latest evaluation record or None
        """
        query = self.db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.agent_name == agent_name)

        if evaluation_type:
            query = query.filter(AgentEvaluationTable.evaluation_type == evaluation_type)

        evaluation = query.order_by(desc(AgentEvaluationTable.created_at)).first()

        if not evaluation:
            return None

        return {
            "id": evaluation.id,
            "agent_name": evaluation.agent_name,
            "evaluation_type": evaluation.evaluation_type,
            "model_version": evaluation.model_version,
            "workflow_config_version": evaluation.workflow_config_version,
            "test_dataset_path": evaluation.test_dataset_path,
            "total_articles": evaluation.total_articles,
            "metrics": evaluation.metrics,
            "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
            "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
        }

    def compare_evaluations(self, baseline_id: int, current_id: int) -> dict[str, Any]:
        """
        Compare two evaluations.

        Args:
            baseline_id: ID of baseline evaluation
            current_id: ID of current evaluation

        Returns:
            Dictionary with comparison results
        """
        baseline = self.db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.id == baseline_id).first()

        current = self.db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.id == current_id).first()

        if not baseline or not current:
            raise ValueError("One or both evaluations not found")

        if baseline.agent_name != current.agent_name:
            raise ValueError("Cannot compare evaluations from different agents")

        comparison = _compare_metrics(baseline.metrics, current.metrics)

        return {
            "baseline": {
                "id": baseline.id,
                "evaluation_type": baseline.evaluation_type,
                "model_version": baseline.model_version,
                "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
                "metrics": baseline.metrics,
            },
            "current": {
                "id": current.id,
                "evaluation_type": current.evaluation_type,
                "model_version": current.model_version,
                "created_at": current.created_at.isoformat() if current.created_at else None,
                "metrics": current.metrics,
            },
            "comparison": comparison,
        }

    def get_improvement_trends(
        self, agent_name: str, metric_key: str, evaluation_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Get improvement trends for a specific metric over time.

        Args:
            agent_name: Name of the agent
            metric_key: Key of metric to track (supports dot notation, e.g., "json_validity_rate")
            evaluation_type: Optional filter by evaluation type

        Returns:
            List of {timestamp, value} dictionaries
        """
        query = self.db_session.query(AgentEvaluationTable).filter(AgentEvaluationTable.agent_name == agent_name)

        if evaluation_type:
            query = query.filter(AgentEvaluationTable.evaluation_type == evaluation_type)

        evaluations = query.order_by(AgentEvaluationTable.created_at).all()

        trends = []

        for eval_record in evaluations:
            # Navigate nested metric structure
            value = eval_record.metrics
            for key_part in metric_key.split("."):
                if isinstance(value, dict):
                    value = value.get(key_part)
                else:
                    value = None
                    break

            if value is not None:
                trends.append(
                    {
                        "timestamp": eval_record.created_at.isoformat() if eval_record.created_at else None,
                        "value": value,
                        "evaluation_id": eval_record.id,
                        "evaluation_type": eval_record.evaluation_type,
                        "model_version": eval_record.model_version,
                    }
                )

        return trends
