"""
Debug and diagnostic endpoints.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

import numpy as np
from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.utils.gpt4o_optimizer import estimate_gpt4o_cost
from src.web.dependencies import get_content_filter, logger

router = APIRouter(tags=["Debug"])


@router.get("/api/test-route")
async def test_route():
    """Test route to verify route registration."""
    return {"message": "Test route is working"}


@router.get("/api/articles/{article_id}/chunk-debug")
async def api_chunk_debug(
    article_id: int,
    chunk_size: int = 1000,
    overlap: int = 200,
    min_confidence: float = 0.7,
    full_analysis: bool = False,
):
    """
    Debug endpoint to analyze chunking and filtering for an article.
    """
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        content_filter = get_content_filter()

        # Extract hunt_score from article metadata
        hunt_score = article.article_metadata.get('threat_hunting_score')
        if hunt_score is not None:
            try:
                hunt_score = float(hunt_score)
            except (ValueError, TypeError):
                hunt_score = None

        max_chunks_setting = int(os.getenv("CHUNK_DEBUG_MAX_CHUNKS", "150"))
        concurrency_limit = max(1, int(os.getenv("CHUNK_DEBUG_CONCURRENCY", "4")))
        per_chunk_timeout = float(os.getenv("CHUNK_DEBUG_CHUNK_TIMEOUT", "12.0"))

        if full_analysis:
            concurrency_limit = max(
                1,
                int(os.getenv("CHUNK_DEBUG_FULL_CONCURRENCY", str(concurrency_limit))),
            )
            per_chunk_timeout = float(os.getenv("CHUNK_DEBUG_FULL_TIMEOUT", str(per_chunk_timeout)))

        original_chunks = await asyncio.to_thread(
            content_filter.chunk_content,
            article.content,
            chunk_size,
            overlap,
        )

        filter_result = await asyncio.to_thread(
            content_filter.filter_content,
            article.content,
            min_confidence,
            chunk_size,
            hunt_score,
        )

        total_chunks = len(original_chunks)
        removed_chunks = len(filter_result.removed_chunks or [])
        kept_chunks = max(total_chunks - removed_chunks, 0)

        chunk_limit = total_chunks if full_analysis else min(total_chunks, max_chunks_setting)
        semaphore = asyncio.Semaphore(concurrency_limit)
        chunk_analysis_results = []

        async def analyze_chunk(chunk_id: int, start: int, end: int, chunk_text: str):
            async with semaphore:
                def _process_chunk():
                    chunk_result = content_filter.filter_content(
                        chunk_text,
                        min_confidence,
                        max(len(chunk_text), 1),
                        hunt_score,
                    )

                    features = content_filter.extract_features(chunk_text, hunt_score, include_new_features=True)
                    sanitized_features = {}
                    for key, value in features.items():
                        if hasattr(value, "item"):
                            sanitized_features[key] = float(value.item())
                        elif isinstance(value, (np.floating, np.integer)):
                            sanitized_features[key] = float(value)
                        else:
                            sanitized_features[key] = value

                    ml_details = None
                    if content_filter.model:
                        try:
                            ml_features = content_filter.extract_features(
                                chunk_text, hunt_score, include_new_features=False
                            )
                            feature_vector = np.array(list(ml_features.values()), dtype=float).reshape(1, -1)
                            prediction = content_filter.model.predict(feature_vector)[0]
                            probabilities = content_filter.model.predict_proba(feature_vector)[0]

                            feature_contribution = None
                            if hasattr(content_filter.model, "feature_importances_"):
                                feature_names = list(ml_features.keys())
                                importances = content_filter.model.feature_importances_
                                if len(importances) == len(feature_vector[0]):
                                    contributions = feature_vector[0] * importances
                                    feature_contribution = dict(zip(feature_names, contributions))
                                    feature_contribution = dict(
                                        sorted(feature_contribution.items(), key=lambda item: item[1], reverse=True)
                                    )

                            ml_details = {
                                "prediction": int(prediction),
                                "prediction_label": "Huntable" if prediction == 1 else "Not Huntable",
                                "probabilities": {
                                    "not_huntable": float(probabilities[0]),
                                    "huntable": float(probabilities[1]),
                                },
                                "feature_contribution": feature_contribution,
                            }
                        except Exception as exc:  # noqa: BLE001
                            ml_details = {"error": str(exc)}

                    # Check for keywords and patterns using threat hunting scorer
                    from src.utils.content import ThreatHuntingScorer
                    hunt_result = ThreatHuntingScorer.score_threat_hunting_content(chunk_text, "Content Filter Analysis")
                    
                    has_keywords = hunt_result.get('good_keyword_matches', [])
                    has_command_patterns = hunt_result.get('lolbas_matches', [])
                    has_perfect_discriminators = hunt_result.get('perfect_keyword_matches', [])
                    
                    has_keywords = len(has_keywords) > 0
                    has_command_patterns = len(has_command_patterns) > 0
                    has_perfect_discriminators = len(has_perfect_discriminators) > 0

                    ml_prediction_correct = None
                    ml_mismatch = False
                    if ml_details and "prediction" in ml_details:
                        ml_prediction_correct = (
                            ml_details["prediction"] == (1 if chunk_result.is_huntable else 0)
                        )
                        ml_mismatch = not ml_prediction_correct

                    return {
                        "chunk_id": chunk_id,
                        "start": start,
                        "end": end,
                        "length": len(chunk_text),
                        "text": chunk_text,
                        "is_kept": chunk_result.is_huntable,
                        "confidence": chunk_result.confidence,
                        "reason": chunk_result.reason,
                        "features": sanitized_features,
                        "ml_details": ml_details,
                        "has_threat_keywords": has_keywords,
                        "has_command_patterns": has_command_patterns,
                        "has_perfect_discriminators": has_perfect_discriminators,
                        "ml_mismatch": ml_mismatch,
                        "ml_prediction_correct": ml_prediction_correct,
                    }

                try:
                    return await asyncio.wait_for(asyncio.to_thread(_process_chunk), timeout=per_chunk_timeout)
                except asyncio.TimeoutError:
                    logger.warning("Chunk %s processing timed out after %s seconds", chunk_id, per_chunk_timeout)
                    return {
                        "chunk_id": chunk_id,
                        "start": start,
                        "end": end,
                        "length": len(chunk_text),
                        "text": chunk_text,
                        "is_kept": False,
                        "confidence": 0.0,
                        "reason": "Processing timed out",
                        "features": {},
                        "ml_details": {"error": "Processing timed out"},
                        "has_threat_keywords": False,
                        "has_command_patterns": False,
                        "has_perfect_discriminators": False,
                        "ml_mismatch": False,
                        "ml_prediction_correct": None,
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.error("Error processing chunk %s: %s", chunk_id, exc)
                    return {
                        "chunk_id": chunk_id,
                        "start": start,
                        "end": end,
                        "length": len(chunk_text),
                        "text": chunk_text,
                        "is_kept": False,
                        "confidence": 0.0,
                        "reason": f"Error: {exc}",
                        "features": {},
                        "ml_details": {"error": str(exc)},
                        "has_threat_keywords": False,
                        "has_command_patterns": False,
                        "has_perfect_discriminators": False,
                        "ml_mismatch": False,
                        "ml_prediction_correct": None,
                    }

        for chunk_id, (start, end, chunk_text) in enumerate(original_chunks[:chunk_limit]):
            chunk_analysis_results.append(analyze_chunk(chunk_id, start, end, chunk_text))

        chunk_analysis = await asyncio.gather(*chunk_analysis_results)
        chunk_analysis = [chunk for chunk in chunk_analysis if chunk is not None]
        chunk_analysis.sort(key=lambda chunk: chunk["chunk_id"])

        cost_estimate = await asyncio.to_thread(estimate_gpt4o_cost, article.content, use_filtering=True)

        original_tokens = len(article.content) // 4
        filtered_tokens = len(filter_result.filtered_content or "") // 4
        tokens_saved = max(original_tokens - filtered_tokens, 0)
        input_cost_per_token = 5.0 / 1_000_000
        actual_cost_savings = tokens_saved * input_cost_per_token

        processed_predictions = [
            chunk for chunk in chunk_analysis if chunk.get("ml_prediction_correct") is not None
        ]
        ml_correct = len([chunk for chunk in processed_predictions if chunk["ml_prediction_correct"]])
        ml_total = len(processed_predictions)
        ml_accuracy = (ml_correct / ml_total * 100) if ml_total > 0 else 0
        ml_mismatches = len([chunk for chunk in processed_predictions if chunk.get("ml_mismatch")])

        return {
            "article_id": article_id,
            "article_title": article.title,
            "content_length": len(article.content),
            "chunk_size": chunk_size,
            "overlap": overlap,
            "min_confidence": min_confidence,
            "total_chunks": total_chunks,
            "kept_chunks": kept_chunks,
            "removed_chunks": removed_chunks,
            "chunk_analysis": chunk_analysis,
            "processing_summary": {
                "processed_chunks": len(chunk_analysis),
                "total_chunks": total_chunks,
                "chunk_limit_applied": chunk_limit < total_chunks,
                "concurrency_limit": concurrency_limit,
                "per_chunk_timeout_seconds": per_chunk_timeout,
                "full_analysis": full_analysis,
                "max_chunks_setting": max_chunks_setting,
                "remaining_chunks": max(total_chunks - len(chunk_analysis), 0),
            },
            "filter_result": {
                "is_huntable": filter_result.is_huntable,
                "confidence": filter_result.confidence,
                "cost_savings": filter_result.cost_savings,
                "kept_chunks_count": kept_chunks,
                "removed_chunks_count": removed_chunks,
            },
            "ml_stats": {
                "total_predictions": ml_total,
                "correct_predictions": ml_correct,
                "accuracy_percent": ml_accuracy,
                "mismatches": ml_mismatches,
            },
            "cost_estimate": cost_estimate,
            "filtering_stats": {
                "reduction_percent": (removed_chunks / total_chunks * 100) if total_chunks > 0 else 0,
                "content_reduction_percent": (
                    (len(article.content) - len(filter_result.filtered_content)) / len(article.content) * 100
                    if len(article.content) > 0
                    else 0
                ),
                "tokens_saved": tokens_saved,
                "cost_savings": actual_cost_savings,
            },
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Chunk debug error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Chunk debug failed: {exc}") from exc

