"""Service for managing chunk analysis results (ML vs Hunt scoring comparison)."""

import logging
from typing import Any

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.database.models import ArticleTable, ChunkAnalysisResultTable
from src.utils.content import ThreatHuntingScorer
from src.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)


class ChunkAnalysisService:
    """Service for managing chunk analysis results."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.hunt_scorer = ThreatHuntingScorer()
        self.content_filter = ContentFilter()

    def should_store_analysis(self, article_id: int) -> bool:
        """Check if we should store chunk analysis for this article (hunt_score > 50)."""
        try:
            article = self.db.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                return False

            hunt_score = article.article_metadata.get("threat_hunting_score", 0)
            return hunt_score > 50
        except Exception as e:
            logger.error(f"Error checking hunt score for article {article_id}: {e}")
            return False

    def store_chunk_analysis(
        self,
        article_id: int,
        chunks: list[tuple[int, int, str]],
        ml_predictions: list[tuple[bool, float]],
        model_version: str,
    ) -> int:
        """Store chunk analysis results for an article."""
        if not self.should_store_analysis(article_id):
            logger.debug(f"Skipping chunk analysis storage for article {article_id} (hunt_score <= 50)")
            return 0

        stored_count = 0
        seen_chunks = set()  # Track already-processed chunks to prevent duplicates

        try:
            for (start, end, chunk_text), (ml_prediction, ml_confidence) in zip(chunks, ml_predictions):
                # Deduplication: skip if we've already processed this chunk
                chunk_key = (article_id, model_version, start, end)
                if chunk_key in seen_chunks:
                    logger.debug(f"Skipping duplicate chunk for article {article_id}: {start}-{end}")
                    continue
                seen_chunks.add(chunk_key)

                # Check if chunk already exists in database
                existing = (
                    self.db.query(ChunkAnalysisResultTable)
                    .filter(
                        ChunkAnalysisResultTable.article_id == article_id,
                        ChunkAnalysisResultTable.model_version == model_version,
                        ChunkAnalysisResultTable.chunk_start == start,
                        ChunkAnalysisResultTable.chunk_end == end,
                    )
                    .first()
                )

                if existing:
                    logger.debug(f"Chunk already exists in DB for article {article_id}: {start}-{end}")
                    continue

                # Get hunt scoring for this chunk
                hunt_result = self.hunt_scorer.score_threat_hunting_content("", chunk_text)
                hunt_score = hunt_result.get("threat_hunting_score", 0)
                hunt_prediction = hunt_score > 0

                # Create chunk analysis result (convert numpy types to Python types)
                chunk_analysis = ChunkAnalysisResultTable(
                    article_id=article_id,
                    chunk_start=start,
                    chunk_end=end,
                    chunk_text=chunk_text,
                    model_version=model_version,
                    ml_prediction=bool(ml_prediction),
                    ml_confidence=float(ml_confidence),
                    hunt_score=float(hunt_score),
                    hunt_prediction=bool(hunt_prediction),
                    perfect_discriminators_found=hunt_result.get("perfect_keyword_matches", []),
                    good_discriminators_found=hunt_result.get("good_keyword_matches", []),
                    lolbas_matches_found=hunt_result.get("lolbas_matches", []),
                    intelligence_matches_found=hunt_result.get("intelligence_matches", []),
                    negative_matches_found=hunt_result.get("negative_matches", []),
                )

                self.db.add(chunk_analysis)
                stored_count += 1

            self.db.commit()
            logger.info(f"Stored {stored_count} chunk analysis results for article {article_id}")

            # Calculate and update ML hunt score after storing chunks
            if stored_count > 0:
                try:
                    self.update_article_ml_hunt_score(
                        article_id, metric="weighted_average", model_version=model_version
                    )
                except Exception as e:
                    logger.warning(f"Failed to update ML hunt score for article {article_id} after storing chunks: {e}")
                    # Don't fail the whole operation if score update fails

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error storing chunk analysis for article {article_id}: {e}")
            raise

        return stored_count

    def get_model_comparison_stats(self, model_version: str | None = None) -> list[dict[str, Any]]:
        """Get comparison statistics for model versions."""
        try:
            from sqlalchemy import case

            query = self.db.query(
                ChunkAnalysisResultTable.model_version,
                func.count(ChunkAnalysisResultTable.id).label("total_chunks"),
                func.sum(case((ChunkAnalysisResultTable.ml_prediction == True, 1), else_=0)).label("ml_huntable_count"),
                func.sum(case((ChunkAnalysisResultTable.hunt_prediction == True, 1), else_=0)).label(
                    "hunt_huntable_count"
                ),
                func.sum(
                    case(
                        (
                            and_(
                                ChunkAnalysisResultTable.ml_prediction == True,
                                ChunkAnalysisResultTable.hunt_prediction == True,
                            ),
                            1,
                        ),
                        (
                            and_(
                                ChunkAnalysisResultTable.ml_prediction == False,
                                ChunkAnalysisResultTable.hunt_prediction == False,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("agreement_count"),
                func.sum(
                    case(
                        (
                            and_(
                                ChunkAnalysisResultTable.ml_prediction == True,
                                ChunkAnalysisResultTable.hunt_prediction == False,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("ml_only_huntable"),
                func.sum(
                    case(
                        (
                            and_(
                                ChunkAnalysisResultTable.ml_prediction == False,
                                ChunkAnalysisResultTable.hunt_prediction == True,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ).label("hunt_only_huntable"),
                func.avg(ChunkAnalysisResultTable.ml_confidence).label("avg_ml_confidence"),
                func.avg(ChunkAnalysisResultTable.hunt_score).label("avg_hunt_score"),
            )

            if model_version:
                query = query.filter(ChunkAnalysisResultTable.model_version == model_version)

            results = query.group_by(ChunkAnalysisResultTable.model_version).all()

            stats = []
            for result in results:
                total = result.total_chunks
                ml_huntable = result.ml_huntable_count or 0
                hunt_huntable = result.hunt_huntable_count or 0
                agreement = result.agreement_count or 0
                ml_only = result.ml_only_huntable or 0
                hunt_only = result.hunt_only_huntable or 0

                # Calculate metrics
                accuracy = (agreement / total) if total > 0 else 0
                precision = (agreement / ml_huntable) if ml_huntable > 0 else 0
                recall = (agreement / hunt_huntable) if hunt_huntable > 0 else 0
                f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

                stats.append(
                    {
                        "model_version": result.model_version,
                        "total_chunks": total,
                        "ml_huntable_count": ml_huntable,
                        "hunt_huntable_count": hunt_huntable,
                        "agreement_count": agreement,
                        "ml_only_huntable": ml_only,
                        "hunt_only_huntable": hunt_only,
                        "accuracy": round(accuracy, 3),
                        "precision": round(precision, 3),
                        "recall": round(recall, 3),
                        "f1_score": round(f1_score, 3),
                        "avg_ml_confidence": round(result.avg_ml_confidence or 0, 3),
                        "avg_hunt_score": round(result.avg_hunt_score or 0, 3),
                    }
                )

            return stats

        except Exception as e:
            logger.error(f"Error getting model comparison stats: {e}")
            return []

    def get_chunk_analysis_results(
        self,
        article_id: int | None = None,
        model_version: str | None = None,
        hunt_score_min: float | None = None,
        hunt_score_max: float | None = None,
        ml_prediction: bool | None = None,
        hunt_prediction: bool | None = None,
        agreement: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get chunk analysis results with filtering."""
        try:
            query = self.db.query(ChunkAnalysisResultTable)

            if article_id:
                query = query.filter(ChunkAnalysisResultTable.article_id == article_id)
            if model_version:
                query = query.filter(ChunkAnalysisResultTable.model_version == model_version)
            if hunt_score_min is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_score >= hunt_score_min)
            if hunt_score_max is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_score <= hunt_score_max)
            if ml_prediction is not None:
                query = query.filter(ChunkAnalysisResultTable.ml_prediction == ml_prediction)
            if hunt_prediction is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_prediction == hunt_prediction)
            if agreement is not None:
                if agreement:
                    # Both agree (both True or both False)
                    query = query.filter(
                        ChunkAnalysisResultTable.ml_prediction == ChunkAnalysisResultTable.hunt_prediction
                    )
                else:
                    # Disagree (one True, one False)
                    query = query.filter(
                        ChunkAnalysisResultTable.ml_prediction != ChunkAnalysisResultTable.hunt_prediction
                    )

            results = query.order_by(desc(ChunkAnalysisResultTable.created_at)).offset(offset).limit(limit).all()

            return [
                {
                    "id": result.id,
                    "article_id": result.article_id,
                    "chunk_start": result.chunk_start,
                    "chunk_end": result.chunk_end,
                    "chunk_text": result.chunk_text,
                    "model_version": result.model_version,
                    "ml_prediction": result.ml_prediction,
                    "ml_confidence": result.ml_confidence,
                    "hunt_score": result.hunt_score,
                    "hunt_prediction": result.hunt_prediction,
                    "perfect_discriminators_found": result.perfect_discriminators_found or [],
                    "good_discriminators_found": result.good_discriminators_found or [],
                    "lolbas_matches_found": result.lolbas_matches_found or [],
                    "intelligence_matches_found": result.intelligence_matches_found or [],
                    "negative_matches_found": result.negative_matches_found or [],
                    "created_at": result.created_at,
                    "updated_at": result.updated_at,
                }
                for result in results
            ]

        except Exception as e:
            logger.error(f"Error getting chunk analysis results: {e}")
            return []

    def get_available_model_versions(self) -> list[str]:
        """Get list of available model versions."""
        try:
            results = self.db.query(ChunkAnalysisResultTable.model_version).distinct().all()
            return [result.model_version for result in results]
        except Exception as e:
            logger.error(f"Error getting model versions: {e}")
            return []

    def calculate_ml_hunt_score(
        self,
        article_id: int,
        model_version: str | None = None,
        metric: str = "weighted_average",
        min_confidence_threshold: float = 0.5,
    ) -> dict[str, Any] | None:
        """
        Calculate ML-based hunt score for an article from chunk analysis results.

        Args:
            article_id: Article ID to calculate score for
            model_version: Optional model version filter (uses latest if not specified)
            metric: Metric calculation method:
                - 'weighted_average': Average confidence of huntable chunks (recommended)
                - 'proportion_weighted': (huntable_count / total_count) * avg_confidence
                - 'confidence_sum_normalized': sum(confidences) / total_chunks
                - 'top_percentile': 75th percentile confidence of huntable chunks
                - 'user_proposed': User's original proposal (chunks >50% conf, sum/total)
            min_confidence_threshold: Minimum confidence for user_proposed metric

        Returns:
            Dict with score (0-100), metric details, and statistics, or None if no chunks found
        """
        try:
            # Get all chunks for this article
            query = self.db.query(ChunkAnalysisResultTable).filter(ChunkAnalysisResultTable.article_id == article_id)

            if model_version:
                query = query.filter(ChunkAnalysisResultTable.model_version == model_version)
            else:
                # Use latest model version if not specified
                latest_version = (
                    self.db.query(func.max(ChunkAnalysisResultTable.model_version))
                    .filter(ChunkAnalysisResultTable.article_id == article_id)
                    .scalar()
                )
                if latest_version:
                    query = query.filter(ChunkAnalysisResultTable.model_version == latest_version)

            chunks = query.all()

            if not chunks:
                logger.debug(f"No chunk analysis results found for article {article_id}")
                return None

            # Extract huntable chunks (where ML predicts huntable)
            huntable_chunks = [
                (chunk.ml_confidence, chunk.ml_prediction) for chunk in chunks if chunk.ml_prediction is True
            ]

            total_chunks = len(chunks)
            huntable_count = len(huntable_chunks)

            if huntable_count == 0:
                # No huntable chunks - return zero score
                return {
                    "ml_hunt_score": 0.0,
                    "metric": metric,
                    "total_chunks": total_chunks,
                    "huntable_chunks": 0,
                    "avg_confidence": 0.0,
                    "details": "No chunks predicted as huntable by ML model",
                }

            # Extract confidences for huntable chunks
            huntable_confidences = [conf for conf, pred in huntable_chunks]

            # Calculate score based on selected metric
            if metric == "weighted_average":
                # Recommended: Average confidence of huntable chunks, scaled to 0-100
                avg_confidence = sum(huntable_confidences) / huntable_count
                score = avg_confidence * 100

            elif metric == "proportion_weighted":
                # Proportion of huntable chunks * average confidence
                proportion = huntable_count / total_chunks
                avg_confidence = sum(huntable_confidences) / huntable_count
                score = proportion * avg_confidence * 100

            elif metric == "confidence_sum_normalized":
                # Sum of all huntable confidences, normalized by total chunks
                confidence_sum = sum(huntable_confidences)
                score = (confidence_sum / total_chunks) * 100

            elif metric == "top_percentile":
                # 75th percentile confidence of huntable chunks
                import numpy as np

                percentile_75 = np.percentile(huntable_confidences, 75)
                score = percentile_75 * 100

            elif metric == "user_proposed":
                # User's original proposal: chunks >threshold, sum/total
                high_confidence_chunks = [conf for conf in huntable_confidences if conf > min_confidence_threshold]
                if len(high_confidence_chunks) == 0:
                    score = 0.0
                else:
                    confidence_sum = sum(high_confidence_chunks)
                    score = (confidence_sum / len(high_confidence_chunks)) * 100
                huntable_count = len(high_confidence_chunks)  # Override for this metric

            else:
                logger.warning(f"Unknown metric '{metric}', using weighted_average")
                avg_confidence = sum(huntable_confidences) / huntable_count
                score = avg_confidence * 100

            # Clamp score to 0-100 range
            score = max(0.0, min(100.0, score))

            # Calculate additional statistics
            avg_confidence = sum(huntable_confidences) / huntable_count
            min_confidence = min(huntable_confidences)
            max_confidence = max(huntable_confidences)

            return {
                "ml_hunt_score": round(score, 2),
                "metric": metric,
                "total_chunks": total_chunks,
                "huntable_chunks": huntable_count,
                "huntable_proportion": round(huntable_count / total_chunks, 3),
                "avg_confidence": round(avg_confidence, 3),
                "min_confidence": round(min_confidence, 3),
                "max_confidence": round(max_confidence, 3),
                "model_version": chunks[0].model_version if chunks else None,
            }

        except Exception as e:
            logger.error(f"Error calculating ML hunt score for article {article_id}: {e}")
            return None

    def update_article_ml_hunt_score(
        self, article_id: int, metric: str = "weighted_average", model_version: str | None = None
    ) -> bool:
        """
        Calculate and update article metadata with ML hunt score.

        Args:
            article_id: Article ID to update
            metric: Metric calculation method (see calculate_ml_hunt_score)
            model_version: Optional model version filter

        Returns:
            True if score was calculated and updated, False otherwise
        """
        try:
            # Calculate ML hunt score
            score_result = self.calculate_ml_hunt_score(article_id, model_version=model_version, metric=metric)

            if not score_result:
                logger.debug(f"No ML hunt score calculated for article {article_id} (no chunks found)")
                return False

            # Get article and update metadata
            article = self.db.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                logger.error(f"Article {article_id} not found")
                return False

            # Update article metadata
            if not article.article_metadata:
                article.article_metadata = {}

            # Store ML hunt score and details
            article.article_metadata["ml_hunt_score"] = score_result["ml_hunt_score"]
            article.article_metadata["ml_hunt_score_metric"] = score_result["metric"]
            article.article_metadata["ml_hunt_score_details"] = {
                "total_chunks": score_result["total_chunks"],
                "huntable_chunks": score_result["huntable_chunks"],
                "huntable_proportion": score_result["huntable_proportion"],
                "avg_confidence": score_result["avg_confidence"],
                "min_confidence": score_result["min_confidence"],
                "max_confidence": score_result["max_confidence"],
                "model_version": score_result["model_version"],
            }

            # Mark JSON field as modified so SQLAlchemy detects the change
            flag_modified(article, "article_metadata")

            self.db.commit()
            logger.info(f"Updated ML hunt score for article {article_id}: {score_result['ml_hunt_score']:.2f}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating ML hunt score for article {article_id}: {e}")
            return False
