"""
Health and diagnostics endpoints for the Huntable CTI Studio FastAPI application.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint for monitoring."""
    try:
        stats = await async_db_manager.get_database_stats()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "status": "connected",
                "sources": stats["total_sources"],
                "articles": stats["total_articles"],
            },
            "version": "4.0.0",
        }
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="Service unhealthy") from exc


@router.get("/api/health")
async def api_health_check() -> Dict[str, Any]:
    """API health check endpoint."""
    try:
        stats = await async_db_manager.get_database_stats()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "status": "connected",
                "sources": stats["total_sources"],
                "articles": stats["total_articles"],
            },
            "version": "4.0.0",
        }
    except Exception as exc:
        logger.error("API health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/health/database")
async def api_database_health() -> Dict[str, Any]:
    """Database health check with detailed statistics."""
    try:
        stats = await async_db_manager.get_database_stats()
        dedup_stats = await async_db_manager.get_deduplication_stats()
        performance_metrics = await async_db_manager.get_performance_metrics()
        corruption_stats = await async_db_manager.get_corruption_stats()

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "connection": "connected",
                "total_articles": stats["total_articles"],
                "total_sources": stats["total_sources"],
                "simhash": {
                    "coverage": f"{dedup_stats.get('simhash_coverage', 0)}%",
                },
                "deduplication": {
                    "total_articles": stats["total_articles"],
                    "unique_urls": dedup_stats.get("unique_urls", 0),
                    "duplicate_rate": f"{dedup_stats.get('duplicate_rate', 0)}%",
                },
                "corruption": {
                    "count": corruption_stats.get("corrupted_count", 0),
                    "examples": corruption_stats.get("examples", []),
                },
                "performance": performance_metrics,
            },
        }
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/health/deduplication")
async def api_deduplication_health() -> Dict[str, Any]:
    """Deduplication system health check."""
    try:
        dedup_stats = await async_db_manager.get_deduplication_stats()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "deduplication": {
                "exact_duplicates": {
                    "content_hash_duplicates": dedup_stats.get(
                        "content_hash_duplicates", 0
                    ),
                    "duplicate_details": dedup_stats.get("duplicate_details", []),
                },
                "near_duplicates": {
                    "potential_near_duplicates": dedup_stats.get("near_duplicates", 0),
                    "simhash_coverage": f"{dedup_stats.get('simhash_coverage', 0)}%",
                },
                "simhash_buckets": {
                    "bucket_distribution": dedup_stats.get("bucket_distribution", []),
                    "most_active_bucket": dedup_stats.get("most_active_bucket"),
                },
            },
        }
    except Exception as exc:
        logger.error("Deduplication health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/health/services")
async def api_services_health() -> Dict[str, Any]:
    """External services health check."""
    try:
        services_status: Dict[str, Any] = {}

        # Check Redis
        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            redis_info = redis_client.info()
            services_status["redis"] = {
                "status": "healthy",
                "info": {
                    "used_memory": redis_info.get("used_memory", 0),
                    "connected_clients": redis_info.get("connected_clients", 0),
                },
            }
        except Exception as redis_exc:
            services_status["redis"] = {
                "status": "unhealthy",
                "error": str(redis_exc),
            }

        # Check LMStudio
        try:
            lmstudio_url = os.getenv(
                "LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1"
            )
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{lmstudio_url}/models", timeout=5.0)
                if response.status_code == 200:
                    models_data = response.json()
                    services_status["lmstudio"] = {
                        "status": "healthy",
                        "models_available": len(models_data.get("data", [])),
                        "models": [
                            model.get("id", "unknown")
                            for model in models_data.get("data", [])
                        ],
                    }
                else:
                    services_status["lmstudio"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}",
                    }
        except Exception as lmstudio_exc:
            services_status["lmstudio"] = {
                "status": "unhealthy",
                "error": str(lmstudio_exc),
            }

        # Check LangFuse
        try:
            from src.utils.langfuse_client import (
                get_langfuse_client,
                is_langfuse_enabled,
            )

            if is_langfuse_enabled():
                client = get_langfuse_client()
                if client:
                    # Try to flush to test connection (non-blocking)
                    try:
                        client.flush()
                        services_status["langfuse"] = {
                            "status": "healthy",
                            "configured": True,
                        }
                    except Exception as flush_exc:
                        services_status["langfuse"] = {
                            "status": "unhealthy",
                            "error": f"Flush failed: {str(flush_exc)}",
                            "configured": True,
                        }
                else:
                    services_status["langfuse"] = {
                        "status": "unhealthy",
                        "error": "Client initialization failed",
                        "configured": False,
                    }
            else:
                services_status["langfuse"] = {
                    "status": "not_configured",
                    "configured": False,
                    "message": "LangFuse not configured (missing keys)",
                }
        except Exception as langfuse_exc:
            services_status["langfuse"] = {
                "status": "unhealthy",
                "error": str(langfuse_exc),
                "configured": False,
            }

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": services_status,
        }
    except Exception as exc:
        logger.error("Services health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/health/celery")
async def api_celery_health() -> Dict[str, Any]:
    """Celery workers health check."""
    try:
        celery_status: Dict[str, Any] = {}

        try:
            from src.worker.celery_app import celery_app

            inspect = celery_app.control.inspect(timeout=2.0)  # 2 second timeout
            active_workers = inspect.active()

            if active_workers:
                celery_status["workers"] = {
                    "status": "healthy",
                    "active_workers": len(active_workers),
                }
            else:
                celery_status["workers"] = {
                    "status": "unhealthy",
                    "error": "No active workers found",
                }
        except Exception as worker_exc:
            celery_status["workers"] = {
                "status": "unhealthy",
                "error": str(worker_exc),
            }

        celery_status["broker"] = {
            "status": "healthy",
            "url": "redis://redis:6379/0",
        }
        celery_status["result_backend"] = {
            "status": "healthy",
            "backend": "redis://redis:6379/0",
        }

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "celery": celery_status,
        }
    except Exception as exc:
        logger.error("Celery health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/health/ingestion")
async def api_ingestion_health() -> Dict[str, Any]:
    """Ingestion analytics health check."""
    try:
        ingestion_stats = await async_db_manager.get_ingestion_analytics()
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "ingestion": ingestion_stats,
        }
    except Exception as exc:
        logger.error("Ingestion health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }
