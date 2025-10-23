"""
Router registration helpers for the CTI Scraper FastAPI application.

Individual router modules should expose an ``router`` instance that is
included from :func:`register_routes`.
"""

from __future__ import annotations

from fastapi import FastAPI

from . import actions, analytics, ai, articles, backup, chat, dashboard, debug, embeddings, evaluation, export, feedback, health, metrics, ml_hunt_comparison, models, pages, pdf, search, sources, tasks, scrape
from .annotations import router as annotation_router
from ..gpt4o_optimized_endpoint import router as gpt4o_router


def register_routes(app: FastAPI) -> None:
    """
    Register all route modules with the provided FastAPI application.

    The concrete router imports are intentionally local to avoid
    expensive module imports during application startup when only some
    routers are required (e.g., for selective testing).
    """
    app.include_router(pages.router)
    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(backup.router)
    app.include_router(analytics.router)
    app.include_router(articles.router)
    app.include_router(search.router)
    app.include_router(embeddings.router)
    app.include_router(chat.router)
    app.include_router(evaluation.router)
    app.include_router(feedback.router)
    app.include_router(models.router)
    app.include_router(ai.router)
    app.include_router(annotation_router)
    app.include_router(tasks.router)
    app.include_router(scrape.router)
    app.include_router(debug.router)
    app.include_router(export.router)
    app.include_router(pdf.router)
    app.include_router(metrics.router)
    app.include_router(dashboard.router)
    app.include_router(actions.router)
    app.include_router(ml_hunt_comparison.router)
    app.include_router(gpt4o_router)
