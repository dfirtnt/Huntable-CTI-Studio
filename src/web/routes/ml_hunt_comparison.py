"""
ML vs Hunt comparison endpoints.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(prefix="/api/ml-hunt-comparison", tags=["ML Hunt Comparison"])


@router.get("/stats")
async def get_model_comparison_stats(model_version: str | None = None):
    """Get comparison statistics for model versions."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_service import ChunkAnalysisService

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
    article_id: int | None = None,
    model_version: str | None = None,
    hunt_score_min: float | None = None,
    hunt_score_max: float | None = None,
    ml_prediction: bool | None = None,
    hunt_prediction: bool | None = None,
    agreement: bool | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Get chunk analysis results with filtering."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_service import ChunkAnalysisService

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
        from src.database.manager import DatabaseManager
        from src.services.chunk_analysis_service import ChunkAnalysisService

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

        log_file = "/tmp/backfill_logs.txt"

        # First, try reading from log file inside Docker container (most reliable)
        try:
            result = subprocess.run(
                ["docker", "exec", "cti_web", "cat", log_file],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout:
                content = result.stdout.strip()
                if content:
                    return {"success": True, "logs": content}
        except FileNotFoundError:
            # Docker not available - try reading from host filesystem
            logger.debug("Docker command not found, trying host filesystem")
            if os.path.exists(log_file):
                try:
                    with open(log_file) as file:
                        content = file.read().strip()
                    if content:
                        return {"success": True, "logs": content}
                except Exception as file_error:  # noqa: BLE001
                    logger.warning(f"Could not read log file {log_file}: {file_error}")
        except subprocess.TimeoutExpired:
            logger.warning("Docker exec command timed out reading log file")
        except Exception as docker_error:  # noqa: BLE001
            logger.debug(f"Could not read log file from container: {docker_error}")

        # Fallback: try reading Docker container stdout logs
        try:
            result = subprocess.run(
                ["docker", "exec", "cti_web", "tail", "-n", "100", "/proc/1/fd/1"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout:
                lines = result.stdout.split("\n")
                filtered_lines = [
                    line
                    for line in lines
                    if any(
                        keyword in line.lower()
                        for keyword in [
                            "processing article",
                            "progress:",
                            "processing complete",
                            "chunk_analysis_backfill",
                            "starting backfill",
                            "backfill",
                            "processing failed",
                            "chunk analysis",
                        ]
                    )
                ]

                if filtered_lines:
                    log_content = "🚀 Real-time Processing Logs:\n\n" + "\n".join(filtered_lines[-30:])
                    return {"success": True, "logs": log_content}
        except FileNotFoundError:
            logger.debug("Docker command not found (running outside Docker?)")
        except subprocess.TimeoutExpired:
            logger.warning("Docker exec command timed out reading stdout")
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Could not read container logs: {exc}")

        # No logs found - return default message
        return {
            "success": True,
            "logs": "🚀 Real-time Processing Logs:\n\nNo logs available yet. Start processing to see real-time updates.",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Error reading logs: %s", exc, exc_info=True)
        return {"success": False, "logs": f"Error reading logs: {exc}"}


@router.post("/backfill")
async def process_eligible_articles_backfill(min_hunt_score: float = 50.0, min_confidence: float = 0.7):
    """Process all eligible articles through chunk analysis."""
    try:
        import time
        import traceback

        log_file = "/tmp/backfill_logs.txt"

        # Ensure log file directory exists and is writable
        try:
            with open(log_file, "w") as file:
                file.write("🚀 Starting article processing...\n")
                file.write(f"📅 Started at {time.strftime('%H:%M:%S')}\n")
                file.write(f"📊 Processing articles with hunt_score > {min_hunt_score}\n")
                file.write(f"🤖 Using ML model with {min_confidence * 100:.0f}% confidence threshold\n")
                file.write("⏳ This may take several minutes...\n\n")
            logger.info(f"Initialized log file at {log_file}")
        except Exception as log_init_error:
            logger.error(f"Failed to initialize log file at {log_file}: {log_init_error}")
            # Continue anyway - logging will fall back to logger

        def process_articles_sync():
            """Synchronous function to process articles (runs in thread pool)."""
            from src.database.manager import DatabaseManager
            from src.services.chunk_analysis_backfill import ChunkAnalysisBackfillService

            db_manager = None
            sync_db = None
            try:
                logger.info(f"Background task started: processing articles with hunt_score > {min_hunt_score}")

                # Write to log file
                try:
                    with open(log_file, "a") as file:
                        file.write(f"[{time.strftime('%H:%M:%S')}] Initializing database connection...\n")
                except Exception:
                    pass  # Log file write failed, continue with logger

                db_manager = DatabaseManager()
                sync_db = db_manager.get_session()

                try:
                    with open(log_file, "a") as file:
                        file.write(f"[{time.strftime('%H:%M:%S')}] Starting chunk analysis backfill service...\n")
                except Exception:
                    pass

                service = ChunkAnalysisBackfillService(sync_db)
                results = service.backfill_all(
                    min_hunt_score=min_hunt_score,
                    min_confidence=min_confidence,
                )

                # Write completion to log file
                try:
                    with open(log_file, "a") as file:
                        file.write("\n✅ Processing Complete!\n")
                        file.write(
                            f"📊 Results: {results.get('successful', 0)}/{results.get('total_eligible', 0)} articles processed successfully\n"
                        )
                        file.write(f"❌ Failed: {results.get('failed', 0)} articles\n")
                        file.write(f"⏱️ Total Duration: {results.get('duration', 'Unknown')}\n")
                        file.write(f"Processing finished at {time.strftime('%H:%M:%S')}\n")
                except Exception:
                    pass

                logger.info(
                    f"Backfill completed: {results.get('successful', 0)}/{results.get('total_eligible', 0)} successful"
                )
                return results

            except Exception as task_error:  # noqa: BLE001
                error_msg = str(task_error)
                error_trace = traceback.format_exc()
                logger.error(f"Error in background processing task: {error_msg}\n{error_trace}")

                # Write error to log file
                try:
                    with open(log_file, "a") as file:
                        file.write("\n❌ Processing Failed!\n")
                        file.write(f"Error: {error_msg}\n")
                        file.write(f"Time: {time.strftime('%H:%M:%S')}\n")
                        file.write(f"Traceback:\n{error_trace}\n")
                except Exception:
                    pass  # Log file write failed, error already logged

                raise  # Re-raise to ensure task failure is visible
            finally:
                if sync_db:
                    try:
                        sync_db.close()
                    except Exception:
                        pass

        async def process_articles():
            """Async wrapper that runs blocking operation in thread pool."""
            # Use get_running_loop() instead of get_event_loop() to avoid creating new loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, but we're in async context - this shouldn't happen
                raise RuntimeError("process_articles() must be called from async context")
            try:
                # Run blocking operation in thread pool to avoid blocking event loop
                results = await loop.run_in_executor(None, process_articles_sync)
                return results
            except Exception as e:
                logger.error(f"Error in async wrapper: {e}", exc_info=True)
                raise

        # Create background task with error handling
        task = asyncio.create_task(process_articles())

        # Add done callback to log completion/failure
        def task_done_callback(task):
            try:
                if task.exception():
                    logger.error(f"Background task failed: {task.exception()}")
            except Exception:
                pass

        task.add_done_callback(task_done_callback)

        return {
            "success": True,
            "message": "Processing started in background",
            "min_hunt_score": min_hunt_score,
            "min_confidence": min_confidence,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Error starting article processing: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/summary")
async def get_comparison_summary():
    """Get summary statistics for the comparison."""
    try:
        from src.database.manager import DatabaseManager
        from src.database.models import MLModelVersionTable
        from src.services.chunk_analysis_service import ChunkAnalysisService

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
