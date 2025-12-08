"""
SIGMA Stability Tester.

Tests rule generation stability by running multiple evaluations
on the same input and measuring variance.
"""

import logging
import statistics
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from src.services.sigma_behavioral_normalizer import (
    SigmaBehavioralNormalizer,
    BehavioralCore
)
from src.services.sigma_semantic_scorer import (
    SigmaSemanticScorer,
    SemanticComparisonResult
)

logger = logging.getLogger(__name__)


@dataclass
class StabilityResult:
    """Result of stability testing."""
    unique_hashes: int
    semantic_variance: float
    selectors_variance: float
    stability_score: float  # 0-1, target ≥0.85
    hash_consistency: float  # Percentage of runs with same hash
    core_hashes: List[str]


class SigmaStabilityTester:
    """
    Tests SIGMA rule generation stability across multiple runs.
    
    Runs the same article/model through the pipeline multiple times
    and measures variance in outputs.
    """
    
    def __init__(self, num_runs: int = 5):
        """
        Initialize stability tester.
        
        Args:
            num_runs: Number of times to run evaluation (default: 5)
        """
        self.num_runs = num_runs
        self.normalizer = SigmaBehavioralNormalizer()
        self.semantic_scorer = SigmaSemanticScorer(use_llm_judge=False)
    
    async def test_stability(
        self,
        article_id: int,
        generate_rule_func,
        reference_rule: Optional[str] = None
    ) -> StabilityResult:
        """
        Test stability by generating rules multiple times.
        
        Args:
            article_id: Article ID to test
            generate_rule_func: Async function that generates a SIGMA rule
                               Signature: async def func(article_id: int) -> str
            reference_rule: Optional reference rule for semantic comparison
            
        Returns:
            StabilityResult with variance metrics
        """
        generated_rules = []
        cores = []
        semantic_scores = []
        
        # Generate rules multiple times
        for run_num in range(self.num_runs):
            try:
                rule_yaml = await generate_rule_func(article_id)
                generated_rules.append(rule_yaml)
                
                # Extract behavioral core
                core = self.normalizer.extract_behavioral_core(rule_yaml)
                cores.append(core)
                
                # Compare with reference if provided
                if reference_rule:
                    comparison = await self.semantic_scorer.compare_rules(
                        rule_yaml, reference_rule
                    )
                    semantic_scores.append(comparison.similarity_score)
            except Exception as e:
                logger.error(f"Stability test run {run_num + 1} failed: {e}")
                continue
        
        if not cores:
            return StabilityResult(
                unique_hashes=0,
                semantic_variance=1.0,
                selectors_variance=1.0,
                stability_score=0.0,
                hash_consistency=0.0,
                core_hashes=[]
            )
        
        # Calculate hash consistency
        core_hashes = [core.core_hash for core in cores]
        unique_hashes = len(set(core_hashes))
        
        # Calculate hash consistency (percentage with most common hash)
        if core_hashes:
            from collections import Counter
            hash_counts = Counter(core_hashes)
            most_common_count = hash_counts.most_common(1)[0][1]
            hash_consistency = most_common_count / len(core_hashes)
        else:
            hash_consistency = 0.0
        
        # Calculate selector count variance
        selector_counts = [core.selector_count for core in cores]
        if len(selector_counts) > 1:
            selector_mean = statistics.mean(selector_counts)
            selector_std = statistics.stdev(selector_counts) if len(selector_counts) > 1 else 0
            selectors_variance = selector_std / selector_mean if selector_mean > 0 else 1.0
        else:
            selectors_variance = 0.0
        
        # Calculate semantic variance
        if semantic_scores and len(semantic_scores) > 1:
            semantic_mean = statistics.mean(semantic_scores)
            semantic_std = statistics.stdev(semantic_scores)
            semantic_variance = semantic_std / semantic_mean if semantic_mean > 0 else 1.0
        else:
            semantic_variance = 0.0
        
        # Calculate overall stability score
        # Higher is better (less variance)
        stability_score = (
            hash_consistency * 0.5 +  # Hash consistency is most important
            (1.0 - min(1.0, selectors_variance)) * 0.3 +  # Lower variance is better
            (1.0 - min(1.0, semantic_variance)) * 0.2  # Lower variance is better
        )
        
        return StabilityResult(
            unique_hashes=unique_hashes,
            semantic_variance=semantic_variance,
            selectors_variance=selectors_variance,
            stability_score=stability_score,
            hash_consistency=hash_consistency,
            core_hashes=core_hashes
        )

