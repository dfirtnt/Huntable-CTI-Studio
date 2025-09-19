"""
Modern FastAPI Application for CTI Scraper

Uses async/await, PostgreSQL, and proper connection management.
"""

import os
import sys
import json
import asyncio
import logging
import httpx
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.sigma_validator import validate_sigma_rule

from src.database.async_manager import async_db_manager
from src.models.source import Source, SourceUpdate, SourceFilter
from src.models.article import Article, ArticleUpdate
from src.models.annotation import ArticleAnnotationCreate, ArticleAnnotationUpdate
from src.worker.celery_app import test_source_connectivity, collect_from_source
from src.utils.search_parser import parse_boolean_search, get_search_help_text
from src.utils.ioc_extractor import HybridIOCExtractor, IOCExtractionResult

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment from environment variable
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Templates
templates = Jinja2Templates(directory="src/web/templates")

# Custom Jinja2 filters
def highlight_keywords(content: str, metadata: Dict[str, Any]) -> str:
    """
    Highlight discriminator keywords in article content.
    
    Args:
        content: Article content text
        metadata: Article metadata containing keyword matches
        
    Returns:
        HTML content with highlighted keywords
    """
    if not content or not metadata:
        return content
    
    # Get all keyword matches
    all_keywords = []
    keyword_types = {
        'perfect_keyword_matches': ('perfect', 'bg-green-100 text-green-800 border-green-300'),
        'good_keyword_matches': ('good', 'bg-purple-100 text-purple-800 border-purple-300'),
        'lolbas_matches': ('lolbas', 'bg-blue-100 text-blue-800 border-blue-300'),
        'intelligence_matches': ('intelligence', 'bg-red-100 text-red-800 border-red-300'),
        'negative_matches': ('negative', 'bg-gray-100 text-gray-800 border-gray-300')
    }
    
    for key, (type_name, css_classes) in keyword_types.items():
        keywords = metadata.get(key, [])
        for keyword in keywords:
            all_keywords.append((keyword, type_name, css_classes))
    
    if not all_keywords:
        return content
    
    # Sort keywords by length (longest first) to avoid partial replacements
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)
    
    # Create highlighted content
    highlighted_content = content
    
    for keyword, type_name, css_classes in all_keywords:
        # Escape special regex characters in the keyword
        import re
        escaped_keyword = re.escape(keyword)
        
        # Create highlight span
        highlight_span = f'<span class="px-1 py-0.5 rounded text-xs font-medium border {css_classes}" title="{type_name.title()} discriminator: {keyword}">{keyword}</span>'
        
        # For certain keywords, allow partial matches (like "hunting" in "threat hunting")
        partial_match_keywords = ['hunting', 'detection', 'monitor', 'alert', 'executable', 'parent-child', 'defender query']
        
        # For wildcard keywords, use prefix matching
        wildcard_keywords = ['spawn']
        
        try:
            if keyword.lower() in partial_match_keywords:
                # Allow partial matches for these keywords
                pattern = re.compile(escaped_keyword, re.IGNORECASE)
            elif keyword.lower() in wildcard_keywords:
                # Allow wildcard matching (e.g., "spawn" matches "spawns", "spawning", "spawned")
                pattern = re.compile(escaped_keyword + r'\w*', re.IGNORECASE)
            else:
                # Use word boundaries for other keywords
                pattern = re.compile(r'\b' + escaped_keyword + r'\b', re.IGNORECASE)
            
            highlighted_content = pattern.sub(highlight_span, highlighted_content)
        except re.error as e:
            # If regex compilation fails, skip this keyword
            logger.warning(f"Regex error for keyword '{keyword}': {e}")
            continue
    
    return highlighted_content

# Register the filter
templates.env.filters["highlight_keywords"] = highlight_keywords

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
                "articles": stats["total_articles"]
            },
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

# Health check API endpoints
@app.get("/api/health")
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
                "articles": stats["total_articles"]
            },
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"API health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/database")
async def api_database_health() -> Dict[str, Any]:
    """Database health check with detailed statistics."""
    try:
        stats = await async_db_manager.get_database_stats()
        
        # Get deduplication stats
        dedup_stats = await async_db_manager.get_deduplication_stats()
        
        # Get performance metrics
        performance_metrics = await async_db_manager.get_performance_metrics()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "connection": "connected",
                "total_articles": stats["total_articles"],
                "total_sources": stats["total_sources"],
                "simhash": {
                    "coverage": f"{dedup_stats.get('simhash_coverage', 0)}%"
                },
                "deduplication": {
                    "total_articles": stats["total_articles"],
                    "unique_urls": dedup_stats.get("unique_urls", 0),
                    "duplicate_rate": f"{dedup_stats.get('duplicate_rate', 0)}%"
                },
                "performance": performance_metrics
            }
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/deduplication")
async def api_deduplication_health():
    """Deduplication system health check."""
    try:
        dedup_stats = await async_db_manager.get_deduplication_stats()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "deduplication": {
                "exact_duplicates": {
                    "content_hash_duplicates": dedup_stats.get("content_hash_duplicates", 0),
                    "duplicate_details": dedup_stats.get("duplicate_details", [])
                },
                "near_duplicates": {
                    "potential_near_duplicates": dedup_stats.get("near_duplicates", 0),
                    "simhash_coverage": f"{dedup_stats.get('simhash_coverage', 0)}%"
                },
                "simhash_buckets": {
                    "bucket_distribution": dedup_stats.get("bucket_distribution", []),
                    "most_active_bucket": dedup_stats.get("most_active_bucket")
                }
            }
        }
    except Exception as e:
        logger.error(f"Deduplication health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/services")
async def api_services_health():
    """External services health check."""
    try:
        services_status = {}
        
        # Check Redis
        try:
            import redis
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
            redis_client = redis.from_url(redis_url, decode_responses=True)
            redis_info = redis_client.info()
            services_status["redis"] = {
                "status": "healthy",
                "info": {
                    "used_memory": redis_info.get("used_memory", 0),
                    "connected_clients": redis_info.get("connected_clients", 0)
                }
            }
        except Exception as e:
            services_status["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check Ollama
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://ollama:11434/api/tags", timeout=5.0)
                if response.status_code == 200:
                    models_data = response.json()
                    services_status["ollama"] = {
                        "status": "healthy",
                        "models_available": len(models_data.get("models", [])),
                        "models": [model["name"] for model in models_data.get("models", [])]
                    }
                else:
                    services_status["ollama"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            services_status["ollama"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": services_status
        }
    except Exception as e:
        logger.error(f"Services health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/celery")
async def api_celery_health():
    """Celery workers health check."""
    try:
        celery_status = {}
        
        # Check Celery workers
        try:
            from src.worker.celery_app import celery_app
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            
            if active_workers:
                celery_status["workers"] = {
                    "status": "healthy",
                    "active_workers": len(active_workers)
                }
            else:
                celery_status["workers"] = {
                    "status": "unhealthy",
                    "error": "No active workers found"
                }
        except Exception as e:
            celery_status["workers"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check broker
        celery_status["broker"] = {
            "status": "healthy",
            "url": "redis://redis:6379/0"
        }
        
        # Check result backend
        celery_status["result_backend"] = {
            "status": "healthy",
            "backend": "redis://redis:6379/0"
        }
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "celery": celery_status
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/ingestion")
async def api_ingestion_health():
    """Ingestion analytics health check."""
    try:
        ingestion_stats = await async_db_manager.get_ingestion_analytics()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "ingestion": ingestion_stats
        }
    except Exception as e:
        logger.error(f"Ingestion health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

# Health Checks Page
@app.get("/health-checks", response_class=HTMLResponse)
async def health_checks_page(request: Request):
    """Health checks monitoring page."""
    return templates.TemplateResponse(
        "health_checks.html",
        {"request": request}
    )

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
                "current_time": current_time,
                "environment": ENVIRONMENT
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

# Health checks page
@app.get("/health-checks", response_class=HTMLResponse)
async def health_checks_page(request: Request):
    """Health checks monitoring page."""
    try:
        return templates.TemplateResponse(
            "health_checks.html",
            {
                "request": request,
                "environment": ENVIRONMENT
            }
        )
    except Exception as e:
        logger.error(f"Health checks page error: {e}")
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

@app.get("/database-chat", response_class=HTMLResponse)
async def database_chat_page(request: Request):
    """Database chat interface page."""
    try:
        return templates.TemplateResponse("database_chat.html", {
            "request": request
        })
    except Exception as e:
        logger.error(f"Database chat page error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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


@app.put("/api/sources/{source_id}/min_content_length")
async def api_update_source_min_content_length(source_id: int, request: dict):
    """Update source minimum content length."""
    try:
        min_content_length = request.get('min_content_length')
        
        if min_content_length is None:
            raise HTTPException(status_code=400, detail="min_content_length is required")
        
        if not isinstance(min_content_length, int) or min_content_length < 0:
            raise HTTPException(status_code=400, detail="min_content_length must be a non-negative integer")
        
        result = await async_db_manager.update_source_min_content_length(source_id, min_content_length)
        if not result:
            raise HTTPException(status_code=404, detail="Source not found")
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API update source min content length error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scrape-url")
async def api_scrape_url(request: dict):
    """Scrape a single URL manually."""
    try:
        url = request.get('url')
        title = request.get('title')
        force_scrape = request.get('force_scrape', False)
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Use httpx to fetch the URL content directly
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                html_content = response.text
            except httpx.RequestError as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")
        
        # Simple content extraction (basic implementation)
        import re
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        extracted_title = title
        if not extracted_title:
            title_tag = soup.find('title')
            if title_tag:
                extracted_title = title_tag.get_text().strip()
            else:
                extracted_title = "Untitled Article"
        
        # Extract main content
        content_selectors = ['article', 'main', '.content', '.post-content', '.article-content', 'body']
        content_text = ""
        
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                content_text = element.get_text(separator=' ', strip=True)
                if len(content_text) > 200:  # Minimum content length
                    break
        
        if not content_text or len(content_text) < 200:
            content_text = soup.get_text(separator=' ', strip=True)
        
        # Get or create a "Manual" source for adhoc scraping
        from src.models.source import SourceFilter
        manual_sources = await async_db_manager.list_sources(SourceFilter(identifier_contains="manual"))
        manual_source = None
        
        # Find exact match for "manual" identifier
        for source in manual_sources:
            if source.identifier == "manual":
                manual_source = source
                break
        
        if not manual_source:
            # Create manual source if it doesn't exist
            from src.models.source import SourceCreate, SourceConfig
            manual_source_data = SourceCreate(
                identifier="manual",
                name="Manual",
                url="https://manual.example.com",  # Provide a valid URL
                rss_url="",
                check_frequency=3600,  # 1 hour
                lookback_days=90,  # 90 days
                active=True,
                config=SourceConfig()  # Use proper SourceConfig object
            )
            manual_source = await async_db_manager.create_source(manual_source_data)
            
            # If creation failed (e.g., duplicate), try to get existing source
            if not manual_source:
                manual_sources = await async_db_manager.list_sources(SourceFilter(identifier_contains="manual"))
                for source in manual_sources:
                    if source.identifier == "manual":
                        manual_source = source
                        break
        
        # Check for existing article if not forcing
        if not force_scrape:
            existing_article = await async_db_manager.get_article_by_url(url)
            if existing_article:
                return {
                    "success": False,
                    "error": "Article already exists",
                    "article_id": existing_article.id,
                    "article_title": existing_article.title
                }
        
        # Create article using ContentProcessor for proper scoring
        from src.models.article import ArticleCreate
        from src.core.processor import ContentProcessor
        from datetime import datetime
        import hashlib
        
        # Create ArticleCreate object
        article_data = ArticleCreate(
            source_id=manual_source.id,
            canonical_url=url,
            title=extracted_title,
            published_at=datetime.utcnow(),
            content=content_text,
            metadata={"source_name": "Manual", "manual_scrape": True}
        )
        
        # Apply threat hunting scoring directly
        from src.utils.content import ThreatHuntingScorer
        
        # Calculate threat hunting score and keyword matches
        threat_hunting_result = ThreatHuntingScorer.score_threat_hunting_content(
            article_data.title, article_data.content
        )
        
        # Update article metadata with threat hunting results
        article_data.metadata.update(threat_hunting_result)
        
        # Add basic quality metrics
        article_data.metadata.update({
            'word_count': len(content_text.split()),
            'quality_score': 50.0,  # Default quality score for manual articles
            'processing_status': 'completed',
            'manual_scrape': True
        })
        
        processed_article = article_data
        
        # Save processed article to database
        try:
            await async_db_manager.create_article(processed_article)
            
            # Get the created article to return its ID
            created_article = await async_db_manager.get_article_by_url(url)
            
            logger.info(f"Successfully scraped and processed manual URL: {url} -> Article ID: {created_article.id}")
            
            return {
                "success": True,
                "article_id": created_article.id,
                "article_title": created_article.title,
                "message": "Article scraped and processed successfully with threat hunting scoring"
            }
        except Exception as e:
            logger.error(f"Error saving processed manual article: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save article: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API scrape URL error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-route")
async def test_route():
    """Test route to verify route registration."""
    return {"message": "Test route is working"}


@app.put("/api/sources/{source_id}/lookback")
async def api_update_source_lookback(source_id: int, request: dict):
    """Update source lookback window."""
    try:
        lookback_days = request.get('lookback_days')
        
        if not lookback_days or not isinstance(lookback_days, int):
            raise HTTPException(status_code=400, detail="lookback_days must be a valid integer")
        
        if lookback_days < 1 or lookback_days > 365:
            raise HTTPException(status_code=400, detail="lookback_days must be between 1 and 365")
        
        # Get the source to verify it exists
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Update the source
        from src.models.source import SourceUpdate
        update_data = SourceUpdate(lookback_days=lookback_days)
        
        updated_source = await async_db_manager.update_source(source_id, update_data)
        if not updated_source:
            raise HTTPException(status_code=500, detail="Failed to update source")
        
        logger.info(f"Updated lookback window for source {source_id} to {lookback_days} days")
        
        return {
            "success": True, 
            "message": f"Lookback window updated to {lookback_days} days",
            "lookback_days": lookback_days
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update source lookback window: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/sources/{source_id}/check_frequency")
async def api_update_source_check_frequency(source_id: int, request: dict):
    """Update source check frequency."""
    try:
        check_frequency = request.get('check_frequency')
        
        if not check_frequency or not isinstance(check_frequency, int):
            raise HTTPException(status_code=400, detail="check_frequency must be a valid integer")
        
        if check_frequency < 60:
            raise HTTPException(status_code=400, detail="check_frequency must be at least 60 seconds")
        
        # Get the source to verify it exists
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Update the source directly using raw SQL since SourceUpdate model doesn't exist
        from sqlalchemy import update
        from src.database.models import SourceTable
        from datetime import datetime
        
        async with async_db_manager.get_session() as session:
            result = await session.execute(
                update(SourceTable)
                .where(SourceTable.id == source_id)
                .values(check_frequency=check_frequency, updated_at=datetime.now())
            )
            await session.commit()
            
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Source not found")
        
        logger.info(f"Updated check frequency for source {source_id} to {check_frequency} seconds")
        
        return {
            "success": True, 
            "message": f"Check frequency updated to {check_frequency} seconds ({check_frequency//60} minutes)",
            "check_frequency": check_frequency
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update source check frequency: {e}")
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
        
        # Calculate actual average threat hunting score
        threat_hunting_scores = []
        for article in articles:
            if article.metadata:
                score = article.metadata.get('threat_hunting_score', 0)
                if score > 0:
                    threat_hunting_scores.append(score)
        
        avg_threat_hunting_score = sum(threat_hunting_scores) / len(threat_hunting_scores) if threat_hunting_scores else 0.0
        
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
            "avg_threat_hunting_score": round(avg_threat_hunting_score, 1),
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "articles_by_date": articles_by_date
        }
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API source stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Search API endpoint
@app.get("/api/articles/search")
async def api_search_articles(
    q: str,
    source_id: Optional[int] = None,
    classification: Optional[str] = None,
    threat_hunting_min: Optional[int] = None,
    limit: Optional[int] = 100,
    offset: Optional[int] = 0
):
    """Search articles with wildcard and boolean support."""
    try:
        # Get all articles first
        all_articles = await async_db_manager.list_articles()
        
        # Apply basic filters
        filtered_articles = all_articles
        
        if source_id:
            filtered_articles = [a for a in filtered_articles if a.source_id == source_id]
        
        if classification:
            filtered_articles = [a for a in filtered_articles 
                               if a.metadata and a.metadata.get('training_category') == classification]
        
        if threat_hunting_min is not None:
            filtered_articles = [a for a in filtered_articles 
                               if a.metadata and a.metadata.get('threat_hunting_score', 0) >= threat_hunting_min]
        
        # Convert to dict format for search parser
        articles_dict = [
            {
                'id': article.id,
                'title': article.title,
                'content': article.content,
                'source_id': article.source_id,
                'published_at': article.published_at.isoformat() if article.published_at else None,
                'canonical_url': article.canonical_url,
                'metadata': article.metadata
            }
            for article in filtered_articles
        ]
        
        # Apply search with wildcard support
        search_results = parse_boolean_search(q, articles_dict)
        
        # Apply pagination
        total_results = len(search_results)
        paginated_results = search_results[offset:offset + limit]
        
        return {
            "query": q,
            "total_results": total_results,
            "articles": paginated_results,
            "pagination": {
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total_results
            }
        }
        
    except Exception as e:
        logger.error(f"Search API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/help")
async def api_search_help():
    """Get search syntax help."""
    return {"help_text": get_search_help_text()}

# Articles management
@app.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request, 
    search: Optional[str] = None,
    source: Optional[str] = None,
    source_id: Optional[int] = None,
    classification: Optional[str] = None,
    threat_hunting_range: Optional[str] = None,
    per_page: Optional[int] = 100,
    page: Optional[int] = 1,
    sort_by: str = "threat_hunting_score",
    sort_order: str = "desc",
    title_only: Optional[bool] = False
):
    """Articles listing page with sorting and filtering."""
    try:
        from src.models.article import ArticleFilter
        
        # Get all articles first to calculate total count
        all_articles_unfiltered = await async_db_manager.list_articles()
        sources = await async_db_manager.list_sources()
        
        # Create source lookup
        source_lookup = {source.id: source for source in sources}
        
        # Apply additional filters (search, source, classification, etc.)
        filtered_articles = all_articles_unfiltered
        
        # Search filter with boolean logic
        if search:
            if title_only:
                # Title-only search using simple filtering
                filtered_articles = [
                    article for article in filtered_articles
                    if search.lower() in article.title.lower()
                ]
            else:
                # Full search with boolean logic
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
        if source_id:
            filtered_articles = [
                article for article in filtered_articles
                if article.source_id == source_id
            ]
        elif source and source.isdigit():
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
        
        # Threat Hunting Score filter
        if threat_hunting_range:
            try:
                # Parse range like "60-79" or "40-100"
                if '-' in threat_hunting_range:
                    min_score, max_score = map(float, threat_hunting_range.split('-'))
                    filtered_articles = [
                        article for article in filtered_articles
                        if article.metadata and 
                        min_score <= article.metadata.get('threat_hunting_score', 0) <= max_score
                    ]
            except (ValueError, TypeError):
                # If parsing fails, ignore the filter
                pass
        
        # Apply sorting after filtering
        if sort_by == "threat_hunting_score":
            # Special handling for threat_hunting_score which is stored in metadata
            filtered_articles.sort(
                key=lambda x: float(x.metadata.get('threat_hunting_score', 0)) if x.metadata and x.metadata.get('threat_hunting_score') else 0,
                reverse=(sort_order == 'desc')
            )
        elif sort_by == "annotation_count":
            # Special handling for annotation_count which is stored in metadata
            filtered_articles.sort(
                key=lambda x: int(x.metadata.get('annotation_count', 0)) if x.metadata and x.metadata.get('annotation_count') is not None else 0,
                reverse=(sort_order == 'desc')
            )
        elif sort_by == "word_count":
            # Special handling for word_count field
            filtered_articles.sort(
                key=lambda x: x.word_count or 0,
                reverse=(sort_order == 'desc')
            )
        else:
            # Get the attribute dynamically
            sort_attr = getattr(filtered_articles[0], sort_by, None) if filtered_articles else None
            if sort_attr is not None:
                filtered_articles.sort(
                    key=lambda x: getattr(x, sort_by, ''),
                    reverse=(sort_order == 'desc')
                )
        
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
            "source_id": source_id,
            "classification": classification or "",
            "threat_hunting_range": threat_hunting_range or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
            "title_only": title_only
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
async def api_articles_list(
    limit: Optional[int] = 100,
    sort_by: str = "threat_hunting_score",
    sort_order: str = "desc",
    source_id: Optional[int] = None,
    processing_status: Optional[str] = None
):
    """API endpoint for listing articles with sorting and filtering."""
    try:
        from src.models.article import ArticleFilter
        
        # Create filter object
        article_filter = ArticleFilter(
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            source_id=source_id,
            processing_status=processing_status
        )
        
        articles = await async_db_manager.list_articles(article_filter=article_filter)
        
        # Get total count without limit for accurate pagination
        total_count = await async_db_manager.get_articles_count(
            source_id=source_id,
            processing_status=processing_status
        )
        
        return {
            "articles": [article.dict() for article in articles],
            "total": total_count,
            "sort_by": sort_by,
            "sort_order": sort_order
        }
    except Exception as e:
        logger.error(f"API articles list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles/next-unclassified")
async def api_get_next_unclassified(current_article_id: Optional[int] = None):
    """API endpoint for getting the next unclassified article."""
    try:
        # Get all articles ordered by ID to ensure consistent ordering
        articles = await async_db_manager.list_articles()
        
        # Sort by ID to ensure we get the next unclassified article ID
        articles.sort(key=lambda x: x.id)
        
        # If no current article ID provided, return the first unclassified
        if not current_article_id:
            for article in articles:
                if not article.metadata or article.metadata.get('training_category') not in ['chosen', 'rejected']:
                    return {"article_id": article.id}
        else:
            # Find the next unclassified article after the current one
            found_current = False
            for article in articles:
                if article.id == current_article_id:
                    found_current = True
                    continue
                
                if found_current and (not article.metadata or article.metadata.get('training_category') not in ['chosen', 'rejected']):
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

@app.post("/api/articles/bulk-action")
async def api_bulk_action(request: Request):
    """API endpoint for performing bulk actions on multiple articles."""
    try:
        body = await request.json()
        action = body.get('action')
        article_ids = body.get('article_ids', [])
        
        if not action:
            raise HTTPException(status_code=400, detail="Action is required")
        
        if not article_ids:
            raise HTTPException(status_code=400, detail="Article IDs are required")
        
        if action not in ['chosen', 'rejected', 'unclassified', 'delete']:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        processed_count = 0
        errors = []
        
        for article_id in article_ids:
            try:
                if action == 'delete':
                    # Delete the article
                    await async_db_manager.delete_article(article_id)
                    processed_count += 1
                else:
                    # Update classification
                    article = await async_db_manager.get_article(article_id)
                    if not article:
                        errors.append(f"Article {article_id} not found")
                        continue
                    
                    # Prepare metadata update
                    from src.models.article import ArticleUpdate
                    
                    # Get current metadata or create new
                    current_metadata = article.metadata.copy() if article.metadata else {}
                    
                    # Update metadata with classification
                    current_metadata['training_category'] = action
                    current_metadata['training_categorized_at'] = datetime.now().isoformat()
                    
                    # Create update object
                    update_data = ArticleUpdate(metadata=current_metadata)
                    
                    # Save the updated article
                    await async_db_manager.update_article(article_id, update_data)
                    processed_count += 1
                    
            except Exception as e:
                errors.append(f"Article {article_id}: {str(e)}")
                logger.error(f"Bulk action error for article {article_id}: {e}")
        
        return {
            "success": True,
            "processed_count": processed_count,
            "total_requested": len(article_ids),
            "errors": errors
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API bulk action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/analyze-threat-hunting")
async def api_analyze_threat_hunting(article_id: int, request: Request):
    """API endpoint for analyzing an article with CustomGPT for threat hunting and detection engineering."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body to determine what to analyze
        body = await request.json()
        analyze_content = body.get('analyze_content', False)  # Default to URL only
        
        # Prepare the analysis prompt
        if analyze_content:
            # Smart content truncation based on model
            if customgpt_api_url and customgpt_api_key:
                # Using ChatGPT - can handle more content
                content_limit = int(os.getenv('CHATGPT_CONTENT_LIMIT', '15000'))
            else:
                # Using Ollama - more conservative limit
                content_limit = int(os.getenv('OLLAMA_CONTENT_LIMIT', '4000'))
            
            # Truncate content intelligently
            content = article.content[:content_limit]
            if len(article.content) > content_limit:
                content += f"\n\n[Content truncated at {content_limit:,} characters. Full article has {len(article.content):,} characters.]"
            
            # Analyze both URL and content
            prompt = f"""As a cybersecurity expert specializing in threat hunting and detection engineering, analyze this threat intelligence article for its usefulness to security professionals.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}

Article Content:
{content}

Please provide a comprehensive analysis covering:

1. **Threat Hunting Value** (1-10 scale):
   - How useful is this for threat hunters?
   - What indicators of compromise (IOCs) are mentioned?
   - What attack techniques are described?

2. **Detection Engineering Value** (1-10 scale):
   - How useful is this for creating detection rules?
   - What detection opportunities are present?
   - What log sources would be relevant?

3. **Key Technical Details**:
   - Specific malware families, tools, or techniques
   - Network indicators, file hashes, registry keys
   - Process names, command lines, or behaviors

4. **Actionable Intelligence**:
   - Specific detection rules that could be created
   - Threat hunting queries that could be used
   - Recommended monitoring areas

5. **Overall Assessment**:
   - Summary of the article's value
   - Priority level for security teams
   - Recommended next steps

Please be specific and actionable in your analysis."""
        else:
            # Analyze URL and metadata only
            prompt = f"""As a cybersecurity expert specializing in threat hunting and detection engineering, analyze this threat intelligence article for its potential usefulness to security professionals.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}
Source: {article.source_id}
Content Length: {len(article.content)} characters

Based on the title, source, and metadata, please provide an initial assessment:

1. **Potential Threat Hunting Value** (1-10 scale):
   - How promising does this article look for threat hunters?
   - What types of threats might be discussed?

2. **Potential Detection Engineering Value** (1-10 scale):
   - How promising does this look for detection rule creation?
   - What detection opportunities might be present?

3. **Source Credibility**:
   - How reliable is this source typically?
   - What is the source's reputation in the security community?

4. **Recommended Next Steps**:
   - Should the full content be analyzed?
   - What specific aspects should be focused on?

Please provide a brief but insightful analysis based on the available metadata."""
        
        # Get CustomGPT configuration from environment
        customgpt_api_url = os.getenv('CUSTOMGPT_API_URL')
        customgpt_api_key = os.getenv('CUSTOMGPT_API_KEY')
        
        if not customgpt_api_url or not customgpt_api_key:
            # Fallback to Ollama if CustomGPT not configured
            ollama_url = os.getenv('LLM_API_URL', 'http://cti_ollama:11434')
            ollama_model = os.getenv('LLM_MODEL', 'mistral')
            
            logger.info(f"Using Ollama at {ollama_url} with model {ollama_model}")
            
            # Use Ollama API
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        f"{ollama_url}/api/generate",
                        json={
                            "model": ollama_model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2048
                            }
                        },
                        timeout=180.0
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Ollama API error: {response.status_code} - {response.text}")
                        raise HTTPException(status_code=500, detail=f"Failed to get analysis from Ollama: {response.status_code}")
                    
                    result = response.json()
                    analysis = result.get('response', 'No analysis available')
                    logger.info(f"Successfully got analysis from Ollama: {len(analysis)} characters")
                    
                except Exception as e:
                    logger.error(f"Ollama API request failed: {e}")
                    logger.error(f"Exception type: {type(e)}")
                    logger.error(f"Exception args: {e.args}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    raise HTTPException(status_code=500, detail=f"Failed to get analysis from Ollama: {str(e)}")
                
        else:
            # Use CustomGPT API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{customgpt_api_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {customgpt_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4",  # or your specific CustomGPT model
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a cybersecurity expert specializing in threat hunting and detection engineering. Provide clear, actionable analysis of threat intelligence articles."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "max_tokens": 2048,
                        "temperature": 0.3
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to get analysis from CustomGPT")
                
                result = response.json()
                analysis = result['choices'][0]['message']['content']
        
        # Store the analysis in article metadata
        current_metadata = article.metadata.copy() if article.metadata else {}
        current_metadata['threat_hunting_analysis'] = {
            'analysis': analysis,
            'analyzed_at': datetime.now().isoformat(),
            'analyzed_content': analyze_content,
            'model_used': 'customgpt' if customgpt_api_url else 'ollama',
            'model_name': 'gpt-4' if customgpt_api_url else ollama_model
        }
        
        # Update the article
        update_data = ArticleUpdate(metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "analyzed_at": current_metadata['threat_hunting_analysis']['analyzed_at'],
            "analyzed_content": analyze_content,
            "model_used": current_metadata['threat_hunting_analysis']['model_used'],
            "model_name": current_metadata['threat_hunting_analysis']['model_name']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API analyze threat hunting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/chatgpt-summary")
async def api_chatgpt_summary(article_id: int, request: Request):
    """API endpoint for generating a ChatGPT summary of an article."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body to determine what to summarize and API key
        body = await request.json()
        include_content = body.get('include_content', True)  # Default to full content
        api_key = body.get('api_key')  # Get API key from request
        force_regenerate = body.get('force_regenerate', False)  # Force regeneration
        
        logger.info(f"ChatGPT summary request for article {article_id}, api_key provided: {bool(api_key)}, force_regenerate: {force_regenerate}")
        
        # If force regeneration is requested, skip cache check
        if not force_regenerate:
            # Check if summary already exists and return cached version
            existing_summary = article.metadata.get('chatgpt_summary', {}) if article.metadata else {}
            if existing_summary and existing_summary.get('summary'):
                logger.info(f"Returning cached ChatGPT summary for article {article_id}")
                return {
                    "success": True,
                    "article_id": article_id,
                    "summary": existing_summary['summary'],
                    "summarized_at": existing_summary['summarized_at'],
                    "content_type": existing_summary['content_type'],
                    "model_used": existing_summary['model_used'],
                    "model_name": existing_summary['model_name'],
                    "cached": True
                }
        
        # Check if API key is provided
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the summary prompt
        if include_content:
            # Smart content truncation based on model
            # Using ChatGPT - can handle more content
            # GPT-4 Turbo: ~50k chars, GPT-4: ~20k chars, GPT-3.5: ~15k chars
            content_limit = int(os.getenv('CHATGPT_CONTENT_LIMIT', '20000'))
            
            # Truncate content intelligently
            content = article.content[:content_limit]
            if len(article.content) > content_limit:
                content += f"\n\n[Content truncated at {content_limit:,} characters. Full article has {len(article.content):,} characters.]"
            
            # Summarize both URL and content
            prompt = f"""Please provide a comprehensive summary of this threat intelligence article.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}

Article Content:
{content}

Please provide a summary that includes:

1. **Key Points**: Main findings and important details
2. **Threat Actors**: Any mentioned threat actors or groups
3. **Techniques**: Attack techniques, tools, or methods described
4. **Indicators**: Any IOCs, hashes, IPs, or domains mentioned
5. **Impact**: Potential impact or severity of the threat
6. **Recommendations**: Any suggested mitigations or actions

Please be concise but comprehensive, focusing on actionable intelligence."""
        else:
            # Summarize URL and metadata only
            prompt = f"""Please provide a brief summary of this threat intelligence article based on its metadata.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}
Source: {article.source_id}
Content Length: {len(article.content)} characters

Based on the title, source, and metadata, please provide a brief assessment of what this article likely covers and its potential importance for security professionals."""
        
        # Use ChatGPT API with provided key
        chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
        
        # Use ChatGPT API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                chatgpt_api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4",  # or your specific ChatGPT model
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a cybersecurity expert specializing in threat intelligence analysis. Provide clear, concise summaries of threat intelligence articles."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = f"Failed to get summary from ChatGPT: {response.status_code}"
                if response.status_code == 401:
                    error_detail = "Invalid API key. Please check your OpenAI API key in Settings."
                elif response.status_code == 429:
                    error_detail = "Rate limit exceeded. Please try again later."
                raise HTTPException(status_code=500, detail=error_detail)
            
            result = response.json()
            summary = result['choices'][0]['message']['content']
        
        # Store the summary in article metadata
        current_metadata = article.metadata.copy() if article.metadata else {}
        current_metadata['chatgpt_summary'] = {
            'summary': summary,
            'summarized_at': datetime.now().isoformat(),
            'content_type': 'full content' if include_content else 'metadata only',
            'model_used': 'chatgpt',
            'model_name': 'gpt-4'
        }
        
        # Update the article
        update_data = ArticleUpdate(metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "summary": summary,
            "summarized_at": current_metadata['chatgpt_summary']['summarized_at'],
            "content_type": current_metadata['chatgpt_summary']['content_type'],
            "model_used": current_metadata['chatgpt_summary']['model_used'],
            "model_name": current_metadata['chatgpt_summary']['model_name']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API ChatGPT summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/custom-prompt")
async def api_custom_prompt(article_id: int, request: Request):
    """API endpoint for custom AI prompts about an article."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        custom_prompt = body.get('prompt')
        api_key = body.get('api_key')
        
        if not custom_prompt:
            raise HTTPException(status_code=400, detail="Custom prompt is required")
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required")
        
        # Smart content truncation based on model
        # Using ChatGPT - can handle more content
        content_limit = int(os.getenv('CHATGPT_CONTENT_LIMIT', '15000'))
        
        # Truncate content intelligently
        content = article.content[:content_limit]
        if len(article.content) > content_limit:
            content += f"\n\n[Content truncated at {content_limit:,} characters. Full article has {len(article.content):,} characters.]"
        
        # Prepare the custom prompt
        full_prompt = f"""As a cybersecurity expert, please answer the following question about this threat intelligence article.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}

Article Content:
{content}

User Question: {custom_prompt}

Please provide a comprehensive and helpful response based on the article content. Be specific, actionable, and focus on cybersecurity insights."""
        
        # Use ChatGPT API
        chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                chatgpt_api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a cybersecurity expert specializing in threat intelligence analysis. Provide clear, helpful responses to questions about threat intelligence articles."
                        },
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = f"Failed to get response from ChatGPT: {response.status_code}"
                if response.status_code == 401:
                    error_detail = "Invalid API key. Please check your OpenAI API key in Settings."
                elif response.status_code == 429:
                    error_detail = "Rate limit exceeded. Please try again later."
                raise HTTPException(status_code=500, detail=error_detail)
            
            result = response.json()
            ai_response = result['choices'][0]['message']['content']
        
        # Store the custom prompt response in article metadata
        current_metadata = article.metadata.copy() if article.metadata else {}
        if 'custom_prompts' not in current_metadata:
            current_metadata['custom_prompts'] = []
        
        current_metadata['custom_prompts'].append({
            'prompt': custom_prompt,
            'response': ai_response,
            'responded_at': datetime.now().isoformat(),
            'model_used': 'chatgpt',
            'model_name': 'gpt-4'
        })
        
        # Update the article
        update_data = ArticleUpdate(metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "response": ai_response,
            "responded_at": current_metadata['custom_prompts'][-1]['responded_at'],
            "model_used": "chatgpt",
            "model_name": "gpt-4"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API custom prompt error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test-chatgpt-summary")
async def test_chatgpt_summary(request: Request):
    """Test ChatGPT summary functionality with provided API key."""
    try:
        body = await request.json()
        api_key = body.get('api_key')
        test_prompt = body.get('test_prompt', 'Please provide a brief summary of cybersecurity threats.')
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        
        # Use ChatGPT API with provided key
        chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                chatgpt_api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a cybersecurity expert. Provide brief, helpful responses."
                        },
                        {
                            "role": "user",
                            "content": test_prompt
                        }
                    ],
                    "max_tokens": 100,
                    "temperature": 0.3
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result['choices'][0]['message']['content']
                return {
                    "success": True, 
                    "message": "ChatGPT Summary is working",
                    "model_name": "gpt-4",
                    "test_summary": summary
                }
            elif response.status_code == 401:
                raise HTTPException(status_code=400, detail="Invalid API key")
            else:
                raise HTTPException(status_code=400, detail=f"API error: {response.status_code}")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test ChatGPT summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to test ChatGPT summary")

@app.post("/api/test-openai-key")
async def test_openai_key(request: Request):
    """Test OpenAI API key validity."""
    try:
        body = await request.json()
        api_key = body.get('api_key')
        
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")
        
        # Test the API key by making a simple request to OpenAI
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                return {"success": True, "message": "API key is valid"}
            elif response.status_code == 401:
                raise HTTPException(status_code=400, detail="Invalid API key")
            else:
                raise HTTPException(status_code=400, detail=f"API error: {response.status_code}")
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test OpenAI API key error: {e}")
        raise HTTPException(status_code=500, detail="Failed to test API key")

@app.post("/api/articles/{article_id}/generate-sigma")
async def api_generate_sigma(article_id: int, request: Request):
    """API endpoint for generating SIGMA detection rules from an article."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Check if article is marked as "chosen" (required for SIGMA generation)
        training_category = article.metadata.get('training_category', '') if article.metadata else ''
        logger.info(f"SIGMA generation request for article {article_id}, training_category: '{training_category}'")
        if training_category != 'chosen':
            raise HTTPException(status_code=400, detail="SIGMA rules can only be generated for articles marked as 'Chosen'. Please classify this article first.")
        
        # Check if SIGMA rules already exist and return cached version
        existing_sigma_rules = article.metadata.get('sigma_rules', {}) if article.metadata else {}
        if existing_sigma_rules and existing_sigma_rules.get('rules'):
            logger.info(f"Returning cached SIGMA rules for article {article_id}")
            return {
                "success": True,
                "article_id": article_id,
                "sigma_rules": existing_sigma_rules['rules'],
                "generated_at": existing_sigma_rules['generated_at'],
                "content_type": existing_sigma_rules['content_type'],
                "model_used": existing_sigma_rules['model_used'],
                "model_name": existing_sigma_rules['model_name'],
                "cached": True
            }
        
        # Get request body
        body = await request.json()
        include_content = body.get('include_content', True)  # Default to full content
        api_key = body.get('api_key')  # Get API key from request
        author_name = body.get('author_name', 'CTIScraper User')  # Get author name from request
        
        logger.info(f"SIGMA generation request for article {article_id}, api_key provided: {bool(api_key)}, author: {author_name}")
        
        if not api_key:
            logger.warning(f"SIGMA generation failed: No API key provided for article {article_id}")
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the SIGMA generation prompt
        if include_content:
            # Smart content truncation for SIGMA generation - much more conservative
            content_limit = int(os.getenv('CHATGPT_CONTENT_LIMIT', '8000'))  # Reduced from 20000
            
            # Truncate content intelligently
            content = article.content[:content_limit]
            if len(article.content) > content_limit:
                content += f"\n\n[Content truncated at {content_limit:,} characters. Full article has {len(article.content):,} characters.]"
            
            # Enhanced SIGMA-specific prompt based on SigmaHQ best practices - simplified
            prompt = f"""Generate a Sigma detection rule based on this threat intelligence:

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}

Content:
{content}

Create one high-quality Sigma rule in YAML format with:
- title: under 50 chars, title case
- id: valid UUID v4
- status: experimental
- description: what it detects
- author: {author_name}
- date: YYYY/MM/DD
- tags: relevant MITRE ATT&CK tags
- logsource: product and category
- detection: selection and condition
- fields: relevant fields
- falsepositives: potential false positives
- level: high/medium/low

CRITICAL SIGMA SYNTAX REQUIREMENTS:
- Use ONLY valid SIGMA condition syntax: 'selection' or 'selection1 and selection2' or 'selection1 or selection2'
- NEVER use SQL-like syntax like 'count()', 'group by', 'where', 'stats', etc.
- NEVER use aggregation functions in conditions
- Valid conditions: 'selection', 'selection and selection', 'selection or selection', 'all of selection*', '1 of selection*'
- Selection must reference defined filters above it
- Use proper YAML indentation and syntax

EXAMPLE VALID SIGMA STRUCTURE:
title: Process Creation Event
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    EventID: 4688
    CommandLine|contains: 'powershell'
  condition: selection

IMPORTANT: Output ONLY clean YAML without markdown formatting. Do not wrap the rule in ```yaml code blocks.

IMPORTANT: Focus on TTPs (Tactics, Techniques, and Procedures) rather than atomic IOCs (Indicators of Compromise). Avoid rules that could easily be replaced by simple IOC matching (specific IP addresses, file hashes, etc.). Instead, focus on:

- Behavioral patterns and techniques
- Process execution chains
- Network communication patterns
- File system activities
- Registry modifications
- Authentication anomalies
- Command execution patterns
- Persistence mechanisms
- Domain/URL patterns (when they indicate technique, not just specific domains)

The rule should detect the technique or behavior, not just specific artifacts. Domain/URL patterns are acceptable when they represent a technique (e.g., specific TLDs, URL structures, or domain patterns that indicate malicious behavior).

CRITICAL: Generate ONLY clean YAML output without any markdown formatting, code blocks, or additional text. The output must be valid YAML that can be directly parsed."""
        else:
            # Metadata-only prompt
            prompt = f"""As a senior cybersecurity detection engineer specializing in SIGMA rule creation and threat hunting, analyze this threat intelligence article metadata and provide guidance for SIGMA rule generation.

Article Title: {article.title}
Source URL: {article.canonical_url or 'N/A'}
Published Date: {article.published_at or 'N/A'}
Source: {article.source_id}
Content Length: {len(article.content)} characters

Based on the article title and metadata, provide:

1. **Potential Detection Opportunities**:
   - What types of threats might be discussed?
   - What detection categories would be most relevant?
   - What log sources should be considered?

2. **Recommended SIGMA Rule Types**:
   - Process creation rules
   - Network activity rules
   - File system rules
   - Registry rules
   - Authentication rules

3. **MITRE ATT&CK Techniques**:
   - Likely techniques based on the title
   - Recommended technique mappings

4. **Next Steps**:
   - Should the full content be analyzed?
   - What specific aspects should be focused on?

Please provide a brief but insightful analysis based on the available metadata."""
        
        # Use ChatGPT API with iterative fixing (up to 3 attempts)
        chatgpt_api_url = os.getenv('CHATGPT_API_URL', 'https://api.openai.com/v1/chat/completions')
        
        logger.info(f"Sending SIGMA request to OpenAI for article {article_id}, content length: {len(content) if include_content else 'metadata only'}")
        
        # Enhanced system prompt with compliance requirements
        system_prompt = """You are a senior cybersecurity detection engineer specializing in SIGMA rule creation and threat hunting. Generate high-quality, actionable SIGMA rules based on threat intelligence articles. Always use proper SIGMA syntax and include all required fields according to SigmaHQ standards. Focus on TTPs (Tactics, Techniques, and Procedures) rather than atomic IOCs (Indicators of Compromise). Create rules that detect behavioral patterns and techniques, not just specific artifacts like IP addresses or file hashes. Domain/URL patterns are acceptable when they represent techniques or behavioral patterns.

CRITICAL COMPLIANCE REQUIREMENTS:
- Use ONLY valid SIGMA condition syntax. NEVER use SQL-like syntax (count(), group by, where, stats, etc.) or aggregation functions in conditions
- Valid conditions are: 'selection', 'selection1 and selection2', 'selection1 or selection2', 'all of selection*', '1 of selection*'
- Always reference defined selections above the condition
- Output ONLY clean YAML without markdown formatting, code blocks, or additional text
- The output must be valid YAML that can be directly parsed by pySIGMA
- Ensure all required fields are present: title, logsource, detection
- Use proper YAML indentation and syntax

The rules you generate MUST pass pySIGMA validation. If validation fails, you will be asked to fix the issues."""

        # Iterative fixing loop (up to 3 attempts)
        sigma_rules = None
        validation_results = []
        attempt = 0  # Start at 0, increment at beginning of loop
        max_attempts = 3
        
        async with httpx.AsyncClient() as client:
            while attempt < max_attempts:
                attempt += 1  # Increment at beginning of loop
                logger.info(f"SIGMA generation attempt {attempt}/{max_attempts} for article {article_id}")
                
                # Prepare messages for this attempt
                messages = [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                # Add validation feedback if this is a retry
                if attempt > 1 and validation_results:
                    last_validation = validation_results[-1]
                    if not last_validation.get('is_valid', False):
                        feedback_prompt = f"""The previous SIGMA rule failed validation. Please fix the following issues:

VALIDATION ERRORS:
{chr(10).join(last_validation.get('errors', []))}

VALIDATION WARNINGS:
{chr(10).join(last_validation.get('warnings', []))}

Please generate a corrected SIGMA rule that addresses these validation issues. Ensure the rule follows proper SIGMA syntax and structure."""
                        
                        messages.append({
                            "role": "user",
                            "content": feedback_prompt
                        })
                
                try:
                    response = await client.post(
                        chatgpt_api_url,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "gpt-4",
                            "messages": messages,
                            "max_tokens": 2048,
                            "temperature": 0.2
                        },
                        timeout=120.0
                    )
                    
                    if response.status_code != 200:
                        error_detail = f"Failed to generate SIGMA rules: {response.status_code}"
                        if response.status_code == 401:
                            error_detail = "Invalid API key. Please check your OpenAI API key in Settings."
                        elif response.status_code == 429:
                            error_detail = "Rate limit exceeded. Please try again later."
                        elif response.status_code == 400:
                            try:
                                error_response = response.json()
                                logger.error(f"OpenAI API 400 error details: {error_response}")
                                error_detail = f"OpenAI API error: {error_response.get('error', {}).get('message', 'Bad request')}"
                            except:
                                error_detail = "OpenAI API error: Bad request - check prompt format"
                        raise HTTPException(status_code=500, detail=error_detail)
                    
                    result = response.json()
                    sigma_rules = result['choices'][0]['message']['content']
                    
                    # Validate the generated rules
                    if sigma_rules:
                        try:
                            # Split rules if multiple rules are generated
                            rules_text = sigma_rules.strip()
                            if '---' in rules_text:
                                individual_rules = [rule.strip() for rule in rules_text.split('---') if rule.strip()]
                            else:
                                individual_rules = [rules_text]
                            
                            attempt_validation_results = []
                            all_valid = True
                            
                            for i, rule_text in enumerate(individual_rules):
                                validation_result = validate_sigma_rule(rule_text)
                                attempt_validation_results.append({
                                    'rule_index': i + 1,
                                    'is_valid': validation_result.is_valid,
                                    'errors': validation_result.errors,
                                    'warnings': validation_result.warnings,
                                    'rule_info': validation_result.rule_info
                                })
                                
                                if not validation_result.is_valid:
                                    all_valid = False
                            
                            validation_results = attempt_validation_results
                            
                            # If all rules are valid, break out of the loop
                            if all_valid:
                                logger.info(f"SIGMA rules passed validation on attempt {attempt}")
                                break
                            else:
                                logger.warning(f"SIGMA rules failed validation on attempt {attempt}")
                                if attempt == max_attempts:
                                    logger.error(f"SIGMA rules failed validation after {max_attempts} attempts")
                                    break
                                
                        except Exception as e:
                            logger.warning(f"SIGMA validation failed on attempt {attempt}: {e}")
                            validation_results = [{
                                'rule_index': 1,
                                'is_valid': False,
                                'errors': [f"Validation error: {e}"],
                                'warnings': [],
                                'rule_info': None
                            }]
                            
                            if attempt == max_attempts:
                                break
                    
                except Exception as e:
                    logger.error(f"SIGMA generation attempt {attempt} failed: {e}")
                    if attempt == max_attempts:
                        raise HTTPException(status_code=500, detail=f"SIGMA generation failed after {max_attempts} attempts: {e}")
        # Check if we have valid rules after all attempts
        if not sigma_rules:
            raise HTTPException(status_code=500, detail="Failed to generate SIGMA rules after all attempts")
        
        # Determine if rules passed validation
        all_rules_valid = all(result.get('is_valid', False) for result in validation_results)
        
        # Store the SIGMA rules in article metadata
        current_metadata = article.metadata.copy() if article.metadata else {}
        current_metadata['sigma_rules'] = {
            'rules': sigma_rules,
            'generated_at': datetime.now().isoformat(),
            'content_type': 'full content' if include_content else 'metadata only',
            'model_used': 'chatgpt',
            'model_name': 'gpt-4',
            'validation_results': validation_results,
            'validation_passed': all_rules_valid,
            'attempts_made': attempt
        }
        
        # Update the article
        update_data = ArticleUpdate(metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        # Prepare response with validation status
        response_data = {
            "success": True,
            "article_id": article_id,
            "sigma_rules": sigma_rules,
            "generated_at": current_metadata['sigma_rules']['generated_at'],
            "content_type": current_metadata['sigma_rules']['content_type'],
            "model_used": current_metadata['sigma_rules']['model_used'],
            "model_name": current_metadata['sigma_rules']['model_name'],
            "validation_results": validation_results,
            "validation_passed": all_rules_valid,
            "attempts_made": attempt
        }
        
        # Add appropriate message based on validation status
        if all_rules_valid:
            response_data["message"] = f"✅ SIGMA rules generated successfully and passed pySIGMA validation after {attempt} attempt(s)."
        else:
            response_data["message"] = f"⚠️ SIGMA rules generated but failed pySIGMA validation after {max_attempts} attempts. Please review the validation errors and consider manual correction."
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SIGMA generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/extract-iocs")
async def api_extract_iocs(article_id: int, request: Request):
    """API endpoint for extracting IOCs from an article using hybrid approach."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        include_content = body.get('include_content', True)  # Default to full content
        api_key = body.get('api_key')  # Get API key from request
        force_regenerate = body.get('force_regenerate', False)  # Force regeneration
        use_llm_validation = body.get('use_llm_validation', True)  # Use LLM validation
        
        logger.info(f"IOC extraction request for article {article_id}, api_key provided: {bool(api_key)}, force_regenerate: {force_regenerate}, use_llm_validation: {use_llm_validation}")
        
        # If force regeneration is requested, skip cache check
        if not force_regenerate:
            # Check if IOCs already exist and return cached version
            existing_iocs = article.metadata.get('extracted_iocs', {}) if article.metadata else {}
            if existing_iocs and existing_iocs.get('iocs'):
                logger.info(f"Returning cached IOCs for article {article_id}")
                return {
                    "success": True,
                    "article_id": article_id,
                    "iocs": existing_iocs['iocs'],
                    "extracted_at": existing_iocs['extracted_at'],
                    "content_type": existing_iocs['content_type'],
                    "model_used": existing_iocs['model_used'],
                    "model_name": existing_iocs['model_name'],
                    "extraction_method": existing_iocs.get('extraction_method', 'unknown'),
                    "confidence": existing_iocs.get('confidence', 0.0),
                    "cached": True
                }
        
        # Initialize hybrid IOC extractor
        ioc_extractor = HybridIOCExtractor(use_llm_validation=use_llm_validation)
        
        # Prepare content for extraction
        if include_content:
            content = article.content
        else:
            # Metadata-only content
            content = f"Title: {article.title}\nURL: {article.canonical_url or 'N/A'}\nPublished: {article.published_at or 'N/A'}\nSource: {article.source_id}"
        
        # Extract IOCs using hybrid approach
        extraction_result = await ioc_extractor.extract_iocs(content, api_key)
        
        # Store the IOCs in article metadata
        current_metadata = article.metadata.copy() if article.metadata else {}
        current_metadata['extracted_iocs'] = {
            'iocs': extraction_result.iocs,
            'extracted_at': datetime.now().isoformat(),
            'content_type': 'full content' if include_content else 'metadata only',
            'model_used': 'hybrid' if extraction_result.extraction_method == 'hybrid' else 'regex',
            'model_name': 'gpt-4' if extraction_result.extraction_method == 'hybrid' else 'custom-regex',
            'extraction_method': extraction_result.extraction_method,
            'confidence': extraction_result.confidence,
            'processing_time': extraction_result.processing_time,
            'raw_count': extraction_result.raw_count,
            'validated_count': extraction_result.validated_count,
            'metadata': extraction_result.metadata
        }
        
        # Update the article
        update_data = ArticleUpdate(metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "iocs": extraction_result.iocs,
            "extracted_at": current_metadata['extracted_iocs']['extracted_at'],
            "content_type": current_metadata['extracted_iocs']['content_type'],
            "model_used": current_metadata['extracted_iocs']['model_used'],
            "model_name": current_metadata['extracted_iocs']['model_name'],
            "extraction_method": extraction_result.extraction_method,
            "confidence": extraction_result.confidence,
            "processing_time": extraction_result.processing_time,
            "raw_count": extraction_result.raw_count,
            "validated_count": extraction_result.validated_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IOC extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/articles/{article_id}/gpt4o-rank")
async def api_gpt4o_rank(article_id: int, request: Request):
    """API endpoint for GPT4o SIGMA huntability ranking."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')  # Get API key from request
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Truncate content if too long (GPT4o has 128K token limit, roughly 500K characters)
        max_chars = 400000  # Leave room for prompt
        content_to_analyze = article.content
        if len(content_to_analyze) > max_chars:
            content_to_analyze = content_to_analyze[:max_chars] + "\n\n[Content truncated due to length]"
        
        # SIGMA-focused prompt
        sigma_prompt = """# Blog Content SIGMA-Suitability Huntability Ranking System

## Your Role

You are a detection engineer evaluating cybersecurity blog content specifically for its suitability to create SIGMA detection rules. Rate content based on how directly it maps to structured log data sources including Windows Event Logs, Sysmon, Linux auditd/Syslog, macOS system logs, AND cloud service logs (AWS CloudTrail, Azure Activity, GCP Audit).

## SIGMA-Focused Scoring (1-10 Scale)

Only content that maps to structured log telemetry receives points. Ignore network payloads, binary analysis, or packet-level details.

## Important Notes

- Do not award points for atomic IOCs (file hashes, IPs, or one-off domains).
- Filename/path patterns and directory conventions are acceptable if they indicate repeatable behavior.
- Only award points for observables that map directly to Windows Event Logs, Sysmon, Linux auditd/Syslog, or macOS system logs.

### Category A – Process Creation & Command-Line Arguments (0-4 pts)

**Data Sources:** 
- Windows: Sysmon Event ID 1, Security 4688
- Linux: process logs, auditd
- **macOS: Endpoint Security process events, unified logging (log show)**
- Cloud: CLI commands in CloudTrail/Activity logs

**Look For:**

- Parent → child process chains with full paths
- Exact command-line strings with arguments, switches, flags
- Process execution sequences
- Cloud CLI commands (aws, az, gcloud) with specific parameters
- **macOS-specific:** osascript commands, launchctl usage, security framework calls

**Scoring:**

- 0 = No process/command details
- 1 = Vague mentions ("runs PowerShell", "uses AWS CLI", or "executes AppleScript")
- 2 = Partial arguments or missing execution context
- 3 = Detailed examples but limited coverage
- 4 = Multiple detailed command chains with full arguments

### Category B – Persistence & System/Service Modification (0-3 pts)

**Data Sources:** 
- Windows: Sysmon Event IDs 12/13/19/7045, Security 4697
- Linux: auditd, systemd logs
- **macOS: LaunchAgent/LaunchDaemon creation, login items, authorization database changes**
- Cloud: AWS CloudTrail, Azure Activity

**Look For:**

- Registry keys with exact paths and values (Windows)
- Service creation/modification details
- Scheduled tasks, cron jobs, or **macOS LaunchAgents/LaunchDaemons**
- Cloud service configurations (IAM roles, SNS topics, Lambda functions, etc.)
- API calls that establish persistence or modify services
- **macOS persistence:** ~/Library/LaunchAgents, /Library/LaunchDaemons, login items, authorization plugins

**Scoring:**

- 0 = No persistence/modification details
- 1 = Generic mention ("creates persistence" or "modifies cloud config")
- 2 = Specific mechanism but incomplete details
- 3 = Exact configurations, API calls, plist files, or settings ready for SIGMA rules

### Category C – Log-Correlated Behavior (0-2 pts)

**Data Sources:** Multiple log sources in sequence (Windows/Linux/macOS/Cloud)

**Look For:**

- Cross-log correlations (process → network, cloud API → local execution)
- Event sequences that can be chained in SIGMA rules
- Time-based correlations between different log types
- Cloud service chains (EC2 → SNS → external endpoint)
- **macOS correlations:** Endpoint Security events + unified logging + authorization logs

**Scoring:**

- 0 = Single log source only
- 1 = Limited correlation opportunities
- 2 = Clear multi-log correlation patterns

### Category D – Structured Log Patterns (0-1 pt)

**Data Sources:** Any structured log format (file creation, API calls, service events)

**Look For:**

- File path patterns or naming conventions (not hashes)
- API call patterns with specific parameters
- Service usage patterns or anomalous configurations
- Structured event patterns in any log format
- **macOS-specific:** .plist file patterns, app bundle structures, Gatekeeper/XProtect logs

**Scoring:**

- 0 = No usable structured patterns
- 1 = Clear structured patterns present

## Important: Multi-Platform Content

**AWS CloudTrail, Azure Activity Logs, GCP Audit Logs, and macOS system logs ARE valid SIGMA data sources.** Do not dismiss cloud-focused or macOS content. API calls, service configurations, LaunchAgent creation, and command execution are all huntable through structured logs.

**macOS SIGMA Data Sources Include:**
- Endpoint Security Framework events
- Unified Logging System (log show commands)  
- Authorization database logs
- LaunchAgent/LaunchDaemon plist files
- Gatekeeper and XProtect logs

## Scoring Bands

- **1-2:** Mostly strategic content, minimal SIGMA applicability
- **3-4:** Limited SIGMA potential, too generic for reliable rules
- **5-6:** Moderate SIGMA candidates with some specificity
- **7-8:** Strong SIGMA potential, multiple rule-ready observables
- **9-10:** Excellent SIGMA content, rules can be drafted immediately

## Output Format

**SIGMA HUNTABILITY SCORE: [1-10]**

**CATEGORY BREAKDOWN:**

- **Process/Command-Line (0-4):** [Score] - [Brief reasoning, noting platform if applicable]
- **Persistence/System Mods (0-3):** [Score] - [Brief reasoning, noting platform-specific mechanisms]
- **Log Correlation (0-2):** [Score] - [Brief reasoning]
- **Structured Patterns (0-1):** [Score] - [Brief reasoning]

**SIGMA-READY OBSERVABLES:**
[List specific elements that can directly become SIGMA rules, noting target platform]

**REQUIRED LOG SOURCES:**
[Windows Event IDs, Sysmon events, Linux logs, macOS log sources, OR cloud service logs needed]

**RULE FEASIBILITY:**
[Assessment of how quickly detection rules could be created, noting any platform-specific considerations]

## Instructions

Analyze the provided blog content using this SIGMA-focused rubric. All major platforms (Windows, Linux, macOS) and cloud service logs are valid SIGMA data sources. Focus on structured log patterns regardless of platform. Ignore only unstructured data like network payloads or binary analysis.

Please analyze the following blog content:

**Title:** {title}
**Source:** {source}
**URL:** {url}

**Content:**
{content}"""
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze
        )
        
        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
        
        # Save the analysis to the article's metadata
        if article.metadata is None:
            article.metadata = {}
        
        article.metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat(),
            'model': 'gpt-4o'
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(metadata=article.metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Enhanced GPT-4o ranking endpoint with content filtering
@app.post("/api/articles/{article_id}/gpt4o-rank-optimized")
async def api_gpt4o_rank_optimized(article_id: int, request: Request):
    """Enhanced API endpoint for GPT4o SIGMA huntability ranking with content filtering."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Get request body
        body = await request.json()
        article_url = body.get('url')
        api_key = body.get('api_key')
        use_filtering = body.get('use_filtering', True)  # Enable filtering by default
        min_confidence = body.get('min_confidence', 0.7)  # Confidence threshold
        
        if not api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key is required. Please configure it in Settings.")
        
        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")
        
        # Import the optimizer
        from src.utils.gpt4o_optimizer import optimize_article_content
        
        # Optimize content if filtering is enabled
        if use_filtering:
            logger.info(f"Optimizing content for article {article_id} with confidence threshold {min_confidence}")
            optimization_result = await optimize_article_content(article.content, min_confidence)
            
            if optimization_result['success']:
                content_to_analyze = optimization_result['filtered_content']
                cost_savings = optimization_result['cost_savings']
                tokens_saved = optimization_result['tokens_saved']
                chunks_removed = optimization_result['chunks_removed']
                
                logger.info(f"Content optimization completed: "
                           f"{tokens_saved:,} tokens saved, "
                           f"${cost_savings:.4f} cost savings, "
                           f"{chunks_removed} chunks removed")
            else:
                logger.warning("Content optimization failed, using original content")
                content_to_analyze = article.content
                cost_savings = 0.0
                tokens_saved = 0
                chunks_removed = 0
        else:
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0
        
        # Truncate content if still too long (GPT4o has 128K token limit, roughly 500K characters)
        max_chars = 400000  # Leave room for prompt
        if len(content_to_analyze) > max_chars:
            content_to_analyze = content_to_analyze[:max_chars] + "\n\n[Content truncated due to length]"
        
        # SIGMA-focused prompt (same as original)
        sigma_prompt = """# Blog Content SIGMA-Suitability Huntability Ranking System

## Your Role

You are a detection engineer evaluating cybersecurity blog content specifically for its suitability to create SIGMA detection rules. Rate content based on how directly it maps to structured log data sources including Windows Event Logs, Sysmon, Linux auditd/Syslog, macOS system logs, AND cloud service logs (AWS CloudTrail, Azure Activity, GCP Audit).

## SIGMA-Focused Scoring (1-10 Scale)

Only content that maps to structured log telemetry receives points. Ignore network payloads, binary analysis, or packet-level details.

## Important Notes

- Do not award points for atomic IOCs (file hashes, IPs, or one-off domains).
- Filename/path patterns and directory conventions are acceptable if they indicate repeatable behavior.
- Only award points for observables that map directly to Windows Event Logs, Sysmon, Linux auditd/Syslog, or macOS system logs.

### Category A – Process Creation & Command-Line Arguments (0-4 pts)

**Data Sources:** 
- Windows: Sysmon Event ID 1, Security 4688
- Linux: process logs, auditd
- **macOS: Endpoint Security process events, unified logging (log show)**
- Cloud: CLI commands in CloudTrail/Activity logs

**Look For:**

- Parent → child process chains with full paths
- Exact command-line strings with arguments, switches, flags
- Process execution sequences
- Cloud CLI commands (aws, az, gcloud) with specific parameters
- **macOS-specific:** osascript commands, launchctl usage, security framework calls

**Scoring:**

- 0 = No process/command details
- 1 = Vague mentions ("runs PowerShell", "uses AWS CLI", or "executes AppleScript")
- 2 = Partial arguments or missing execution context
- 3 = Detailed examples but limited coverage
- 4 = Multiple detailed command chains with full arguments

### Category B – Persistence & System/Service Modification (0-3 pts)

**Data Sources:** 
- Windows: Sysmon Event IDs 12/13/19/7045, Security 4697
- Linux: auditd, systemd logs
- **macOS: LaunchAgent/LaunchDaemon creation, login items, authorization database changes**
- Cloud: AWS CloudTrail, Azure Activity

**Look For:**

- Registry keys with exact paths and values (Windows)
- Service creation/modification details
- Scheduled tasks, cron jobs, or **macOS LaunchAgents/LaunchDaemons**
- Cloud service configurations (IAM roles, SNS topics, Lambda functions, etc.)
- API calls that establish persistence or modify services
- **macOS persistence:** ~/Library/LaunchAgents, /Library/LaunchDaemons, login items, authorization plugins

**Scoring:**

- 0 = No persistence/modification details
- 1 = Generic mention ("creates persistence" or "modifies cloud config")
- 2 = Specific mechanism but incomplete details
- 3 = Exact configurations, API calls, plist files, or settings ready for SIGMA rules

### Category C – Log-Correlated Behavior (0-2 pts)

**Data Sources:** Multiple log sources in sequence (Windows/Linux/macOS/Cloud)

**Look For:**

- Cross-log correlations (process → network, cloud API → local execution)
- Event sequences that can be chained in SIGMA rules
- Time-based correlations between different log types
- Cloud service chains (EC2 → SNS → external endpoint)
- **macOS correlations:** Endpoint Security events + unified logging + authorization logs

**Scoring:**

- 0 = Single log source only
- 1 = Limited correlation opportunities
- 2 = Clear multi-log correlation patterns

### Category D – Structured Log Patterns (0-1 pt)

**Data Sources:** Any structured log format (file creation, API calls, service events)

**Look For:**

- File path patterns or naming conventions (not hashes)
- API call patterns with specific parameters
- Service usage patterns or anomalous configurations
- Structured event patterns in any log format
- **macOS-specific:** .plist file patterns, app bundle structures, Gatekeeper/XProtect logs

**Scoring:**

- 0 = No usable structured patterns
- 1 = Clear structured patterns present

## Important: Multi-Platform Content

**AWS CloudTrail, Azure Activity Logs, GCP Audit Logs, and macOS system logs ARE valid SIGMA data sources.** Do not dismiss cloud-focused or macOS content. API calls, service configurations, LaunchAgent creation, and command execution are all huntable through structured logs.

**macOS SIGMA Data Sources Include:**
- Endpoint Security Framework events
- Unified Logging System (log show commands)  
- Authorization database logs
- LaunchAgent/LaunchDaemon plist files
- Gatekeeper and XProtect logs

## Scoring Bands

- **1-2:** Mostly strategic content, minimal SIGMA applicability
- **3-4:** Limited SIGMA potential, too generic for reliable rules
- **5-6:** Moderate SIGMA candidates with some specificity
- **7-8:** Strong SIGMA potential, multiple rule-ready observables
- **9-10:** Excellent SIGMA content, rules can be drafted immediately

## Output Format

**SIGMA HUNTABILITY SCORE: [1-10]**

**CATEGORY BREAKDOWN:**

- **Process/Command-Line (0-4):** [Score] - [Brief reasoning, noting platform if applicable]
- **Persistence/System Mods (0-3):** [Score] - [Brief reasoning, noting platform-specific mechanisms]
- **Log Correlation (0-2):** [Score] - [Brief reasoning]
- **Structured Patterns (0-1):** [Score] - [Brief reasoning]

**SIGMA-READY OBSERVABLES:**
[List specific elements that can directly become SIGMA rules, noting target platform]

**REQUIRED LOG SOURCES:**
[Windows Event IDs, Sysmon events, Linux logs, macOS log sources, OR cloud service logs needed]

**RULE FEASIBILITY:**
[Assessment of how quickly detection rules could be created, noting any platform-specific considerations]

## Instructions

Analyze the provided blog content using this SIGMA-focused rubric. All major platforms (Windows, Linux, macOS) and cloud service logs are valid SIGMA data sources. Focus on structured log patterns regardless of platform. Ignore only unstructured data like network payloads or binary analysis.

Please analyze the following blog content:

**Title:** {title}
**Source:** {source}
**URL:** {url}

**Content:**
{content}"""
        
        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"
        
        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze
        )
        
        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.3
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")
            
            result = response.json()
            analysis = result['choices'][0]['message']['content']
        
        # Save the analysis to the article's metadata
        if article.metadata is None:
            article.metadata = {}
        
        article.metadata['gpt4o_ranking'] = {
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat(),
            'model': 'gpt-4o',
            'optimization_enabled': use_filtering,
            'cost_savings': cost_savings,
            'tokens_saved': tokens_saved,
            'chunks_removed': chunks_removed,
            'min_confidence': min_confidence if use_filtering else None
        }
        
        # Update the article in the database
        from src.models.article import ArticleUpdate
        update_data = ArticleUpdate(metadata=article.metadata)
        await async_db_manager.update_article(article_id, update_data)
        
        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.utcnow().isoformat(),
            "optimization": {
                "enabled": use_filtering,
                "cost_savings": cost_savings,
                "tokens_saved": tokens_saved,
                "chunks_removed": chunks_removed,
                "min_confidence": min_confidence if use_filtering else None
            },
            "debug_info": {
                "removed_chunks": optimization_result.get('removed_chunks', []) if use_filtering and optimization_result.get('success') else [],
                "original_length": len(article.content),
                "filtered_length": len(content_to_analyze),
                "reduction_percent": round((len(article.content) - len(content_to_analyze)) / len(article.content) * 100, 1) if use_filtering else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
# Annotation API endpoints

@app.post("/api/articles/{article_id}/annotations")
async def create_annotation(article_id: int, annotation_data: dict):
    """Create a new text annotation for an article."""
    try:
        # Verify article exists
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Create annotation data object
        from src.models.annotation import ArticleAnnotationCreate
        annotation_create = ArticleAnnotationCreate(
            article_id=article_id,
            annotation_type=annotation_data.get("annotation_type"),
            selected_text=annotation_data.get("selected_text"),
            start_position=annotation_data.get("start_position"),
            end_position=annotation_data.get("end_position"),
            context_before=annotation_data.get("context_before"),
            context_after=annotation_data.get("context_after"),
            confidence_score=annotation_data.get("confidence_score", 1.0)
        )
        
        # Create annotation
        annotation = await async_db_manager.create_annotation(annotation_create)
        if not annotation:
            raise HTTPException(status_code=500, detail="Failed to create annotation")
        
        logger.info(f"Created annotation {annotation.id} for article {article_id}")
        
        return {
            "success": True,
            "annotation": annotation,
            "message": f"Annotation created successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles/{article_id}/annotations")
async def get_article_annotations(article_id: int):
    """Get all annotations for a specific article."""
    try:
        # Verify article exists
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        annotations = await async_db_manager.get_article_annotations(article_id)
        
        return {
            "success": True,
            "article_id": article_id,
            "annotations": annotations,
            "count": len(annotations)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get annotations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/articles/{article_id}/annotations/{annotation_id}")
async def delete_annotation(article_id: int, annotation_id: int):
    """Delete a specific annotation"""
    try:
        # Verify article exists
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        success = await async_db_manager.delete_annotation(annotation_id)
        if success:
            return {"success": True, "message": f"Annotation {annotation_id} deleted"}
        else:
            raise HTTPException(status_code=404, detail="Annotation not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting annotation {annotation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete annotation")

@app.get("/api/annotations/stats")
async def get_annotation_stats():
    """Get annotation statistics."""
    try:
        stats = await async_db_manager.get_annotation_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get annotation stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/annotations/{annotation_id}")
async def get_annotation(annotation_id: int):
    """Get a specific annotation by ID."""
    try:
        annotation = await async_db_manager.get_annotation(annotation_id)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")
        
        return {
            "success": True,
            "annotation": annotation
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/annotations/{annotation_id}")
async def get_annotation(annotation_id: int):
    """Get a specific annotation by ID."""
    try:
        annotation = await async_db_manager.get_annotation(annotation_id)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")
        
        return {
            "success": True,
            "annotation": annotation
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/annotations/{annotation_id}")
async def update_annotation(annotation_id: int, update_data: ArticleAnnotationUpdate):
    """Update an existing annotation."""
    try:
        annotation = await async_db_manager.update_annotation(annotation_id, update_data)
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found")
        
        logger.info(f"Updated annotation {annotation_id}")
        
        return {
            "success": True,
            "annotation": annotation,
            "message": "Annotation updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/annotations/{annotation_id}")
async def delete_annotation(annotation_id: int):
    """Delete an annotation."""
    try:
        success = await async_db_manager.delete_annotation(annotation_id)
        if not success:
            raise HTTPException(status_code=404, detail="Annotation not found")
        
        logger.info(f"Deleted annotation {annotation_id}")
        
        return {
            "success": True,
            "message": "Annotation deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete annotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/articles/{article_id}")
async def delete_article(article_id: int):
    """Delete an article and all its related data."""
    try:
        # Verify article exists first
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # Delete the article and all related data
        success = await async_db_manager.delete_article(article_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete article")
        
        logger.info(f"Deleted article {article_id}")
        
        return {
            "success": True,
            "message": "Article deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete article: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors."""
    # Check if this is an API request
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            content={"detail": "Not found"},
            status_code=404
        )
    
    # For non-API requests, return HTML error page
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

# Static file serving for backups
backup_dir = Path("backups")
backup_dir.mkdir(exist_ok=True)
app.mount("/backups", StaticFiles(directory=str(backup_dir)), name="backups")

# Database Backup & Restore API endpoints
@app.post("/api/backup/create")
async def api_create_backup(background_tasks: BackgroundTasks):
    """Create a new database backup."""
    try:
        from pathlib import Path
        import gzip
        import io
        
        # Create backup directory
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"cti_scraper_backup_{timestamp}.sql.gz"
        backup_path = backup_dir / backup_filename
        
        # Create backup using SQLAlchemy to dump all tables
        from sqlalchemy import text, inspect
        from src.database.async_manager import AsyncDatabaseManager
        
        db_manager = AsyncDatabaseManager()
        
        # Get database connection
        async with db_manager.get_session() as session:
            # Get all table names using raw SQL
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            
            backup_content = []
            backup_content.append("-- PostgreSQL database backup")
            backup_content.append(f"-- Generated at: {datetime.now().isoformat()}")
            backup_content.append("-- CTI Scraper Database Backup")
            backup_content.append("")
            
            # Add SET statements
            backup_content.append("SET statement_timeout = 0;")
            backup_content.append("SET lock_timeout = 0;")
            backup_content.append("SET idle_in_transaction_session_timeout = 0;")
            backup_content.append("SET client_encoding = 'UTF8';")
            backup_content.append("SET standard_conforming_strings = on;")
            backup_content.append("SET check_function_bodies = false;")
            backup_content.append("SET xmloption = content;")
            backup_content.append("SET client_min_messages = warning;")
            backup_content.append("SET row_security = off;")
            backup_content.append("")
            
            # For each table, dump data only (simplified approach)
            for table_name in tables:
                backup_content.append(f"-- Data for table {table_name}")
                
                # Get column names first
                col_result = await session.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """))
                columns = [row[0] for row in col_result.fetchall()]
                
                if not columns:
                    continue
                
                # Get table data
                result = await session.execute(text(f'SELECT * FROM "{table_name}"'))
                rows = result.fetchall()
                
                if rows:
                    backup_content.append(f"-- Data for table {table_name}")
                    
                    for row in rows:
                        values = []
                        for i, col in enumerate(columns):
                            value = row[i]
                            if value is None:
                                values.append('NULL')
                            elif isinstance(value, str):
                                # Escape single quotes
                                escaped_value = value.replace("'", "''")
                                values.append(f"'{escaped_value}'")
                            else:
                                values.append(str(value))
                        
                        # Build column names and values separately
                        col_names = ", ".join(f'"{col}"' for col in columns)
                        val_str = ", ".join(values)
                        insert_sql = f'INSERT INTO "{table_name}" ({col_names}) VALUES ({val_str});'
                        backup_content.append(insert_sql)
                    
                    backup_content.append("")
            
            # Compress the backup
            backup_text = "\n".join(backup_content)
            with gzip.open(backup_path, 'wt') as f:
                f.write(backup_text)
        
        # Get file size
        file_size = backup_path.stat().st_size
        
        return {
            "success": True,
            "message": f"Backup created successfully: {backup_filename}",
            "backup_file": backup_filename,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Backup creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/annotations")
async def api_export_annotations():
    """Export all annotations to CSV."""
    try:
        import io
        import csv
        from datetime import datetime
        
        # Get annotations from database
        async with async_db_manager.get_session() as session:
            from sqlalchemy import text
            
            query = text("""
            SELECT 
                ROW_NUMBER() OVER (ORDER BY th.created_at) as record_number,
                th.selected_text as highlighted_text,
                CASE 
                    WHEN th.is_huntable = true THEN 'Huntable'
                    WHEN th.is_huntable = false THEN 'Not Huntable'
                    ELSE 'Unknown'
                END as classification,
                a.title as article_title,
                th.created_at as classification_date
            FROM text_highlights th
            LEFT JOIN articles a ON th.article_id = a.id
            ORDER BY th.created_at
            """)
            
            result = await session.execute(query)
            annotations = result.fetchall()
        
        # Create CSV content
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['record_number', 'highlighted_text', 'classification', 'article_title', 'classification_date'])
        
        # Write data
        for annotation in annotations:
            writer.writerow([
                annotation.record_number,
                annotation.highlighted_text,
                annotation.classification,
                annotation.article_title,
                annotation.classification_date.isoformat() if annotation.classification_date else ''
            ])
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"annotations_{timestamp}.csv"
        
        # Return CSV as response
        csv_content = output.getvalue()
        output.close()
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Export annotations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/backup/list")
async def api_list_backups():
    """List all available database backups."""
    try:
        from pathlib import Path
        import os
        
        backup_dir = Path("backups")
        if not backup_dir.exists():
            return {"backups": []}
        
        backups = []
        for backup_file in backup_dir.glob("*.sql.gz"):
            stat = backup_file.stat()
            backups.append({
                "filename": backup_file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {"backups": backups}
        
    except Exception as e:
        logger.error(f"Backup listing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/backup/restore")
async def api_restore_backup(request: Request):
    """Restore database from a backup file."""
    try:
        from fastapi import UploadFile, File
        import tempfile
        import gzip
        
        # Get uploaded file
        form = await request.form()
        backup_file = form.get("backup_file")
        if not backup_file:
            raise HTTPException(status_code=400, detail="No backup file provided")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sql.gz") as temp_file:
            content = await backup_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Decompress and restore using SQLAlchemy
            with gzip.open(temp_file_path, 'rt') as f_gz:
                sql_content = f_gz.read()
            
            from sqlalchemy import text
            from src.database.async_manager import AsyncDatabaseManager
            
            db_manager = AsyncDatabaseManager()
            
            # Split SQL content into individual statements
            statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
            
            async with db_manager.get_session() as session:
                # Execute each SQL statement
                for statement in statements:
                    if statement and not statement.startswith('--'):
                        try:
                            await session.execute(text(statement))
                        except Exception as e:
                            # Log the error but continue with other statements
                            logger.warning(f"Failed to execute statement: {statement[:100]}... Error: {e}")
                
                # Commit all changes
                await session.commit()
            
            return {
                "success": True,
                "message": "Database restored successfully",
                "restored_at": datetime.now().isoformat()
            }
            
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)
        
    except Exception as e:
        logger.error(f"Backup restore error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/backup/{backup_filename}")
async def api_delete_backup(backup_filename: str):
    """Delete a specific backup file."""
    try:
        from pathlib import Path
        
        # Security check - ensure filename is safe
        if not backup_filename.endswith('.sql.gz') or '..' in backup_filename or '/' in backup_filename:
            raise HTTPException(status_code=400, detail="Invalid backup filename")
        
        backup_path = Path("backups") / backup_filename
        if not backup_path.exists():
            raise HTTPException(status_code=404, detail="Backup file not found")
        
        backup_path.unlink()
        
        return {
            "success": True,
            "message": f"Backup {backup_filename} deleted successfully"
        }
        
    except Exception as e:
        logger.error(f"Backup deletion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Database Chat API Endpoints
from src.services.sql_generator import SQLGenerator
from src.services.query_executor import DatabaseQueryExecutor

# Initialize services
sql_generator = SQLGenerator()
query_executor = DatabaseQueryExecutor()

@app.post("/api/database-chat")
async def api_database_chat(request: Request):
    """Handle natural language database queries."""
    try:
        body = await request.json()
        user_query = body.get("query", "").strip()
        
        if not user_query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Generate SQL from natural language with timeout
        import asyncio
        try:
            sql_result = await asyncio.wait_for(sql_generator.generate_sql(user_query), timeout=30.0)
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Query generation timed out. Please try a simpler query.",
                "user_query": user_query
            }
        
        if not sql_result["success"]:
            return {
                "success": False,
                "error": f"SQL generation failed: {sql_result.get('error', 'Unknown error')}",
                "user_query": user_query
            }
        
        sql_query = sql_result["sql"]
        
        # Execute the SQL query
        execution_result = await query_executor.execute_query(sql_query)
        
        if not execution_result["success"]:
            return {
                "success": False,
                "error": f"Query execution failed: {execution_result.get('error', 'Unknown error')}",
                "user_query": user_query,
                "generated_sql": sql_query
            }
        
        # Generate explanation of results
        explanation = await sql_generator.explain_query(
            sql_query, 
            execution_result["results"], 
            user_query
        )
        
        return {
            "success": True,
            "user_query": user_query,
            "generated_sql": sql_query,
            "results": execution_result["results"],
            "columns": execution_result["columns"],
            "row_count": execution_result["row_count"],
            "execution_time": execution_result["execution_time"],
            "explanation": explanation,
            "metadata": {
                "model_used": sql_result.get("model_used"),
                "query_info": execution_result.get("query_info", {}),
                "warnings": execution_result.get("warnings", [])
            }
        }
        
    except Exception as e:
        logger.error(f"Database chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/database-chat/paginated")
async def api_database_chat_paginated(request: Request):
    """Handle paginated natural language database queries."""
    try:
        body = await request.json()
        user_query = body.get("query", "").strip()
        page = body.get("page", 1)
        page_size = body.get("page_size", 50)
        
        if not user_query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        # Generate SQL from natural language
        sql_result = await sql_generator.generate_sql(user_query)
        
        if not sql_result["success"]:
            return {
                "success": False,
                "error": f"SQL generation failed: {sql_result.get('error', 'Unknown error')}",
                "user_query": user_query
            }
        
        sql_query = sql_result["sql"]
        
        # Execute the SQL query with pagination
        execution_result = await query_executor.execute_with_pagination(sql_query, page, page_size)
        
        if not execution_result["success"]:
            return {
                "success": False,
                "error": f"Query execution failed: {execution_result.get('error', 'Unknown error')}",
                "user_query": user_query,
                "generated_sql": sql_query
            }
        
        # Generate explanation of results
        explanation = await sql_generator.explain_query(
            sql_query, 
            execution_result["results"], 
            user_query
        )
        
        return {
            "success": True,
            "user_query": user_query,
            "generated_sql": sql_query,
            "results": execution_result["results"],
            "columns": execution_result["columns"],
            "row_count": execution_result["row_count"],
            "execution_time": execution_result["execution_time"],
            "explanation": explanation,
            "pagination": execution_result.get("pagination", {}),
            "metadata": {
                "model_used": sql_result.get("model_used"),
                "query_info": execution_result.get("query_info", {}),
                "warnings": execution_result.get("warnings", [])
            }
        }
        
    except Exception as e:
        logger.error(f"Database chat paginated error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database-chat/sample/{table_name}")
async def api_get_table_sample(table_name: str, limit: int = 5):
    """Get sample data from a table."""
    try:
        result = await query_executor.get_sample_data(table_name, limit)
        return result
    except Exception as e:
        logger.error(f"Table sample error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/database-chat/info/{table_name}")
async def api_get_table_info(table_name: str):
    """Get table schema information."""
    try:
        result = await query_executor.get_table_info(table_name)
        return result
    except Exception as e:
        logger.error(f"Table info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.web.modern_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
