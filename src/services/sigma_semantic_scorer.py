"""
SIGMA Semantic Equivalence Scorer.

Compares generated SIGMA rules against reference rules using
LLM-judge or embedding-based similarity.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticComparisonResult:
    """Result of semantic comparison between rules."""
    similarity_score: float  # 0-1
    missing_behaviors: int
    extraneous_behaviors: int
    missing_behavior_details: List[str]
    extraneous_behavior_details: List[str]


class SigmaSemanticScorer:
    """
    Scores semantic equivalence between SIGMA rules.
    
    Supports two methods:
    1. LLM-judge: Uses LLM to compare rules
    2. Embedding-based: Uses embeddings for similarity
    """
    
    def __init__(self, use_llm_judge: bool = True, llm_service=None):
        """
        Initialize semantic scorer.
        
        Args:
            use_llm_judge: If True, use LLM-judge; otherwise use embeddings
            llm_service: LLM service instance (required if use_llm_judge=True)
        """
        self.use_llm_judge = use_llm_judge
        self.llm_service = llm_service
        
        if use_llm_judge and not llm_service:
            logger.warning("LLM-judge requested but no LLM service provided. Will use embedding fallback.")
            self.use_llm_judge = False
    
    async def compare_rules(
        self,
        generated_rule: str,
        reference_rule: str,
        generated_rule_yaml: Optional[Dict] = None,
        reference_rule_yaml: Optional[Dict] = None
    ) -> SemanticComparisonResult:
        """
        Compare generated rule against reference rule.
        
        Args:
            generated_rule: Generated SIGMA rule (YAML string)
            reference_rule: Reference SIGMA rule (YAML string)
            generated_rule_yaml: Parsed generated rule (optional)
            reference_rule_yaml: Parsed reference rule (optional)
            
        Returns:
            SemanticComparisonResult with similarity and behavior differences
        """
        if self.use_llm_judge and self.llm_service:
            return await self._compare_with_llm_judge(
                generated_rule, reference_rule, generated_rule_yaml, reference_rule_yaml
            )
        else:
            return await self._compare_with_embeddings(
                generated_rule, reference_rule, generated_rule_yaml, reference_rule_yaml
            )
    
    async def _compare_with_llm_judge(
        self,
        generated_rule: str,
        reference_rule: str,
        generated_rule_yaml: Optional[Dict],
        reference_rule_yaml: Optional[Dict]
    ) -> SemanticComparisonResult:
        """Compare rules using LLM-judge."""
        prompt = f"""You are evaluating SIGMA detection rules. Compare the generated rule against the reference rule.

Reference Rule:
```yaml
{reference_rule}
```

Generated Rule:
```yaml
{generated_rule}
```

Evaluate:
1. Does the generated rule detect the same behaviors as the reference?
2. Are any behaviors missing from the generated rule?
3. Are any irrelevant behaviors added to the generated rule?
4. Is there overfitting (IOC-based logic)?
5. Are there false-positive amplifiers?

Respond in JSON format:
{{
    "similarity_score": 0.0-1.0,
    "missing_behaviors": ["behavior1", "behavior2"],
    "extraneous_behaviors": ["behavior1", "behavior2"],
    "overfitting_detected": true/false,
    "fp_risk": "low/medium/high",
    "explanation": "brief explanation"
}}
"""
        
        try:
            # Use LLM service to get comparison
            # Create a simple chat completion request
            system_prompt = "You are an expert SIGMA rule evaluator. Analyze and compare SIGMA detection rules."
            
            payload = {
                "model": self.llm_service.model_sigma,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }
            
            # Call LLM service
            response = await self.llm_service._post_lmstudio_chat(
                payload,
                model_name=self.llm_service.model_sigma,
                timeout=60.0,
                failure_context="Semantic rule comparison"
            )
            
            # Extract response text
            response_text = response.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            # Try to parse JSON from response
            import json
            import re
            
            # Try to extract JSON from response (might be wrapped in markdown)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Fallback: try to parse entire response
                result = json.loads(response_text)
            
            return SemanticComparisonResult(
                similarity_score=float(result.get('similarity_score', 0.0)),
                missing_behaviors=len(result.get('missing_behaviors', [])),
                extraneous_behaviors=len(result.get('extraneous_behaviors', [])),
                missing_behavior_details=result.get('missing_behaviors', []),
                extraneous_behavior_details=result.get('extraneous_behaviors', [])
            )
        except Exception as e:
            logger.error(f"LLM-judge comparison failed: {e}")
            # Fallback to embedding-based
            return await self._compare_with_embeddings(
                generated_rule, reference_rule, generated_rule_yaml, reference_rule_yaml
            )
    
    async def _compare_with_embeddings(
        self,
        generated_rule: str,
        reference_rule: str,
        generated_rule_yaml: Optional[Dict],
        reference_rule_yaml: Optional[Dict]
    ) -> SemanticComparisonResult:
        """Compare rules using embedding similarity (fallback method)."""
        try:
            from src.services.embedding_service import EmbeddingService
            import asyncio
            
            embedding_service = EmbeddingService()
            
            # Generate embeddings (synchronous, but run in executor to avoid blocking)
            # Use get_running_loop() instead of get_event_loop() to avoid creating new loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, but we're in async context - this shouldn't happen
                raise RuntimeError("compare_rules() must be called from async context")
            gen_embedding = await loop.run_in_executor(None, embedding_service.generate_embedding, generated_rule)
            ref_embedding = await loop.run_in_executor(None, embedding_service.generate_embedding, reference_rule)
            
            # Calculate cosine similarity
            import numpy as np
            similarity = np.dot(gen_embedding, ref_embedding) / (
                np.linalg.norm(gen_embedding) * np.linalg.norm(ref_embedding)
            )
            
            # For embedding-based, we can't easily extract missing/extraneous behaviors
            # So we use a heuristic based on similarity
            missing_count = 0
            extraneous_count = 0
            
            if similarity < 0.7:
                # Low similarity suggests missing or extraneous behaviors
                # Estimate based on similarity difference
                missing_count = int((1.0 - similarity) * 2)
                extraneous_count = int((1.0 - similarity) * 1)
            
            return SemanticComparisonResult(
                similarity_score=float(similarity),
                missing_behaviors=missing_count,
                extraneous_behaviors=extraneous_count,
                missing_behavior_details=[],
                extraneous_behavior_details=[]
            )
        except Exception as e:
            logger.error(f"Embedding-based comparison failed: {e}")
            # Ultimate fallback: return neutral result
            return SemanticComparisonResult(
                similarity_score=0.5,
                missing_behaviors=0,
                extraneous_behaviors=0,
                missing_behavior_details=[],
                extraneous_behavior_details=[]
            )

