"""
ML vs Hunt comparison endpoints.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(prefix="/api/ml-hunt-comparison", tags=["ML Hunt Comparison"])


@router.get("/stats")
async def get_model_comparison_stats(model_version: Optional[str] = None):
    """Get comparison statistics for model versions."""
    try:
        from src.services.chunk_analysis_service import ChunkAnalysisService
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisService(sync_db)
            stats = service.get_model_comparison_stats(model_version)
        finally:
            sync_db.close()
        return {"success": True, "stats": stats}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting model comparison stats: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/results")
async def get_chunk_analysis_results(
    article_id: Optional[int] = None,
    model_version: Optional[str] = None,
    hunt_score_min: Optional[float] = None,
    hunt_score_max: Optional[float] = None,
    ml_prediction: Optional[bool] = None,
    hunt_prediction: Optional[bool] = None,
    agreement: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get chunk analysis results with filtering."""
    try:
        from src.services.chunk_analysis_service import ChunkAnalysisService
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisService(sync_db)
            results = service.get_chunk_analysis_results(
                article_id=article_id,
                model_version=model_version,
                hunt_score_min=hunt_score_min,
                hunt_score_max=hunt_score_max,
                ml_prediction=ml_prediction,
                hunt_prediction=hunt_prediction,
                agreement=agreement,
                limit=limit,
                offset=offset,
            )
        finally:
            sync_db.close()
        return {"success": True, "results": results, "count": len(results)}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting chunk analysis results: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/model-versions")
async def get_available_model_versions():
    """Get list of available model versions."""
    try:
        from src.services.chunk_analysis_service import ChunkAnalysisService
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisService(sync_db)
            versions = service.get_available_model_versions()
        finally:
            sync_db.close()
        return {"success": True, "model_versions": versions}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting model versions: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/eligible-count")
async def get_eligible_articles_count(min_hunt_score: float = 50.0):
    """Get count of articles eligible for chunk analysis."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_backfill import ChunkAnalysisBackfillService

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisBackfillService(sync_db)
            eligible = service.get_eligible_articles(min_hunt_score)
            count = len(eligible)
        finally:
            sync_db.close()

        return {"success": True, "count": count, "min_hunt_score": min_hunt_score}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting eligible count: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/logs")
async def get_backfill_logs():
    """Get real-time backfill processing logs."""
    try:
        import subprocess

        try:
            result = subprocess.run(
                ["docker", "exec", "cti_web", "tail", "-n", "50", "/proc/1/fd/1"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                lines = result.stdout.split("\n")
                filtered_lines = [
                    line
                    for line in lines
                    if any(
                        keyword in line
                        for keyword in [
                            "Processing article",
                            "Progress:",
                            "Backfill complete",
                            "chunk_analysis_backfill",
                            "Starting backfill",
                        ]
                    )
                ]

                if filtered_lines:
                    log_content = "🚀 Real-time Processing Logs:\n\n" + "\n".join(filtered_lines[-20:])
                else:
                    log_content = "🚀 Real-time Processing Logs:\n\nNo processing logs found yet..."

                return {"success": True, "logs": log_content}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read container logs: %s", exc)

        log_file = "/tmp/backfill_logs.txt"
        if os.path.exists(log_file):
            with open(log_file, "r") as file:
                content = file.read()
            return {"success": True, "logs": content}

        return {
            "success": True,
            "logs": "🚀 Real-time Processing Logs:\n\nNo logs available yet. Start processing to see real-time updates.",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Error reading logs: %s", exc)
        return {"success": False, "logs": f"Error reading logs: {exc}"}


@router.post("/backfill")
async def process_eligible_articles_backfill(min_hunt_score: float = 50.0, min_confidence: float = 0.7):
    """Process all eligible articles through chunk analysis."""
    try:
        import time

        log_file = "/tmp/backfill_logs.txt"
        with open(log_file, "w") as file:
            file.write("🚀 Starting article processing...\n")
            file.write(f"📅 Started at {time.strftime('%H:%M:%S')}\n")
            file.write(f"📊 Processing articles with hunt_score > {min_hunt_score}\n")
            file.write(f"🤖 Using ML model with {min_confidence*100:.0f}% confidence threshold\n")
            file.write("⏳ This may take several minutes...\n\n")

        async def process_articles():
            from src.database.manager import DatabaseManager
            from src.services.chunk_analysis_backfill import ChunkAnalysisBackfillService

            db_manager = DatabaseManager()
            sync_db = db_manager.get_session()
            try:
                service = ChunkAnalysisBackfillService(sync_db)
                results = service.backfill_all(
                    min_hunt_score=min_hunt_score,
                    min_confidence=min_confidence,
                )

                with open(log_file, "a") as file:
                    file.write("\n✅ Processing Complete!\n")
                    file.write(
                        f"📊 Results: {results['successful']}/{results['total_eligible']} articles processed successfully\n"
                    )
                    file.write(f"❌ Failed: {results['failed']} articles\n")
                    file.write(f"⏱️ Total Duration: {results.get('duration', 'Unknown')}\n")
                    file.write(f"Processing finished at {time.strftime('%H:%M:%S')}\n")

                return results
            finally:
                sync_db.close()

        asyncio.create_task(process_articles())

        return {
            "success": True,
            "message": "Processing started in background",
            "min_hunt_score": min_hunt_score,
            "min_confidence": min_confidence,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error starting article processing: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/summary")
async def get_comparison_summary():
    """Get summary statistics for the comparison."""
    try:
        from src.services.chunk_analysis_service import ChunkAnalysisService
        from src.database.models import MLModelVersionTable
        from src.database.manager import DatabaseManager

        db_manager = DatabaseManager()
        sync_db = db_manager.get_session()
        try:
            service = ChunkAnalysisService(sync_db)
            all_stats = service.get_model_comparison_stats()
            model_versions = service.get_available_model_versions()
            total_model_versions = sync_db.query(MLModelVersionTable).count()
            recent_results = service.get_chunk_analysis_results(limit=1)
            total_results = len(service.get_chunk_analysis_results(limit=50000))
        finally:
            sync_db.close()

        summary = {
            "total_model_versions": total_model_versions,
            "total_chunk_analyses": total_results,
            "model_versions": model_versions,
            "overall_stats": all_stats,
            "last_updated": recent_results[0]["created_at"] if recent_results else None,
        }

        return {"success": True, "summary": summary}
    except Exception as exc:  # noqa: BLE001
        logger.error("Error getting comparison summary: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

