"""
HTML page routes for the Huntable CTI Studio application.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.database.async_manager import async_db_manager
from src.utils.search_parser import parse_boolean_search
from src.web.dependencies import ENVIRONMENT, logger, templates

router = APIRouter()


@router.get("/chat")
async def chat_page(request: Request):
    """Serve the RAG chat interface."""
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page with 3x3 grid layout."""
    try:
        stats = await async_db_manager.get_database_stats()
        sources = await async_db_manager.list_sources()
        recent_articles = await async_db_manager.list_articles(limit=5)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return templates.TemplateResponse(
            "dashboard.html.orig",
            {
                "request": request,
                "stats": stats,
                "sources": sources,
                "recent_articles": recent_articles,
                "current_time": current_time,
                "environment": ENVIRONMENT,
            },
        )
    except Exception as exc:
        logger.error("Dashboard error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics dashboard page."""
    try:
        return templates.TemplateResponse("analytics.html", {"request": request})
    except Exception as exc:
        logger.error("Analytics page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    try:
        return templates.TemplateResponse("settings.html", {"request": request})
    except Exception as exc:
        logger.error("Settings page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/diags", response_class=HTMLResponse)
async def diags_page(request: Request):
    """System diagnostics and health monitoring page combining jobs, health checks, and analytics."""
    try:
        return templates.TemplateResponse(
            "diags.html", {"request": request, "environment": ENVIRONMENT}
        )
    except Exception as exc:
        logger.error("Diagnostics page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/analytics/scraper-metrics", response_class=HTMLResponse)
async def scraper_metrics_page(request: Request):
    """Scraper metrics analytics page."""
    try:
        return templates.TemplateResponse(
            "scraper_metrics.html", {"request": request, "environment": ENVIRONMENT}
        )
    except Exception as exc:
        logger.error("Scraper metrics page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/analytics/hunt-metrics", response_class=HTMLResponse)
async def hunt_metrics_page(request: Request):
    """Hunt scoring metrics analytics page."""
    try:
        return templates.TemplateResponse(
            "hunt_metrics.html", {"request": request, "environment": ENVIRONMENT}
        )
    except Exception as exc:
        logger.error("Hunt metrics page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/analytics/hunt-metrics-demo", response_class=HTMLResponse)
async def hunt_metrics_demo_page(request: Request):
    """Advanced hunt scoring metrics demo page with multidimensional visualizations."""
    try:
        return templates.TemplateResponse(
            "hunt_metrics_demo.html", {"request": request, "environment": ENVIRONMENT}
        )
    except Exception as exc:
        logger.error("Hunt metrics demo page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/sources", response_class=HTMLResponse)
async def sources_list(request: Request):
    """Sources management page."""
    try:
        sources = await async_db_manager.list_sources()
        quality_stats = await async_db_manager.get_source_quality_stats()
        hunt_scores = await async_db_manager.get_source_hunt_scores()

        logger.info("Quality stats returned: %d entries", len(quality_stats))
        logger.info("Hunt scores returned: %d entries", len(hunt_scores))
        for stat in quality_stats[:5]:
            logger.info(
                "Source %s: %s - Rejection rate: %s%%",
                stat["source_id"],
                stat["name"],
                stat["rejection_rate"],
            )

        total_articles = await async_db_manager.get_total_article_count()

        quality_lookup = {stat["source_id"]: stat for stat in quality_stats}
        hunt_score_lookup = {stat["source_id"]: stat for stat in hunt_scores}

        def get_hunt_score(source):
            if source.id in hunt_score_lookup:
                return hunt_score_lookup[source.id].get("avg_hunt_score", 0)
            return 0

        sources_sorted = sorted(sources, key=get_hunt_score, reverse=True)

        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "sources": sources_sorted,
                "quality_stats": quality_lookup,
                "hunt_score_lookup": hunt_score_lookup,
                "total_articles": total_articles,
            },
        )
    except Exception as exc:
        logger.error("Sources list error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request,
    search: Optional[str] = None,
    source: Optional[str] = None,
    source_id: Optional[int] = None,
    threat_hunting_range: Optional[str] = None,
    per_page: Optional[int] = 100,
    page: Optional[int] = 1,
    sort_by: str = "published_at",
    sort_order: str = "desc",
    title_only: Optional[bool] = False,
):
    """Articles listing page with sorting and filtering."""
    try:
        # Get all articles first to calculate total count
        all_articles_unfiltered = await async_db_manager.list_articles()
        sources = await async_db_manager.list_sources()

        source_lookup = {source_.id: source_ for source_ in sources}

        filtered_articles = all_articles_unfiltered

        if search:
            if title_only:
                filtered_articles = [
                    article
                    for article in filtered_articles
                    if search.lower() in article.title.lower()
                ]
            else:
                articles_dict = [
                    {
                        "id": article.id,
                        "title": article.title,
                        "content": article.content,
                        "source_id": article.source_id,
                        "published_at": article.published_at,
                        "canonical_url": article.canonical_url,
                        "metadata": article.article_metadata,
                    }
                    for article in filtered_articles
                ]

                filtered_dicts = parse_boolean_search(search, articles_dict)
                filtered_article_ids = {article["id"] for article in filtered_dicts}
                filtered_articles = [
                    article
                    for article in filtered_articles
                    if article.id in filtered_article_ids
                ]

        if source_id:
            filtered_articles = [
                article
                for article in filtered_articles
                if article.source_id == source_id
            ]
        elif source and source.isdigit():
            source_id = int(source)
            filtered_articles = [
                article
                for article in filtered_articles
                if article.source_id == source_id
            ]

        if threat_hunting_range:
            try:
                if "-" in threat_hunting_range:
                    min_score, max_score = map(float, threat_hunting_range.split("-"))
                    filtered_articles = [
                        article
                        for article in filtered_articles
                        if article.article_metadata
                        and min_score
                        <= article.article_metadata.get("threat_hunting_score", 0)
                        <= max_score
                    ]
            except (ValueError, TypeError):
                pass

        if sort_by == "threat_hunting_score":
            filtered_articles.sort(
                key=lambda x: float(x.article_metadata.get("threat_hunting_score", 0))
                if x.article_metadata and x.article_metadata.get("threat_hunting_score")
                else 0,
                reverse=(sort_order == "desc"),
            )
        elif sort_by == "annotation_count":
            filtered_articles.sort(
                key=lambda x: int(x.article_metadata.get("annotation_count", 0))
                if x.article_metadata
                and x.article_metadata.get("annotation_count") is not None
                else 0,
                reverse=(sort_order == "desc"),
            )
        elif sort_by == "word_count":
            filtered_articles.sort(
                key=lambda x: x.word_count or 0, reverse=(sort_order == "desc")
            )
        else:
            sort_attr = (
                getattr(filtered_articles[0], sort_by, None)
                if filtered_articles
                else None
            )
            if sort_attr is not None:
                if sort_order == "desc":
                    filtered_articles.sort(
                        key=lambda x: (
                            getattr(x, sort_by, ""),
                            -float(x.article_metadata.get("threat_hunting_score", 0))
                            if x.article_metadata
                            and x.article_metadata.get("threat_hunting_score")
                            else 0,
                        ),
                        reverse=True,
                    )
                else:
                    filtered_articles.sort(
                        key=lambda x: (
                            getattr(x, sort_by, ""),
                            float(x.article_metadata.get("threat_hunting_score", 0))
                            if x.article_metadata
                            and x.article_metadata.get("threat_hunting_score")
                            else 0,
                        ),
                        reverse=False,
                    )
            else:
                filtered_articles.sort(
                    key=lambda x: float(
                        x.article_metadata.get("threat_hunting_score", 0)
                    )
                    if x.article_metadata
                    and x.article_metadata.get("threat_hunting_score")
                    else 0,
                    reverse=True,
                )

        total_articles = len(filtered_articles)
        per_page = max(1, min(per_page or 1, 100))
        total_pages = max(1, (total_articles + per_page - 1) // per_page)
        page = max(1, min(page or 1, total_pages))

        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_articles)

        articles = filtered_articles[start_idx:end_idx]

        pagination = {
            "total_articles": total_articles,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "start_idx": start_idx + 1,
            "end_idx": end_idx,
        }

        filters = {
            "search": search or "",
            "source": source or "",
            "source_id": source_id,
            "threat_hunting_range": threat_hunting_range or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
            "title_only": title_only,
        }

        chosen_count = sum(
            1
            for article in filtered_articles
            if article.article_metadata
            and article.article_metadata.get("training_category") == "chosen"
        )
        rejected_count = sum(
            1
            for article in filtered_articles
            if article.article_metadata
            and article.article_metadata.get("training_category") == "rejected"
        )
        unclassified_count = sum(
            1
            for article in filtered_articles
            if not article.article_metadata
            or article.article_metadata.get("training_category")
            not in ["chosen", "rejected"]
        )

        stats = {
            "chosen_count": chosen_count,
            "rejected_count": rejected_count,
            "unclassified_count": unclassified_count,
        }

        return templates.TemplateResponse(
            "articles.html",
            {
                "request": request,
                "articles": articles,
                "sources": sources,
                "source_lookup": source_lookup,
                "pagination": pagination,
                "filters": filters,
                "stats": stats,
            },
        )
    except Exception as exc:
        logger.error("Articles list error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    """Article detail page."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Article not found"},
                status_code=404,
            )

        source = await async_db_manager.get_source(article.source_id)

        return templates.TemplateResponse(
            "article_detail.html",
            {
                "request": request,
                "article": article,
                "source": source,
                "chatgpt_content_limit": int(
                    os.getenv("CHATGPT_CONTENT_LIMIT", "1000000")
                ),
                "anthropic_content_limit": int(
                    os.getenv("ANTHROPIC_CONTENT_LIMIT", "1000000")
                ),
                "content_filtering_enabled": os.getenv(
                    "CONTENT_FILTERING_ENABLED", "true"
                ).lower()
                == "true",
                "content_filtering_confidence": float(
                    os.getenv("CONTENT_FILTERING_CONFIDENCE", "0.7")
                ),
            },
        )
    except Exception as exc:
        logger.error("Article detail error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/pdf-upload")
async def pdf_upload_page():
    """PDF upload page."""
    return templates.TemplateResponse("pdf_upload.html", {"request": {}})


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    """Job monitoring page."""
    return templates.TemplateResponse(
        "jobs.html", {"request": request, "environment": ENVIRONMENT}
    )


@router.get("/ml-hunt-comparison", response_class=HTMLResponse)
async def ml_hunt_comparison_page(request: Request):
    """ML vs Hunt scoring comparison page."""
    return templates.TemplateResponse(
        "ml_hunt_comparison.html", {"request": request, "environment": ENVIRONMENT}
    )


@router.get("/observables-training", response_class=HTMLResponse)
async def observable_training_page(request: Request):
    """Observable extractor training dashboard."""
    return templates.TemplateResponse(
        "observable_training.html", {"request": request, "environment": ENVIRONMENT}
    )


@router.get("/sigma-ab-test", response_class=HTMLResponse)
async def sigma_ab_test_page(request: Request):
    """SIGMA rule A/B testing interface."""
    try:
        return templates.TemplateResponse("sigma_ab_test.html", {"request": request})
    except Exception as exc:
        logger.error("SIGMA A/B test page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )


@router.get("/sigma-similarity-test", response_class=HTMLResponse)
async def sigma_similarity_test_page(request: Request):
    """SIGMA rule cosine similarity testing interface."""
    try:
        return templates.TemplateResponse(
            "sigma_similarity_test.html", {"request": request}
        )
    except Exception as exc:
        logger.error("SIGMA similarity test page error: %s", exc)
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(exc)},
            status_code=500,
        )
