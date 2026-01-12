"""
Embedding-related API routes.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(tags=["Embeddings"])


@router.get("/api/embeddings/stats")
async def api_embedding_stats():
    """Get statistics about embedding coverage and usage."""
    try:
        from src.services.rag_service import get_rag_service

        rag_service = get_rag_service()
        stats = await rag_service.get_embedding_coverage()
        return stats

    except Exception as exc:  # noqa: BLE001
        logger.error("Embedding stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/embeddings/update")
async def api_update_embeddings(request: Request):
    """
    Trigger embedding update for articles without embeddings.
    """
    try:
        import time
        from celery import Celery
        from src.services.rag_service import get_rag_service

        body = await request.json()
        batch_size = body.get("batch_size", 50)

        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.retroactive_embed_all_articles",
            args=[batch_size],
            queue="default",
        )

        rag_service = get_rag_service()
        stats = await rag_service.get_embedding_coverage()

        return {
            "success": True,
            "message": "Embedding update task started",
            "task_id": task.id,
            "batch_size": batch_size,
            "estimated_articles": stats.get("pending_embeddings", 0),
            "current_coverage": stats.get("embedding_coverage_percent", 0),
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Embedding update error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/embeddings/logs")
async def get_embedding_logs():
    """Get real-time embedding processing logs."""
    try:
        import subprocess

        log_file = "/tmp/embedding_logs.txt"
        
        # First, try reading from log file inside Docker container (most reliable)
        try:
            result = subprocess.run(
                ["docker", "exec", "cti_worker", "cat", log_file],
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
                    with open(log_file, "r") as file:
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
                ["docker", "exec", "cti_worker", "tail", "-n", "100", "/proc/1/fd/1"],
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
                            "embedding",
                            "batch",
                            "processing",
                            "processed",
                            "complete",
                            "failed",
                            "error",
                        ]
                    )
                ]

                if filtered_lines:
                    log_content = "🚀 Real-time Embedding Processing Logs:\n\n" + "\n".join(filtered_lines[-30:])
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
            "logs": "🚀 Real-time Embedding Processing Logs:\n\nNo logs available yet. Start processing to see real-time updates.",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Error reading embedding logs: %s", exc, exc_info=True)
        return {"success": False, "logs": f"Error reading logs: {exc}"}


@router.post("/api/articles/{article_id}/embed")
async def api_generate_embedding(article_id: int):
    """
    Generate embedding for a specific article.
    """
    try:
        from src.worker.celery_app import generate_article_embedding

        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Check if embedding exists (handle numpy array)
        has_embedding = article.embedding is not None
        if isinstance(article.embedding, list):
            has_embedding = len(article.embedding) > 0
        
        if has_embedding:
            return {
                "status": "already_embedded",
                "message": f"Article {article_id} already has an embedding",
                "embedded_at": article.embedded_at,
            }

        task = generate_article_embedding.delay(article_id)

        return {
            "status": "task_submitted",
            "task_id": task.id,
            "message": f"Embedding generation started for article {article_id}",
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Generate embedding error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

