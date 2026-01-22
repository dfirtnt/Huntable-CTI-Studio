"""
SIGMA Agent Evaluator implementing E2E-SIG framework.

Implements 7-stage evaluation:
1. Structural Validation (pySigma)
2. Extended Structural Checks
3. Normalized Behavioral Core Extraction
4. Semantic Equivalence Scoring
5. Huntability/Detection Utility Score
6. Cross-Run Stability (Variance Testing)
7. Novelty Detection (Repo Comparison)
"""

import logging
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path

from src.services.evaluation.base_evaluator import BaseAgentEvaluator
from src.services.sigma_extended_validator import SigmaExtendedValidator, ExtendedValidationResult
from src.services.sigma_behavioral_normalizer import SigmaBehavioralNormalizer, BehavioralCore
from src.services.sigma_semantic_scorer import SigmaSemanticScorer, SemanticComparisonResult
from src.services.sigma_huntability_scorer import SigmaHuntabilityScorer, HuntabilityScore
from src.services.sigma_stability_tester import SigmaStabilityTester, StabilityResult
from src.services.sigma_novelty_detector import SigmaNoveltyDetector, NoveltyResult

logger = logging.getLogger(__name__)


class SigmaAgentEvaluator(BaseAgentEvaluator):
    """
    Evaluator for SIGMA Agent using E2E-SIG framework.
    """
    
    def __init__(
        self,
        model_version: Optional[str] = None,
        evaluation_type: str = "baseline",
        workflow_config_version: Optional[int] = None,
        llm_service=None,
        db_session=None
    ):
        """
        Initialize SIGMA agent evaluator.
        
        Args:
            model_version: Model version identifier
            evaluation_type: Type of evaluation (baseline, finetuned, etc.)
            workflow_config_version: Workflow config version
            llm_service: LLM service for semantic scoring (optional)
            db_session: Database session for novelty detection (optional)
        """
        super().__init__(
            agent_name="SigmaAgent",
            model_version=model_version,
            evaluation_type=evaluation_type,
            workflow_config_version=workflow_config_version
        )
        
        self.extended_validator = SigmaExtendedValidator()
        self.normalizer = SigmaBehavioralNormalizer()
        self.semantic_scorer = SigmaSemanticScorer(use_llm_judge=llm_service is not None, llm_service=llm_service)
        self.huntability_scorer = SigmaHuntabilityScorer()
        self.stability_tester = SigmaStabilityTester(num_runs=5)
        self.novelty_detector = SigmaNoveltyDetector()
        self.db_session = db_session
    
    async def evaluate_dataset(
        self,
        test_data_path: Path,
        generate_rule_func=None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Evaluate SIGMA agent on test dataset.
        
        Args:
            test_data_path: Path to test dataset JSON file
            generate_rule_func: Optional function to generate rules
                               Signature: async def func(article_id: int) -> str
            **kwargs: Additional evaluation parameters
            
        Returns:
            Dictionary with evaluation results
        """
        import json
        
        # Load test data
        with open(test_data_path, 'r') as f:
            test_data = json.load(f)
        
        results = []
        
        for example in test_data:
            article_id = example.get('article_id')
            expected_rules = example.get('expected_sigma_rules', [])
            reference_rules = example.get('reference_rules', [])
            
            if not article_id:
                logger.warning("Skipping example without article_id")
                continue
            
            # Generate rule if function provided
            generated_rule = None
            if generate_rule_func:
                try:
                    generated_rule = await generate_rule_func(article_id)
                except Exception as e:
                    logger.error(f"Failed to generate rule for article {article_id}: {e}")
                    results.append({
                        'article_id': article_id,
                        'error': str(e),
                        'evaluation': None
                    })
                    continue
            
            # Use provided rule or generated rule
            rule_yaml = example.get('generated_rule') or generated_rule
            
            if not rule_yaml:
                logger.warning(f"No rule provided for article {article_id}")
                results.append({
                    'article_id': article_id,
                    'error': 'No rule provided',
                    'evaluation': None
                })
                continue
            
            # Evaluate rule
            evaluation = await self._evaluate_single_rule(
                rule_yaml,
                reference_rule=reference_rules[0] if reference_rules else None,
                article_id=article_id
            )
            
            results.append({
                'article_id': article_id,
                'rule_yaml': rule_yaml,
                'evaluation': evaluation
            })
        
        self.results = results
        return self.calculate_metrics()
    
    async def _evaluate_single_rule(
        self,
        rule_yaml: str,
        reference_rule: Optional[str] = None,
        article_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single SIGMA rule through all 7 stages.
        
        Args:
            rule_yaml: Generated SIGMA rule (YAML string)
            reference_rule: Optional reference rule for comparison
            article_id: Optional article ID for stability testing
            
        Returns:
            Dictionary with complete evaluation results
        """
        # Stage 1 & 2: Structural Validation
        structural_result = self.extended_validator.validate(rule_yaml)
        
        # If structural validation fails, return early
        if not structural_result.final_pass:
            return {
                'structural_validation': {
                    'pySigma': {
                        'passed': structural_result.pySigma_passed,
                        'errors': structural_result.pySigma_errors
                    },
                    'extended_checks': {
                        'telemetry_feasible': structural_result.telemetry_feasible,
                        'condition_valid': structural_result.condition_valid,
                        'pattern_safe': structural_result.pattern_safe,
                        'ioc_leakage': structural_result.ioc_leakage,
                        'field_conformance': structural_result.field_conformance
                    },
                    'final_pass': False,
                    'errors': structural_result.errors
                },
                'normalized_core': None,
                'semantic_comparison': None,
                'huntability_score': None,
                'stability': None,
                'novelty': None
            }
        
        # Stage 3: Normalized Behavioral Core
        behavioral_core = self.normalizer.extract_behavioral_core(rule_yaml)
        
        # Stage 4: Semantic Equivalence (if reference provided)
        semantic_comparison = None
        if reference_rule:
            try:
                semantic_comparison = await self.semantic_scorer.compare_rules(
                    rule_yaml, reference_rule
                )
            except Exception as e:
                logger.error(f"Semantic comparison failed: {e}")
        
        # Stage 5: Huntability Score
        try:
            rule_data = yaml.safe_load(rule_yaml)
            huntability_score = self.huntability_scorer.score_rule(rule_yaml, rule_data)
        except Exception as e:
            logger.error(f"Huntability scoring failed: {e}")
            huntability_score = None
        
        # Stage 6: Stability Testing (if article_id provided and generate function available)
        stability = None
        # Note: Stability testing requires a generate function, which should be passed
        # through evaluate_dataset. Skipping for single rule evaluation.
        
        # Stage 7: Novelty Detection
        novelty = None
        if self.db_session:
            try:
                novelty = self.novelty_detector.detect_novelty(rule_yaml, self.db_session)
            except Exception as e:
                logger.error(f"Novelty detection failed: {e}")
        
        return {
            'structural_validation': {
                'pySigma': {
                    'passed': structural_result.pySigma_passed,
                    'errors': structural_result.pySigma_errors
                },
                'extended_checks': {
                    'telemetry_feasible': structural_result.telemetry_feasible,
                    'condition_valid': structural_result.condition_valid,
                    'pattern_safe': structural_result.pattern_safe,
                    'ioc_leakage': structural_result.ioc_leakage,
                    'field_conformance': structural_result.field_conformance
                },
                'final_pass': structural_result.final_pass
            },
            'normalized_core': {
                'behavior_selectors': behavioral_core.behavior_selectors,
                'core_hash': behavioral_core.core_hash,
                'selector_count': behavioral_core.selector_count
            },
            'semantic_comparison': {
                'similarity_score': semantic_comparison.similarity_score if semantic_comparison else None,
                'missing_behaviors': semantic_comparison.missing_behaviors if semantic_comparison else None,
                'extraneous_behaviors': semantic_comparison.extraneous_behaviors if semantic_comparison else None
            } if semantic_comparison else None,
            'huntability_score': {
                'score': huntability_score.score if huntability_score else None,
                'false_positive_risk': huntability_score.false_positive_risk if huntability_score else None,
                'coverage_notes': huntability_score.coverage_notes if huntability_score else None
            } if huntability_score else None,
            'stability': stability,
            'novelty': {
                'status': novelty.novelty_status if novelty else None,
                'novelty_score': novelty.novelty_score if novelty else None,
                'closest_match_id': novelty.closest_match_id if novelty else None
            } if novelty else None
        }
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """Calculate aggregate metrics from evaluation results."""
        if not self.results:
            return {}
        
        valid_results = [r for r in self.results if r.get('evaluation') and not r.get('error')]
        
        if not valid_results:
            return {
                'total_articles': len(self.results),
                'valid_results': 0,
                'errors': len([r for r in self.results if r.get('error')])
            }
        
        evaluations = [r['evaluation'] for r in valid_results]
        
        # Structural validation metrics
        structural_passed = sum(
            1 for e in evaluations
            if e.get('structural_validation', {}).get('final_pass', False)
        )
        
        # Huntability metrics
        huntability_scores = [
            e.get('huntability_score', {}).get('score')
            for e in evaluations
            if e.get('huntability_score', {}).get('score') is not None
        ]
        
        # Semantic similarity metrics
        semantic_scores = [
            e.get('semantic_comparison', {}).get('similarity_score')
            for e in evaluations
            if e.get('semantic_comparison', {}).get('similarity_score') is not None
        ]
        
        # Novelty metrics
        novelty_scores = [
            e.get('novelty', {}).get('novelty_score')
            for e in evaluations
            if e.get('novelty') and isinstance(e.get('novelty'), dict) and e.get('novelty', {}).get('novelty_score') is not None
        ]
        
        metrics = {
            'total_articles': len(self.results),
            'valid_results': len(valid_results),
            'errors': len([r for r in self.results if r.get('error')]),
            'structural_validation_pass_rate': structural_passed / len(valid_results) if valid_results else 0,
            'avg_huntability_score': sum(huntability_scores) / len(huntability_scores) if huntability_scores else None,
            'avg_semantic_similarity': sum(semantic_scores) / len(semantic_scores) if semantic_scores else None,
            'novelty_distribution': {
                'duplicates': sum(1 for s in novelty_scores if s == 0),
                'variants': sum(1 for s in novelty_scores if s == 1),
                'novel': sum(1 for s in novelty_scores if s == 2)
            } if novelty_scores else None
        }
        
        self.metrics = metrics
        return metrics

