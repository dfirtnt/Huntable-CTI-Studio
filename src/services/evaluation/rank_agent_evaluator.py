"""
Rank Agent Evaluator.

Evaluates Rank Agent performance on test datasets.
"""

import logging
import json
import statistics
from typing import Dict, List, Any, Optional
from pathlib import Path

from src.services.evaluation.base_evaluator import BaseAgentEvaluator
from src.database.models import ArticleTable
from src.services.llm_service import LLMService
from src.database.manager import DatabaseManager

logger = logging.getLogger(__name__)


class RankAgentEvaluator(BaseAgentEvaluator):
    """
    Evaluator for Rank Agent.
    
    Metrics:
    - Score distribution (mean, std, min, max)
    - Threshold accuracy (correctly identifies huntable articles)
    - Reasoning quality (if available)
    - Processing time
    """
    
    def __init__(
        self,
        model_version: Optional[str] = None,
        evaluation_type: str = "baseline",
        workflow_config_version: Optional[int] = None,
        ranking_threshold: float = 6.0
    ):
        """
        Initialize Rank Agent evaluator.
        
        Args:
            model_version: Model version identifier
            evaluation_type: Type of evaluation
            workflow_config_version: Workflow config version
            ranking_threshold: Threshold for considering article huntable (default: 6.0)
        """
        super().__init__(
            agent_name="RankAgent",
            model_version=model_version,
            evaluation_type=evaluation_type,
            workflow_config_version=workflow_config_version
        )
        self.ranking_threshold = ranking_threshold
    
    async def evaluate_dataset(
        self,
        test_data_path: Path,
        llm_service: Optional[LLMService] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Evaluate Rank Agent on test dataset.
        
        Args:
            test_data_path: Path to test dataset JSON file
            llm_service: LLM service instance
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with evaluation results
        """
        # Load test data
        with open(test_data_path, 'r') as f:
            test_data = json.load(f)
        
        # Initialize services if not provided
        if not llm_service:
            llm_service = LLMService()
        
        # Get database session
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        results = []
        
        try:
            for example in test_data:
                article_id = example.get('article_id')
                expected_score = example.get('expected_score')
                ground_truth_hunt_score = example.get('ground_truth_hunt_score')
                
                if not article_id:
                    logger.warning("Skipping example without article_id")
                    continue
                
                # Get article from database
                article = db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
                
                if not article:
                    logger.warning(f"Article {article_id} not found, skipping")
                    results.append({
                        'article_id': article_id,
                        'error': 'Article not found',
                        'evaluation': None
                    })
                    continue
                
                # Evaluate article
                try:
                    result = await self._evaluate_article(
                        article,
                        llm_service,
                        expected_score,
                        ground_truth_hunt_score
                    )
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error evaluating article {article_id}: {e}")
                    results.append({
                        'article_id': article_id,
                        'error': str(e),
                        'evaluation': None
                    })
        finally:
            db_session.close()
        
        self.results = results
        return self.calculate_metrics()
    
    async def _evaluate_article(
        self,
        article: ArticleTable,
        llm_service: LLMService,
        expected_score: Optional[float] = None,
        ground_truth_hunt_score: Optional[float] = None
    ) -> Dict[str, Any]:
        """Evaluate ranking on a single article."""
        import time
        
        # Get prompt config
        from src.services.workflow_trigger_service import WorkflowTriggerService
        from src.database.manager import DatabaseManager
        
        db_session = DatabaseManager().get_session()
        try:
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            
            if not config_obj or not config_obj.agent_prompts or "RankAgent" not in config_obj.agent_prompts:
                raise ValueError("RankAgent prompt not found in workflow config")
            
            agent_prompt_data = config_obj.agent_prompts["RankAgent"]
            
            # Get prompt template string
            rank_prompt_template = None
            if isinstance(agent_prompt_data.get("prompt"), str):
                rank_prompt_template = agent_prompt_data["prompt"]
        finally:
            db_session.close()
        
        # Run ranking
        start_time = time.time()
        try:
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=article.content or "",
                source=article.source.name if article.source else "Unknown",
                url=article.canonical_url or "",
                prompt_template=rank_prompt_template,
                article_id=article.id
            )
            processing_time = time.time() - start_time
        except Exception as e:
            return {
                'article_id': article.id,
                'error': str(e),
                'ranking_result': None,
                'evaluation': None
            }
        
        # Extract score and reasoning
        score = ranking_result.get('score') if isinstance(ranking_result, dict) else None
        reasoning = ranking_result.get('reasoning') if isinstance(ranking_result, dict) else None
        
        # Evaluate
        evaluation = self._evaluate_ranking_result(
            score,
            reasoning,
            expected_score,
            ground_truth_hunt_score,
            processing_time
        )
        
        return {
            'article_id': article.id,
            'title': article.title,
            'url': article.canonical_url or '',
            'ranking_result': ranking_result,
            'evaluation': evaluation,
            'expected_score': expected_score,
            'ground_truth_hunt_score': ground_truth_hunt_score
        }
    
    def _evaluate_ranking_result(
        self,
        score: Optional[float],
        reasoning: Optional[str],
        expected_score: Optional[float],
        ground_truth_hunt_score: Optional[float],
        processing_time: float
    ) -> Dict[str, Any]:
        """Evaluate a single ranking result."""
        evaluation = {
            'score': score,
            'score_valid': score is not None and isinstance(score, (int, float)),
            'has_reasoning': reasoning is not None and len(reasoning) > 0,
            'processing_time': processing_time,
            'above_threshold': score >= self.ranking_threshold if score is not None else None,
            'score_diff': None,
            'threshold_accuracy': None
        }
        
        # Compare with expected score
        if expected_score is not None and score is not None:
            evaluation['score_diff'] = abs(score - expected_score)
            evaluation['expected_score'] = expected_score
        
        # Compare with ground truth hunt score
        if ground_truth_hunt_score is not None:
            # Determine if article should be above threshold based on hunt score
            # Assume hunt score > 65 means article should be ranked above threshold
            should_be_above = ground_truth_hunt_score > 65
            is_above = score >= self.ranking_threshold if score is not None else False
            evaluation['threshold_accuracy'] = should_be_above == is_above
            evaluation['ground_truth_hunt_score'] = ground_truth_hunt_score
        
        # Reasoning quality (simple heuristic: length and structure)
        if reasoning:
            evaluation['reasoning_length'] = len(reasoning)
            evaluation['reasoning_has_structure'] = any(
                marker in reasoning.lower()
                for marker in ['because', 'therefore', 'however', 'additionally']
            )
        else:
            evaluation['reasoning_length'] = 0
            evaluation['reasoning_has_structure'] = False
        
        return evaluation
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate aggregate metrics from results."""
        if not self.results:
            return {}
        
        total = len(self.results)
        errors = sum(1 for r in self.results if r.get('error'))
        valid_results = [r for r in self.results if r.get('evaluation') and not r.get('error')]
        
        if not valid_results:
            return {
                'total_articles': total,
                'errors': errors,
                'valid_results': 0,
                'error_rate': errors / total if total > 0 else 0
            }
        
        evaluations = [r['evaluation'] for r in valid_results]
        
        # Score distribution
        scores = [e['score'] for e in evaluations if e.get('score') is not None]
        
        # Threshold accuracy
        threshold_accuracies = [
            e['threshold_accuracy']
            for e in evaluations
            if e.get('threshold_accuracy') is not None
        ]
        
        # Processing times
        processing_times = [e.get('processing_time', 0) for e in evaluations]
        
        metrics = {
            'total_articles': total,
            'errors': errors,
            'valid_results': len(valid_results),
            'error_rate': errors / total if total > 0 else 0,
            
            # Score distribution
            'score_mean': statistics.mean(scores) if scores else None,
            'score_std': statistics.stdev(scores) if len(scores) > 1 else None,
            'score_min': min(scores) if scores else None,
            'score_max': max(scores) if scores else None,
            'score_median': statistics.median(scores) if scores else None,
            
            # Threshold accuracy
            'threshold_accuracy': sum(threshold_accuracies) / len(threshold_accuracies) if threshold_accuracies else None,
            
            # Reasoning quality
            'reasoning_rate': sum(1 for e in evaluations if e.get('has_reasoning')) / len(evaluations),
            'avg_reasoning_length': statistics.mean([e.get('reasoning_length', 0) for e in evaluations]) if evaluations else 0,
            
            # Processing time
            'avg_processing_time': statistics.mean(processing_times) if processing_times else None,
            'min_processing_time': min(processing_times) if processing_times else None,
            'max_processing_time': max(processing_times) if processing_times else None
        }
        
        self.metrics = metrics
        return metrics

