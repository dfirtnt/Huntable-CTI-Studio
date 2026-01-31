"""
SIGMA Novelty Detector.

Compares generated SIGMA rules against existing SigmaHQ repository
to determine if rules are novel, variants, or duplicates.
"""

import logging
from dataclasses import dataclass

from src.services.sigma_behavioral_normalizer import SigmaBehavioralNormalizer

logger = logging.getLogger(__name__)


@dataclass
class NoveltyResult:
    """Result of novelty detection."""

    novelty_score: int  # 0=duplicate, 1=variant, 2=novel
    novelty_status: str  # "duplicate", "variant", "novel"
    closest_match_id: int | None = None
    closest_match_similarity: float | None = None
    closest_match_title: str | None = None


class SigmaNoveltyDetector:
    """
    Detects novelty of SIGMA rules by comparing against existing repository.

    Uses behavioral core fingerprints to identify duplicates and variants.
    """

    def __init__(self, similarity_threshold_duplicate: float = 0.95, similarity_threshold_variant: float = 0.70):
        """
        Initialize novelty detector.

        Args:
            similarity_threshold_duplicate: Hash similarity threshold for duplicates (default: 0.95)
            similarity_threshold_variant: Hash similarity threshold for variants (default: 0.70)
        """
        self.similarity_threshold_duplicate = similarity_threshold_duplicate
        self.similarity_threshold_variant = similarity_threshold_variant
        self.normalizer = SigmaBehavioralNormalizer()

    def detect_novelty(self, rule_yaml: str, db_session=None) -> NoveltyResult:
        """
        Detect novelty of a SIGMA rule.

        Args:
            rule_yaml: Generated SIGMA rule (YAML string)
            db_session: Database session to query existing rules

        Returns:
            NoveltyResult with novelty status
        """
        # Extract behavioral core
        core = self.normalizer.extract_behavioral_core(rule_yaml)

        if not core.core_hash:
            return NoveltyResult(
                novelty_score=2,
                novelty_status="novel",
                closest_match_id=None,
                closest_match_similarity=None,
                closest_match_title=None,
            )

        # Query existing rules from database
        if db_session:
            from src.database.models import SigmaRuleTable

            # Get all existing rules
            existing_rules = db_session.query(SigmaRuleTable).all()

            best_match = None
            best_similarity = 0.0

            for existing_rule in existing_rules:
                # Extract core from existing rule
                try:
                    existing_core = self.normalizer.extract_behavioral_core(existing_rule.rule_yaml or "")

                    # Compare cores
                    if existing_core.core_hash == core.core_hash:
                        # Exact match
                        return NoveltyResult(
                            novelty_score=0,
                            novelty_status="duplicate",
                            closest_match_id=existing_rule.id,
                            closest_match_similarity=1.0,
                            closest_match_title=existing_rule.title,
                        )

                    # Calculate similarity
                    comparison = self.normalizer.compare_cores(core, existing_core)
                    similarity = comparison["similarity"]

                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = existing_rule
                except Exception as e:
                    logger.debug(f"Failed to compare with rule {existing_rule.id}: {e}")
                    continue

            # Determine novelty based on best match
            if best_match:
                if best_similarity >= self.similarity_threshold_duplicate:
                    return NoveltyResult(
                        novelty_score=0,
                        novelty_status="duplicate",
                        closest_match_id=best_match.id,
                        closest_match_similarity=best_similarity,
                        closest_match_title=best_match.title,
                    )
                if best_similarity >= self.similarity_threshold_variant:
                    return NoveltyResult(
                        novelty_score=1,
                        novelty_status="variant",
                        closest_match_id=best_match.id,
                        closest_match_similarity=best_similarity,
                        closest_match_title=best_match.title,
                    )

            # No close match found - rule is novel
            return NoveltyResult(
                novelty_score=2,
                novelty_status="novel",
                closest_match_id=best_match.id if best_match else None,
                closest_match_similarity=best_similarity if best_match else None,
                closest_match_title=best_match.title if best_match else None,
            )
        # No database session - assume novel
        logger.warning("No database session provided, assuming rule is novel")
        return NoveltyResult(
            novelty_score=2,
            novelty_status="novel",
            closest_match_id=None,
            closest_match_similarity=None,
            closest_match_title=None,
        )
