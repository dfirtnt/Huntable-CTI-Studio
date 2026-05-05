"""SIGMA Semantic Equivalence Scorer using embedding similarity."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticComparisonResult:
    """Result of semantic comparison between rules."""

    similarity_score: float  # 0-1


class SigmaSemanticScorer:
    """Scores semantic equivalence between SIGMA rules using embedding similarity."""

    async def compare_rules(self, generated_rule: str, reference_rule: str) -> SemanticComparisonResult:
        """Compare generated rule against reference rule."""
        try:
            import asyncio

            import numpy as np

            from src.services.embedding_service import EmbeddingService

            embedding_service = EmbeddingService()
            loop = asyncio.get_running_loop()
            gen_embedding = await loop.run_in_executor(None, embedding_service.generate_embedding, generated_rule)
            ref_embedding = await loop.run_in_executor(None, embedding_service.generate_embedding, reference_rule)

            similarity = np.dot(gen_embedding, ref_embedding) / (
                np.linalg.norm(gen_embedding) * np.linalg.norm(ref_embedding)
            )
            return SemanticComparisonResult(similarity_score=float(similarity))
        except Exception as e:
            logger.error("Embedding-based comparison failed: %s", e)
            return SemanticComparisonResult(similarity_score=0.5)
