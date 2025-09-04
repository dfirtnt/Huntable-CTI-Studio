"""
Modern FastAPI Application for CTI Scraper

Uses async/await, PostgreSQL, and proper connection management.
"""

import os
import sys
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from sqlalchemy.ext.asyncio import AsyncSession

# Add src to path for imports
src_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(src_path))

from src.database.async_manager import async_db_manager
from src.models.source import Source, SourceUpdate, SourceFilter
from src.models.article import Article
from src.worker.celery_app import test_source_connectivity, collect_from_source
from src.utils.search_parser import parse_boolean_search, get_search_help_text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Templates
templates = Jinja2Templates(directory="src/web/templates")

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info("Starting CTI Scraper application...")
    
    # Create database tables
    try:
        await async_db_manager.create_tables()
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise
    
    # Health check
    try:
        stats = await async_db_manager.get_database_stats()
        logger.info(f"Database connection successful: {stats['total_sources']} sources, {stats['total_articles']} articles")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down CTI Scraper application...")
    await async_db_manager.close()
    logger.info("Application shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="CTI Scraper - Modern Threat Intelligence Platform",
    description="Enterprise-grade threat intelligence aggregation and analysis platform",
    version="2.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Static files
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

# Dependency for database session
async def get_db_session() -> AsyncSession:
    """Get database session for dependency injection."""
    async with async_db_manager.get_session() as session:
        yield session

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    try:
        stats = await async_db_manager.get_database_stats()
        return {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00Z",
            "database": {
                "status": "connected",
                "sources": stats["total_sources"],
                "articles": stats["total_articles"]
            },
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# Dashboard
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    try:
        stats = await async_db_manager.get_database_stats()
        sources = await async_db_manager.list_sources()
        recent_articles = await async_db_manager.list_articles(limit=5)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "stats": stats,
                "sources": sources,
                "recent_articles": recent_articles,
                "current_time": current_time
            }
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

# Settings page
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    try:
        return templates.TemplateResponse(
            "settings.html",
            {"request": request}
        )
    except Exception as e:
        logger.error(f"Settings page error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

# Sources management
@app.get("/sources", response_class=HTMLResponse)
async def sources_list(request: Request):
    """Sources management page."""
    try:
        sources = await async_db_manager.list_sources()
        quality_stats = await async_db_manager.get_source_quality_stats()
        
        # Debug logging
        logger.info(f"Quality stats returned: {len(quality_stats)} entries")
        for stat in quality_stats[:5]:  # Log first 5 entries
            logger.info(f"Source {stat['source_id']}: {stat['name']} - Rejection rate: {stat['rejection_rate']}%")
        
        # Create a lookup for quality stats by source ID
        quality_lookup = {stat["source_id"]: stat for stat in quality_stats}
        
        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request, 
                "sources": sources,
                "quality_stats": quality_lookup
            }
        )
    except Exception as e:
        logger.error(f"Sources list error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

@app.get("/api/sources")
async def api_sources_list(filter_params: SourceFilter = Depends()):
    """API endpoint for listing sources."""
    try:
        sources = await async_db_manager.list_sources(filter_params)
        return {"sources": [source.dict() for source in sources]}
    except Exception as e:
        logger.error(f"API sources list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sources/{source_id}")
async def api_get_source(source_id: int):
    """API endpoint for getting a specific source."""
    try:
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        return source.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API get source error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sources/{source_id}/toggle")
async def api_toggle_source_status(source_id: int):
    """Toggle source active status."""
    try:
        result = await async_db_manager.toggle_source_status(source_id)
        if not result:
            raise HTTPException(status_code=404, detail="Source not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API toggle source status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/sources/{source_id}/stats")
async def api_source_stats(source_id: int):
    """Get source statistics."""
    try:
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Get articles for this source to calculate real stats
        articles = await async_db_manager.list_articles_by_source(source_id)
        
        # Calculate statistics
        total_articles = len(articles)
        avg_content_length = sum(len(article.content or "") for article in articles) // max(total_articles, 1)
        
        # Mock quality score for now (in production, this would be calculated from actual quality data)
        avg_quality_score = 65  # Mock value
        
        # Mock articles by date for now
        articles_by_date = {"2024-01-01": total_articles} if total_articles > 0 else {}
        
        stats = {
            "source_id": source_id,
            "source_name": source.name,
            "active": getattr(source, 'active', True),
            "tier": getattr(source, 'tier', 1),
            "collection_method": "RSS" if source.rss_url else "Web Scraping",
            "total_articles": total_articles,
            "avg_content_length": avg_content_length,
            "avg_quality_score": avg_quality_score,
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "articles_by_date": articles_by_date
        }
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API source stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Articles management
@app.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request, 
    search: Optional[str] = None,
    source: Optional[str] = None,
    classification: Optional[str] = None,
    per_page: Optional[int] = 100,
    page: Optional[int] = 1
):
    """Articles listing page."""
    try:
        # Get all articles first for filtering
        all_articles = await async_db_manager.list_articles()
        sources = await async_db_manager.list_sources()
        
        # Create source lookup
        source_lookup = {source.id: source for source in sources}
        
        # Apply filters
        filtered_articles = all_articles
        
        # Search filter with boolean logic
        if search:
            # Convert articles to dict format for the search parser
            articles_dict = [
                {
                    'id': article.id,
                    'title': article.title,
                    'content': article.content,
                    'source_id': article.source_id,
                    'published_at': article.published_at,
                    'canonical_url': article.canonical_url,
                    'metadata': article.metadata
                }
                for article in filtered_articles
            ]
            
            # Apply boolean search filtering
            filtered_dicts = parse_boolean_search(search, articles_dict)
            
            # Convert back to article objects
            filtered_article_ids = {article['id'] for article in filtered_dicts}
            filtered_articles = [
                article for article in filtered_articles
                if article.id in filtered_article_ids
            ]
        
        # Source filter
        if source and source.isdigit():
            source_id = int(source)
            filtered_articles = [
                article for article in filtered_articles
                if article.source_id == source_id
            ]
        
        # Classification filter
        if classification and classification in ['chosen', 'rejected', 'unclassified']:
            if classification == 'unclassified':
                filtered_articles = [
                    article for article in filtered_articles
                    if not article.metadata or 
                    article.metadata.get('training_category') not in ['chosen', 'rejected']
                ]
            else:
                filtered_articles = [
                    article for article in filtered_articles
                    if article.metadata and 
                    article.metadata.get('training_category') == classification
                ]
        
        # Apply pagination
        total_articles = len(filtered_articles)
        per_page = max(1, min(per_page, 100))  # Limit to 100 per page
        total_pages = max(1, (total_articles + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, total_articles)
        
        # Get articles for current page
        articles = filtered_articles[start_idx:end_idx]
        
        pagination = {
            "total_articles": total_articles,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "start_idx": start_idx + 1,
            "end_idx": end_idx
        }
        
        # Create filters data
        filters = {
            "search": search or "",
            "source": source or "",
            "classification": classification or ""
        }
        
        # Get classification statistics from filtered articles
        chosen_count = sum(1 for article in filtered_articles 
                          if article.metadata and 
                          article.metadata.get('training_category') == 'chosen')
        rejected_count = sum(1 for article in filtered_articles 
                           if article.metadata and 
                           article.metadata.get('training_category') == 'rejected')
        unclassified_count = sum(1 for article in filtered_articles 
                               if not article.metadata or 
                               article.metadata.get('training_category') not in ['chosen', 'rejected'])
        
        stats = {
            "chosen_count": chosen_count,
            "rejected_count": rejected_count,
            "unclassified_count": unclassified_count
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
                "stats": stats
            }
        )
    except Exception as e:
        logger.error(f"Articles list error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

@app.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    """Article detail page."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Article not found"},
                status_code=404
            )
        
        source = await async_db_manager.get_source(article.source_id)
        
        # Simplified article detail without TTP analysis
        return templates.TemplateResponse(
            "article_detail.html",
            {
                "request": request, 
                "article": article, 
                "source": source
            }
        )
    except Exception as e:
        logger.error(f"Article detail error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

# Analysis page removed - no longer needed after quality scoring removal

@app.get("/api/articles")
async def api_articles_list(limit: Optional[int] = 100):
    """API endpoint for listing articles."""
    try:
        articles = await async_db_manager.list_articles(limit=limit)
        return {"articles": [article.dict() for article in articles]}
    except Exception as e:
        logger.error(f"API articles list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles/next-unclassified")
async def api_get_next_unclassified():
    """API endpoint for getting the next unclassified article."""
    try:
        # Get all articles ordered by ID to ensure consistent ordering
        articles = await async_db_manager.list_articles()
        
        # Sort by ID to ensure we get the lowest unclassified article ID
        articles.sort(key=lambda x: x.id)
        
        # Find the first unclassified article
        for article in articles:
            if not article.metadata or article.metadata.get('training_category') not in ['chosen', 'rejected']:
                return {"article_id": article.id}
        
        # If no unclassified articles found
        return {"article_id": None, "message": "No unclassified articles found"}
        
    except Exception as e:
        logger.error(f"API get next unclassified error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles/{article_id}")
async def api_get_article(article_id: int):
    """API endpoint for getting a specific article."""
    try:
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        return article.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API get article error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/classify")
async def api_classify_article(article_id: int, request: Request):
    """API endpoint for classifying an article."""
    try:
        # Get request body
        body = await request.json()
        category = body.get('category')
        reason = body.get('reason')
        
        if not category or category not in ['chosen', 'rejected', 'unclassified']:
            raise HTTPException(status_code=400, detail="Invalid category. Must be 'chosen', 'rejected', or 'unclassified'")
        
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Prepare metadata update
        from src.models.article import ArticleUpdate
        
        # Get current metadata or create new
        current_metadata = article.metadata.copy() if article.metadata else {}
        
        # Update metadata with classification
        current_metadata['training_category'] = category
        current_metadata['training_reason'] = reason
        current_metadata['training_categorized_at'] = datetime.now().isoformat()
        
        # Create update object
        update_data = ArticleUpdate(metadata=current_metadata)
        
        # Save the updated article
        updated_article = await async_db_manager.update_article(article_id, update_data)
        
        if not updated_article:
            raise HTTPException(status_code=500, detail="Failed to update article")
        
        return {
            "success": True,
            "article_id": article_id,
            "category": category,
            "reason": reason,
            "categorized_at": current_metadata['training_categorized_at']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API classify article error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors."""
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Page not found"},
        status_code=404
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: HTTPException):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {exc}")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Internal server error"},
        status_code=500
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.web.modern_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
