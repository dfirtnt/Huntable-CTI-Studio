"""
Debug and diagnostic endpoints.
"""

from __future__ import annotations

import asyncio
import os

import numpy as np
from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.utils.llm_optimizer import GPT4O_INPUT_COST_PER_MILLION_TOKENS, estimate_gpt4o_cost  # Backward compatibility
from src.web.dependencies import get_content_filter, logger

router = APIRouter(tags=["Debug"])

_CHUNK_DEBUG_PROGRESS_TTL_SECONDS = 300


def _redis_client():
    """Same REDIS_URL resolution used by tasks.py/health.py.

    The web service runs multiple uvicorn workers (docker-compose.yml
    --workers 2), so chunk-debug progress must live in Redis rather than
    process memory -- a poll can land on a different worker than the one
    running the analysis.
    """
    import redis

    redis_url = os.getenv("REDIS_URL") or (
        "redis://localhost:6379/0" if os.getenv("APP_ENV") == "test" else "redis://redis:6379/0"
    )
    return redis.from_url(redis_url, decode_responses=True)


def _chunk_debug_progress_key(article_id: int) -> str:
    return f"chunk_debug_progress:{article_id}"


def _init_chunk_debug_progress(
    article_id: int,
    *,
    total_chunks: int,
    chunk_limit_applied: bool,
    concurrency_limit: int,
    per_chunk_timeout_seconds: float,
) -> None:
    """Best-effort: a Redis outage should degrade progress reporting, not the analysis itself."""
    try:
        client = _redis_client()
        try:
            key = _chunk_debug_progress_key(article_id)
            client.hset(
                key,
                mapping={
                    "processed_chunks": 0,
                    "total_chunks": total_chunks,
                    "chunk_limit_applied": int(chunk_limit_applied),
                    "concurrency_limit": concurrency_limit,
                    "per_chunk_timeout_seconds": per_chunk_timeout_seconds,
                },
            )
            client.expire(key, _CHUNK_DEBUG_PROGRESS_TTL_SECONDS)
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chunk-debug progress init failed for article %s: %s", article_id, exc)


def _clear_chunk_debug_progress(article_id: int) -> None:
    try:
        client = _redis_client()
        try:
            client.delete(_chunk_debug_progress_key(article_id))
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chunk-debug progress cleanup failed for article %s: %s", article_id, exc)


def _read_chunk_debug_progress(article_id: int) -> dict | None:
    try:
        client = _redis_client()
        try:
            data = client.hgetall(_chunk_debug_progress_key(article_id))
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chunk-debug progress read failed for article %s: %s", article_id, exc)
        return None

    if not data:
        return None
    return {
        "processed_chunks": int(data.get("processed_chunks", 0)),
        "total_chunks": int(data.get("total_chunks", 0)),
        "chunk_limit_applied": bool(int(data.get("chunk_limit_applied", 0))),
        "concurrency_limit": int(data.get("concurrency_limit", 0)),
        "per_chunk_timeout_seconds": float(data.get("per_chunk_timeout_seconds", 0)),
    }


def _humanize_feature_name(name: str) -> str:
    """cmdline_artifact_count -> 'cmdline artifact count', for use mid-sentence."""
    return name.replace("_", " ").strip()


def _build_chunk_reason(is_huntable: bool, feature_contribution: dict[str, float] | None) -> str:
    """Per-chunk reason for the Junk Filter Tuning modal.

    ContentFilter.filter_content's own reason ("Content filtered successfully" /
    "No huntable content found") describes a whole-article filter pass, not a
    single chunk's keep/remove decision -- reused per-chunk, "Content filtered
    successfully" reads as "this chunk was filtered out" when it means the
    opposite. This names the chunk's actual outcome and, when the model exposes
    feature importances, the top contributing feature so the reason answers
    what a tuning UI exists to answer.
    """
    top_feature = next(iter(feature_contribution), None) if feature_contribution else None

    if is_huntable:
        if top_feature:
            return f"Kept - {_humanize_feature_name(top_feature)} was the strongest signal"
        return "Kept - huntable content detected"

    if top_feature:
        return f"Not kept - confidence stayed below threshold ({_humanize_feature_name(top_feature)} was the strongest signal)"
    return "Not kept - no huntable content found"


def calculate_filtered_costs(
    original_length: int,
    filtered_length: int,
    prompt_tokens: int = 500,
    input_rate_per_million: float = GPT4O_INPUT_COST_PER_MILLION_TOKENS,
) -> dict:
    """
    Estimate token counts and costs for filtered content.

    Uses a simple 4 chars/token heuristic and clamps filtered tokens to the original size
    so estimates never exceed the pre-filtered content.
    """
    original_tokens = max(int(round(original_length / 4)), 0)
    filtered_tokens = max(int(round(filtered_length / 4)), 0)
    filtered_tokens = min(filtered_tokens, original_tokens)

    tokens_saved = max(original_tokens - filtered_tokens, 0)
    cost_savings = (tokens_saved * input_rate_per_million) / 1_000_000

    prompt_tokens = max(prompt_tokens, 0)
    input_tokens = filtered_tokens + prompt_tokens
    input_cost = (input_tokens * input_rate_per_million) / 1_000_000

    return {
        "original_tokens": original_tokens,
        "filtered_tokens": filtered_tokens,
        "tokens_saved": tokens_saved,
        "cost_savings": cost_savings,
        "prompt_tokens": prompt_tokens,
        "input_tokens": input_tokens,
        "input_cost": input_cost,
        "rate_per_million": input_rate_per_million,
    }


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
        hunt_score = article.article_metadata.get("threat_hunting_score")
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

        _init_chunk_debug_progress(
            article_id,
            total_chunks=chunk_limit,
            chunk_limit_applied=chunk_limit < total_chunks,
            concurrency_limit=concurrency_limit,
            per_chunk_timeout_seconds=per_chunk_timeout,
        )

        async def analyze_chunk(chunk_id: int, start: int, end: int, chunk_text: str):
            async with semaphore:

                def _extract_for_version() -> dict[str, float]:
                    """Dispatch on the filter's feature_version so the chunk debugger
                    uses the SAME featurizer the live model was trained with. Hard-coding
                    v1's extract_features() here caused a shape mismatch against v2/v3
                    models and surfaced as 'ML processing failed' in the UI.
                    """
                    version = getattr(content_filter, "feature_version", "v1")
                    if version == "v3":
                        return content_filter.extract_features_v3(chunk_text)
                    if version == "v2":
                        return content_filter.extract_features_v2(chunk_text)
                    return content_filter.extract_features(chunk_text, hunt_score, include_new_features=True)

                def _process_chunk():
                    chunk_result = content_filter.filter_content(
                        chunk_text,
                        min_confidence,
                        max(len(chunk_text), 1),
                        hunt_score,
                    )

                    features = _extract_for_version()
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
                            ml_features = _extract_for_version()
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
                        except Exception:  # noqa: BLE001
                            ml_details = {"error": "ML processing failed"}

                    # Check for keywords and patterns using threat hunting scorer
                    from src.utils.content import ThreatHuntingScorer

                    hunt_result = ThreatHuntingScorer.score_threat_hunting_content(
                        "Content Filter Analysis", chunk_text
                    )

                    has_keywords = hunt_result.get("good_keyword_matches", [])
                    has_command_patterns = hunt_result.get("lolbas_matches", [])
                    has_perfect_discriminators = hunt_result.get("perfect_keyword_matches", [])

                    has_keywords = len(has_keywords) > 0
                    has_command_patterns = len(has_command_patterns) > 0
                    has_perfect_discriminators = len(has_perfect_discriminators) > 0

                    ml_prediction_correct = None
                    ml_mismatch = False
                    if ml_details and "prediction" in ml_details:
                        ml_prediction_correct = ml_details["prediction"] == (1 if chunk_result.is_huntable else 0)
                        ml_mismatch = not ml_prediction_correct

                    return {
                        "chunk_id": chunk_id,
                        "start": start,
                        "end": end,
                        "length": len(chunk_text),
                        "text": chunk_text,
                        "is_kept": chunk_result.is_huntable,
                        "confidence": chunk_result.confidence,
                        "reason": _build_chunk_reason(
                            chunk_result.is_huntable, ml_details.get("feature_contribution") if ml_details else None
                        ),
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
                except TimeoutError:
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
                        "ml_details": {"error": "ML processing failed"},
                        "has_threat_keywords": False,
                        "has_command_patterns": False,
                        "has_perfect_discriminators": False,
                        "ml_mismatch": False,
                        "ml_prediction_correct": None,
                    }

        # One shared client for the whole run rather than one per chunk -- a
        # full analysis can complete over 1,000 chunks, and opening a fresh
        # Redis connection per increment would add real per-chunk overhead.
        try:
            progress_redis_client = _redis_client()
        except Exception as exc:  # noqa: BLE001
            progress_redis_client = None
            logger.warning("chunk-debug progress client unavailable for article %s: %s", article_id, exc)

        def _increment_chunk_debug_progress() -> None:
            if progress_redis_client is None:
                return
            try:
                progress_redis_client.hincrby(_chunk_debug_progress_key(article_id), "processed_chunks", 1)
            except Exception as exc:  # noqa: BLE001
                logger.warning("chunk-debug progress increment failed for article %s: %s", article_id, exc)

        async def _analyze_chunk_and_track(chunk_id: int, start: int, end: int, chunk_text: str):
            result = await analyze_chunk(chunk_id, start, end, chunk_text)
            _increment_chunk_debug_progress()
            return result

        for chunk_id, (start, end, chunk_text) in enumerate(original_chunks[:chunk_limit]):
            chunk_analysis_results.append(_analyze_chunk_and_track(chunk_id, start, end, chunk_text))

        try:
            chunk_analysis = await asyncio.gather(*chunk_analysis_results)
        finally:
            if progress_redis_client is not None:
                progress_redis_client.close()
            _clear_chunk_debug_progress(article_id)
        chunk_analysis = [chunk for chunk in chunk_analysis if chunk is not None]
        chunk_analysis.sort(key=lambda chunk: chunk["chunk_id"])

        cost_estimate = await asyncio.to_thread(estimate_gpt4o_cost, article.content, use_filtering=True)

        original_tokens = len(article.content) // 4
        filtered_tokens = len(filter_result.filtered_content or "") // 4
        tokens_saved = max(original_tokens - filtered_tokens, 0)
        input_cost_per_token = GPT4O_INPUT_COST_PER_MILLION_TOKENS / 1_000_000
        actual_cost_savings = tokens_saved * input_cost_per_token

        processed_predictions = [chunk for chunk in chunk_analysis if chunk.get("ml_prediction_correct") is not None]
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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/api/articles/{article_id}/chunk-debug/progress")
async def api_chunk_debug_progress(article_id: int):
    """Poll-friendly progress snapshot for an in-flight chunk-debug analysis.

    A long analysis (article 7216's 1,250 chunks took 62s) previously gave no
    indication of size or progress until the whole request finished. The main
    endpoint writes progress to Redis as chunks complete; this reads it back
    so the loading modal can poll instead of guessing. Redis, not process
    memory, because the poll and the analysis can land on different uvicorn
    workers (docker-compose.yml --workers 2).
    """
    progress = _read_chunk_debug_progress(article_id)
    if progress is None:
        return {"in_progress": False, "processed_chunks": 0, "total_chunks": 0}
    return {"in_progress": True, **progress}
