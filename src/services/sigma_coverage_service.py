"""
Sigma Coverage Classification Service

Analyzes matched Sigma rules to determine coverage status (covered/extend/new)
by comparing article behaviors to rule detection patterns.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import ChunkAnalysisResultTable, SigmaRuleTable

logger = logging.getLogger(__name__)


class SigmaCoverageService:
    """Service for classifying Sigma rule coverage for articles."""

    def __init__(self, db_session: Session):
        """
        Initialize the coverage service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def extract_article_behaviors(self, article_id: int) -> dict[str, Any]:
        """
        Extract behaviors from article's chunk analysis results.

        Args:
            article_id: Article ID

        Returns:
            Dictionary of extracted behaviors
        """
        try:
            # Get all chunk analysis results for the article
            chunks = self.db.query(ChunkAnalysisResultTable).filter_by(article_id=article_id).all()

            if not chunks:
                logger.info(f"No chunk analysis found for article {article_id}")
                return {
                    "perfect_discriminators": set(),
                    "good_discriminators": set(),
                    "lolbas_matches": set(),
                    "intelligence_matches": set(),
                    "hunt_scores": [],
                    "avg_hunt_score": 0.0,
                    "max_hunt_score": 0.0,
                }

            # Aggregate behaviors across all chunks
            perfect_discriminators = set()
            good_discriminators = set()
            lolbas_matches = set()
            intelligence_matches = set()
            hunt_scores = []

            for chunk in chunks:
                if chunk.perfect_discriminators_found:
                    perfect_discriminators.update(chunk.perfect_discriminators_found)
                if chunk.good_discriminators_found:
                    good_discriminators.update(chunk.good_discriminators_found)
                if chunk.lolbas_matches_found:
                    lolbas_matches.update(chunk.lolbas_matches_found)
                if chunk.intelligence_matches_found:
                    intelligence_matches.update(chunk.intelligence_matches_found)
                hunt_scores.append(chunk.hunt_score)

            behaviors = {
                "perfect_discriminators": perfect_discriminators,
                "good_discriminators": good_discriminators,
                "lolbas_matches": lolbas_matches,
                "intelligence_matches": intelligence_matches,
                "hunt_scores": hunt_scores,
                "avg_hunt_score": sum(hunt_scores) / len(hunt_scores) if hunt_scores else 0.0,
                "max_hunt_score": max(hunt_scores) if hunt_scores else 0.0,
                "chunk_count": len(chunks),
            }

            logger.debug(
                f"Extracted behaviors for article {article_id}: "
                f"{len(perfect_discriminators)} perfect, "
                f"{len(good_discriminators)} good, "
                f"{len(lolbas_matches)} lolbas"
            )

            return behaviors

        except Exception as e:
            logger.error(f"Error extracting behaviors for article {article_id}: {e}")
            return {
                "perfect_discriminators": set(),
                "good_discriminators": set(),
                "lolbas_matches": set(),
                "intelligence_matches": set(),
                "hunt_scores": [],
                "avg_hunt_score": 0.0,
                "max_hunt_score": 0.0,
            }

    def extract_rule_patterns(self, rule: SigmaRuleTable) -> set[str]:
        """
        Extract detection patterns from a Sigma rule.

        Args:
            rule: Sigma rule object

        Returns:
            Set of pattern strings from the rule
        """
        patterns = set()

        try:
            detection = rule.detection

            if not detection or not isinstance(detection, dict):
                return patterns

            # Extract patterns from detection fields
            for key, value in detection.items():
                if key == "condition":
                    continue

                # Extract values from selection criteria
                if isinstance(value, dict):
                    for field, field_value in value.items():
                        if isinstance(field_value, list):
                            for item in field_value:
                                if isinstance(item, str):
                                    # Extract key patterns (lowercase, clean)
                                    patterns.add(item.lower().strip("*"))
                        elif isinstance(field_value, str):
                            patterns.add(field_value.lower().strip("*"))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            patterns.add(item.lower().strip("*"))
                elif isinstance(value, str):
                    patterns.add(value.lower().strip("*"))

            # Also extract from title and description for context
            if rule.title:
                # Extract significant words from title (longer than 4 chars)
                title_words = [w.lower() for w in rule.title.split() if len(w) > 4]
                patterns.update(title_words)

            logger.debug(f"Extracted {len(patterns)} patterns from rule {rule.rule_id}")

        except Exception as e:
            logger.error(f"Error extracting patterns from rule {rule.rule_id}: {e}")

        return patterns

    def calculate_behavior_overlap(self, article_behaviors: dict[str, Any], rule_patterns: set[str]) -> dict[str, Any]:
        """
        Calculate overlap between article behaviors and rule patterns.

        Args:
            article_behaviors: Behaviors extracted from article
            rule_patterns: Patterns extracted from Sigma rule

        Returns:
            Dictionary with overlap statistics
        """
        # Combine all article behaviors
        all_behaviors = set()
        all_behaviors.update(article_behaviors.get("perfect_discriminators", set()))
        all_behaviors.update(article_behaviors.get("good_discriminators", set()))
        all_behaviors.update(article_behaviors.get("lolbas_matches", set()))
        all_behaviors.update(article_behaviors.get("intelligence_matches", set()))

        # Normalize behaviors for comparison (lowercase)
        normalized_behaviors = {b.lower() for b in all_behaviors}

        # Find matching patterns
        matched_behaviors = []
        for behavior in normalized_behaviors:
            for pattern in rule_patterns:
                if pattern in behavior or behavior in pattern:
                    matched_behaviors.append(behavior)
                    break

        # Calculate overlap metrics
        total_behaviors = len(normalized_behaviors)
        matched_count = len(matched_behaviors)

        overlap_ratio = matched_count / total_behaviors if total_behaviors > 0 else 0.0

        return {
            "total_behaviors": total_behaviors,
            "matched_behaviors": matched_behaviors,
            "matched_count": matched_count,
            "overlap_ratio": overlap_ratio,
            "unmatched_count": total_behaviors - matched_count,
        }

    def classify_match(
        self, article_id: int, sigma_rule: SigmaRuleTable, similarity_score: float, chunk_id: int | None = None
    ) -> dict[str, Any]:
        """
        Classify the coverage status of a matched Sigma rule.

        Args:
            article_id: Article ID
            sigma_rule: Matched Sigma rule
            similarity_score: Cosine similarity score
            chunk_id: Optional chunk ID for chunk-level matches

        Returns:
            Classification result with status and reasoning
        """
        try:
            # Extract article behaviors
            article_behaviors = self.extract_article_behaviors(article_id)

            # Extract rule patterns
            rule_patterns = self.extract_rule_patterns(sigma_rule)

            # Calculate overlap
            overlap = self.calculate_behavior_overlap(article_behaviors, rule_patterns)

            # Classify based on similarity score and behavior overlap
            coverage_status = "new"
            confidence = 0.0
            reasoning = ""

            overlap_ratio = overlap["overlap_ratio"]
            matched_count = overlap["matched_count"]

            # Classification logic
            if similarity_score >= 0.85 and overlap_ratio >= 0.7:
                # High similarity + high overlap = covered
                coverage_status = "covered"
                confidence = min(0.9, (similarity_score + overlap_ratio) / 2)
                reasoning = (
                    f"Article behaviors are well covered by this rule "
                    f"({matched_count}/{overlap['total_behaviors']} behaviors matched, "
                    f"{similarity_score:.2f} similarity)"
                )

            elif similarity_score >= 0.7 and overlap_ratio >= 0.3:
                # Medium similarity + some overlap = extend
                coverage_status = "extend"
                confidence = (similarity_score + overlap_ratio) / 2
                reasoning = (
                    f"Partial overlap detected "
                    f"({matched_count}/{overlap['total_behaviors']} behaviors matched, "
                    f"{similarity_score:.2f} similarity). "
                    f"Rule could be extended to cover additional behaviors."
                )

            else:
                # Low overlap = new detection opportunity
                coverage_status = "new"
                confidence = 1.0 - (similarity_score + overlap_ratio) / 2
                reasoning = (
                    f"Minimal overlap "
                    f"({matched_count}/{overlap['total_behaviors']} behaviors matched, "
                    f"{similarity_score:.2f} similarity). "
                    f"Article represents new detection patterns."
                )

            # Adjust based on hunt score
            avg_hunt_score = article_behaviors.get("avg_hunt_score", 0)
            if avg_hunt_score > 70:
                reasoning += f" High hunt score ({avg_hunt_score:.1f}) indicates valuable content."

            result = {
                "coverage_status": coverage_status,
                "coverage_confidence": confidence,
                "coverage_reasoning": reasoning,
                "matched_discriminators": overlap["matched_behaviors"][:10],  # Top 10
                "matched_lolbas": list(article_behaviors.get("lolbas_matches", set()))[:10],
                "matched_intelligence": list(article_behaviors.get("intelligence_matches", set()))[:5],
                "overlap_ratio": overlap_ratio,
                "similarity_score": similarity_score,
            }

            logger.debug(
                f"Classified match for article {article_id} and rule {sigma_rule.rule_id}: "
                f"{coverage_status} (confidence: {confidence:.2f})"
            )

            return result

        except Exception as e:
            logger.error(f"Error classifying match for article {article_id}: {e}")
            return {
                "coverage_status": "new",
                "coverage_confidence": 0.5,
                "coverage_reasoning": f"Error during classification: {str(e)}",
                "matched_discriminators": [],
                "matched_lolbas": [],
                "matched_intelligence": [],
                "overlap_ratio": 0.0,
                "similarity_score": similarity_score,
            }

    def analyze_article_coverage(self, article_id: int) -> dict[str, Any]:
        """
        Analyze overall Sigma rule coverage for an article.

        Args:
            article_id: Article ID

        Returns:
            Comprehensive coverage analysis
        """
        from src.services.sigma_matching_service import SigmaMatchingService

        try:
            matching_service = SigmaMatchingService(self.db)

            # Get all matches for the article
            matches = matching_service.get_article_matches(article_id)

            if not matches:
                return {
                    "has_coverage": False,
                    "coverage_summary": {"covered": 0, "extend": 0, "new": 0, "total": 0},
                    "recommendation": "No matching Sigma rules found. Generate new rules.",
                    "top_matches": [],
                }

            # Aggregate coverage statistics
            coverage_counts = {"covered": 0, "extend": 0, "new": 0}

            for match in matches:
                status = match.get("coverage_status", "new")
                if status in coverage_counts:
                    coverage_counts[status] += 1

            total_matches = len(matches)
            coverage_counts["total"] = total_matches

            # Generate recommendation
            if coverage_counts["covered"] > 0:
                recommendation = (
                    f"{coverage_counts['covered']} existing rule(s) cover this article. No new rules needed."
                )
            elif coverage_counts["extend"] > 0:
                recommendation = (
                    f"{coverage_counts['extend']} rule(s) partially cover this article. "
                    f"Consider generating enhanced rules."
                )
            else:
                recommendation = "No significant coverage found. Generate new Sigma rules."

            return {
                "has_coverage": coverage_counts["covered"] > 0 or coverage_counts["extend"] > 0,
                "coverage_summary": coverage_counts,
                "recommendation": recommendation,
                "top_matches": matches[:5],  # Top 5 matches
            }

        except Exception as e:
            logger.error(f"Error analyzing coverage for article {article_id}: {e}")
            return {
                "has_coverage": False,
                "coverage_summary": {"covered": 0, "extend": 0, "new": 0, "total": 0},
                "recommendation": f"Error analyzing coverage: {str(e)}",
                "top_matches": [],
            }
