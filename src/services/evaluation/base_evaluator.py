"""
Base evaluation interface for all agent evaluators.

Provides common interface and standardized output schema for tracking
agent performance improvements over time.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


class BaseAgentEvaluator(ABC):
    """
    Abstract base class for agent evaluators.
    
    All agent-specific evaluators should extend this class to ensure
    consistent interface and output schema.
    """
    
    def __init__(
        self,
        agent_name: str,
        model_version: Optional[str] = None,
        evaluation_type: str = "baseline",
        workflow_config_version: Optional[int] = None
    ):
        """
        Initialize base evaluator.
        
        Args:
            agent_name: Name of the agent (e.g., "ExtractAgent", "SigmaAgent")
            model_version: Version/identifier of the model being evaluated
            evaluation_type: Type of evaluation (e.g., "baseline", "finetuned", "v2")
            workflow_config_version: Version of workflow config used
        """
        self.agent_name = agent_name
        self.model_version = model_version
        self.evaluation_type = evaluation_type
        self.workflow_config_version = workflow_config_version
        self.results: List[Dict[str, Any]] = []
        self.metrics: Dict[str, Any] = {}
        self.timestamp = datetime.now()
        
    @abstractmethod
    async def evaluate_dataset(
        self,
        test_data_path: Path,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Evaluate agent on test dataset.
        
        Args:
            test_data_path: Path to test dataset JSON file
            **kwargs: Agent-specific evaluation parameters
            
        Returns:
            Dictionary with evaluation results and metrics
        """
        pass
    
    @abstractmethod
    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate aggregate metrics from evaluation results.
        
        Returns:
            Dictionary with calculated metrics
        """
        pass
    
    def save_results(
        self,
        output_path: Optional[Path] = None,
        save_to_db: bool = False,
        db_session = None
    ) -> Dict[str, Any]:
        """
        Save evaluation results to file and/or database.
        
        Args:
            output_path: Optional path to save JSON results file
            save_to_db: Whether to save to database
            db_session: Database session (required if save_to_db=True)
            
        Returns:
            Dictionary with save results including evaluation_id if saved to DB
        """
        # Calculate metrics if not already calculated
        if not self.metrics:
            self.metrics = self.calculate_metrics()
        
        # Prepare full report
        report = {
            'agent_name': self.agent_name,
            'evaluation_type': self.evaluation_type,
            'model_version': self.model_version,
            'workflow_config_version': self.workflow_config_version,
            'timestamp': self.timestamp.isoformat(),
            'metrics': self.metrics,
            'results': self.results
        }
        
        # Save to file if path provided
        evaluation_id = None
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved evaluation results to: {output_path}")
        
        # Save to database if requested
        if save_to_db and db_session:
            from src.database.models import AgentEvaluationTable
            from sqlalchemy.orm import Session
            
            if not isinstance(db_session, Session):
                raise ValueError("db_session must be a SQLAlchemy Session")
            
            # Extract article IDs from results
            article_ids = []
            test_dataset_path = None
            if output_path:
                test_dataset_path = str(output_path)
            
            # Try to extract article IDs from results
            for result in self.results:
                if 'article_id' in result:
                    article_ids.append(result['article_id'])
            
            # Create database record
            eval_record = AgentEvaluationTable(
                agent_name=self.agent_name,
                evaluation_type=self.evaluation_type,
                model_version=self.model_version,
                workflow_config_version=self.workflow_config_version,
                test_dataset_path=test_dataset_path,
                article_ids=article_ids if article_ids else None,
                total_articles=len(self.results),
                metrics=self.metrics,
                results=self.results if len(json.dumps(self.results)) < 1000000 else None  # Skip if too large
            )
            
            db_session.add(eval_record)
            db_session.commit()
            db_session.refresh(eval_record)
            evaluation_id = eval_record.id
            logger.info(f"Saved evaluation to database with ID: {evaluation_id}")
        
        return {
            'saved': True,
            'output_path': str(output_path) if output_path else None,
            'evaluation_id': evaluation_id,
            'report': report
        }
    
    def compare_with_baseline(
        self,
        baseline_metrics: Dict[str, Any],
        current_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compare current evaluation metrics with baseline.
        
        Args:
            baseline_metrics: Metrics from baseline evaluation
            current_metrics: Current metrics (uses self.metrics if None)
            
        Returns:
            Dictionary with comparison results showing improvements/degradations
        """
        if current_metrics is None:
            if not self.metrics:
                self.metrics = self.calculate_metrics()
            current_metrics = self.metrics
        
        comparison = {
            'baseline': baseline_metrics,
            'current': current_metrics,
            'improvements': {},
            'degradations': {},
            'unchanged': {}
        }
        
        # Compare numeric metrics
        def compare_metric(key: str, baseline_val: Any, current_val: Any):
            """Compare a single metric value."""
            if isinstance(baseline_val, (int, float)) and isinstance(current_val, (int, float)):
                diff = current_val - baseline_val
                pct_change = (diff / baseline_val * 100) if baseline_val != 0 else 0
                
                if abs(diff) < 0.001:  # Essentially unchanged
                    comparison['unchanged'][key] = {
                        'baseline': baseline_val,
                        'current': current_val,
                        'diff': diff,
                        'pct_change': pct_change
                    }
                elif diff > 0:  # Improvement
                    comparison['improvements'][key] = {
                        'baseline': baseline_val,
                        'current': current_val,
                        'diff': diff,
                        'pct_change': pct_change
                    }
                else:  # Degradation
                    comparison['degradations'][key] = {
                        'baseline': baseline_val,
                        'current': current_val,
                        'diff': diff,
                        'pct_change': pct_change
                    }
        
        # Recursively compare nested dictionaries
        def compare_dicts(baseline: Dict, current: Dict, prefix: str = ""):
            for key in set(list(baseline.keys()) + list(current.keys())):
                full_key = f"{prefix}.{key}" if prefix else key
                baseline_val = baseline.get(key)
                current_val = current.get(key)
                
                if isinstance(baseline_val, dict) and isinstance(current_val, dict):
                    compare_dicts(baseline_val, current_val, full_key)
                else:
                    compare_metric(full_key, baseline_val, current_val)
        
        compare_dicts(baseline_metrics, current_metrics)
        
        return comparison
    
    def get_standardized_output(self) -> Dict[str, Any]:
        """
        Get standardized output schema for this evaluation.
        
        Returns:
            Dictionary with standardized evaluation output
        """
        if not self.metrics:
            self.metrics = self.calculate_metrics()
        
        return {
            'agent_name': self.agent_name,
            'evaluation_type': self.evaluation_type,
            'model_version': self.model_version,
            'workflow_config_version': self.workflow_config_version,
            'timestamp': self.timestamp.isoformat(),
            'metrics': self.metrics,
            'total_samples': len(self.results),
            'results': self.results
        }

