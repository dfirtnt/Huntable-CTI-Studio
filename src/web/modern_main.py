"""
FastAPI application entrypoint for the CTI Scraper platform.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from celery import Celery
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.database.async_manager import async_db_manager
from src.services.source_sync import SourceSyncService
from src.web.dependencies import DEFAULT_SOURCE_USER_AGENT, logger, templates
from src.web.routes import register_routes
from src.web.utils.openai_helpers import (
    build_openai_payload as _build_openai_payload,
    extract_openai_summary as _extract_openai_summary,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown events."""
    logger.info("Starting CTI Scraper application…")

    try:
        await async_db_manager.create_tables()
        logger.info("Database tables created/verified successfully")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create database tables: %s", exc)
        raise

    try:
        existing_identifiers = await async_db_manager.list_source_identifiers()

        if not existing_identifiers or len(existing_identifiers) < 5:
            config_path = Path(os.getenv("SOURCES_CONFIG", "config/sources.yaml"))
            if config_path.exists():
                logger.info(
                    "Initial setup detected (%d sources), seeding from %s",
                    len(existing_identifiers),
                    config_path,
                )
                sync_service = SourceSyncService(config_path, async_db_manager)
                await sync_service.sync()
            else:
                logger.warning("Source config seed file missing: %s", config_path)
        else:
            logger.info(
                "Skipping YAML sync; %d sources already present",
                len(existing_identifiers),
            )

        stats = await async_db_manager.get_database_stats()
        logger.info(
            "Database connection successful: %s sources, %s articles",
            stats["total_sources"],
            stats["total_articles"],
        )

        updated_agents = await async_db_manager.set_robots_user_agent_for_all(
            DEFAULT_SOURCE_USER_AGENT
        )
        if updated_agents:
            logger.info("Normalized robots user-agent for %s sources", updated_agents)

        # Disabled startup collection to prevent UI hanging
        # try:
        #     celery_app = Celery("cti_scraper")
        #     celery_app.config_from_object("src.worker.celeryconfig")

        #     sources = await async_db_manager.list_sources()
        #     active_sources = [source for source in sources if getattr(source, "active", True)]

        #     logger.info("Triggering startup collection for %s active sources…", len(active_sources))

        #     for source in active_sources:
        #         try:
        #             task = celery_app.send_task(
        #                 "src.worker.celery_app.collect_from_source",
        #                 args=[source.id],
        #                 queue="collection",
        #             )
        #             logger.info(
        #                 "Started collection task for %s (ID: %s) - Task: %s",
        #                 source.name,
        #                 source.id,
        #                 task.id,
        #             )
        #         except Exception as exc:  # noqa: BLE001
        #             logger.error("Failed to start collection for %s: %s", source.name, exc)
        # except Exception as exc:  # noqa: BLE001
        #     logger.error("Failed to trigger startup collection: %s", exc)
        
        logger.info("Startup collection disabled to prevent UI performance issues")
    except Exception as exc:  # noqa: BLE001
        logger.error("Database connection failed: %s", exc)
        raise

    yield

    logger.info("Shutting down CTI Scraper application…")
    await async_db_manager.close()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="CTI Scraper - Modern Threat Intelligence Platform",
    description="Enterprise-grade threat intelligence aggregation and analysis platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

register_routes(app)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(content={"detail": "Not found"}, status_code=404)

    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Page not found"},
        status_code=404,
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: HTTPException):
    """Handle 500 errors."""
    logger.error("Internal server error: %s", exc)
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Internal server error"},
        status_code=500,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.web.modern_main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
