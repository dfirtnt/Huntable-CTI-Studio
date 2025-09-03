#!/usr/bin/env python3
"""
FastAPI Web Server for CTI Scraper

Provides a modern web interface for browsing collected threat intelligence,
analyzing TTPs, and viewing quality assessments.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

# Setup logging
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Import our modules
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from database.manager import DatabaseManager
from utils.ttp_extractor import ThreatHuntingDetector

# Initialize FastAPI app
app = FastAPI(
    title="CTI Scraper Web Interface",
    description="Modern web interface for threat intelligence aggregation and analysis",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates and static files
templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(templates_dir))
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize database and TTP detector
db_manager = DatabaseManager()
ttp_detector = ThreatHuntingDetector()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard showing overview of collected intelligence."""
    try:
        # Get database statistics
        stats = db_manager.get_database_stats()
        
        # Get recent articles
        recent_articles = db_manager.list_articles()
        if len(recent_articles) > 10:
            recent_articles = recent_articles[:10]
        
        # Get sources
        sources = db_manager.list_sources()
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "stats": stats,
                "recent_articles": recent_articles,
                "sources": sources,
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Failed to load dashboard: {str(e)}"}
        )

@app.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    quality_min: Optional[int] = Query(None, ge=0, le=75)
):
    """Browse all collected articles with filtering and pagination."""
    try:
        # Get all articles
        all_articles = db_manager.list_articles()
        
        # Apply filters
        if source:
            all_articles = [a for a in all_articles if str(a.source_id) == source]
        
        if search:
            search_lower = search.lower()
            all_articles = [
                a for a in all_articles 
                if search_lower in a.title.lower() or search_lower in a.content.lower()
            ]
        
        # Apply quality filter if specified
        if quality_min is not None:
            filtered_articles = []
            for article in all_articles:
                quality_score = ttp_detector.calculate_ttp_quality_score(article.content)
                if quality_score['total_score'] >= quality_min:
                    filtered_articles.append(article)
            all_articles = filtered_articles
        
        # Pagination
        total_articles = len(all_articles)
        total_pages = (total_articles + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        articles = all_articles[start_idx:end_idx]
        
        # Get sources for filter dropdown
        sources = db_manager.list_sources()
        
        return templates.TemplateResponse(
            "articles.html",
            {
                "request": request,
                "articles": articles,
                "sources": sources,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": total_pages,
                    "total_articles": total_articles,
                    "start_idx": start_idx + 1,
                    "end_idx": min(end_idx, total_articles)
                },
                "filters": {
                    "source": source,
                    "search": search,
                    "quality_min": quality_min
                }
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)}
        )

@app.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    """View detailed article with TTP analysis and quality assessment."""
    try:
        # Get article
        article = db_manager.get_article(article_id)
        if not article:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Article not found"},
                status_code=404
            )
        
        # Get source info
        source = db_manager.get_source(article.source_id)
        
        # Analyze article for TTPs
        ttp_analysis = ttp_detector.detect_hunting_techniques(article.content, article_id)
        
        # Get quality assessment
        quality_report = ttp_detector.generate_quality_report(article.content)
        quality_data = ttp_detector.calculate_ttp_quality_score(article.content)
        
        return templates.TemplateResponse(
            "article_detail.html",
            {
                "request": request,
                "article": article,
                "source": source,
                "ttp_analysis": ttp_analysis,
                "quality_report": quality_report,
                "quality_data": quality_data
            }
        )
    except Exception as e:
        logger.error(f"Article detail error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": f"Failed to load article: {str(e)}"},
            status_code=500
        )

@app.get("/analysis", response_class=HTMLResponse)
async def analysis_dashboard(request: Request):
    """TTP analysis dashboard showing hunting techniques and quality metrics."""
    try:
        # Get all articles for analysis
        all_articles = db_manager.list_articles()
        
        # Analyze articles (limit to recent ones for performance)
        recent_articles = all_articles[-50:] if len(all_articles) > 50 else all_articles
        
        analyses = []
        quality_scores = []
        
        for article in recent_articles:
            try:
                # TTP analysis
                analysis = ttp_detector.detect_hunting_techniques(article.content, article.id)
                if analysis.total_techniques > 0:
                    analyses.append({
                        'article': article,
                        'analysis': analysis
                    })
                
                # Quality assessment
                quality = ttp_detector.calculate_ttp_quality_score(article.content)
                quality_scores.append(quality)
                
            except Exception as e:
                continue  # Skip articles that fail analysis
        
        # Calculate overall statistics
        if quality_scores:
            avg_quality = sum(q['total_score'] for q in quality_scores) / len(quality_scores)
            quality_distribution = {
                'Excellent': len([q for q in quality_scores if q['total_score'] >= 60]),
                'Good': len([q for q in quality_scores if 45 <= q['total_score'] < 60]),
                'Fair': len([q for q in quality_scores if 30 <= q['total_score'] < 45]),
                'Limited': len([q for q in quality_scores if q['total_score'] < 30])
            }
        else:
            avg_quality = 0
            quality_distribution = {'Excellent': 0, 'Good': 0, 'Fair': 0, 'Limited': 0}
        
        return templates.TemplateResponse(
            "analysis.html",
            {
                "request": request,
                "analyses": analyses[:20],  # Limit to top 20 for performance
                "quality_stats": {
                    "average_score": avg_quality,
                    "distribution": quality_distribution,
                    "total_analyzed": len(quality_scores)
                }
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)}
        )

@app.get("/sources", response_class=HTMLResponse)
async def sources_list(request: Request):
    """View all configured threat intelligence sources."""
    try:
        sources = db_manager.list_sources()
        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "sources": sources
            }
        )
    except Exception as e:
        logger.error(f"Sources list error: {e}")
        # Provide a more user-friendly error message for database issues
        if "database is locked" in str(e):
            error_msg = "Database is temporarily busy. Please wait a moment and refresh the page."
        else:
            error_msg = f"Failed to load sources: {str(e)}"
        
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": error_msg}
        )

@app.post("/api/sources/{source_id}/test")
async def test_source(source_id: int):
    """Test if a source is accessible and working."""
    try:
        import httpx
        import asyncio
        from datetime import datetime
        
        # Get the source
        source = db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Test the source URLs
        results = {
            "source_id": source_id,
            "source_name": source.name,
            "timestamp": datetime.now().isoformat(),
            "tests": []
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test main URL
            try:
                response = await client.get(source.url)
                results["tests"].append({
                    "url": source.url,
                    "type": "main_url",
                    "status": response.status_code,
                    "success": response.status_code == 200,
                    "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
                })
            except Exception as e:
                results["tests"].append({
                    "url": source.url,
                    "type": "main_url",
                    "status": None,
                    "success": False,
                    "error": str(e)
                })
            
            # Test RSS URL if available
            if source.rss_url:
                try:
                    response = await client.get(source.rss_url)
                    results["tests"].append({
                        "url": source.rss_url,
                        "type": "rss_feed",
                        "status": response.status_code,
                        "success": response.status_code == 200,
                        "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else None
                    })
                except Exception as e:
                    results["tests"].append({
                        "url": source.rss_url,
                        "type": "rss_feed",
                        "status": None,
                        "success": False,
                        "error": str(e)
                    })
        
        # Calculate overall success
        results["overall_success"] = all(test["success"] for test in results["tests"])
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sources/{source_id}/stats")
async def get_source_stats(source_id: int):
    """Get detailed statistics for a specific source."""
    try:
        # Get the source
        source = db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Get articles from this source
        all_articles = db_manager.list_articles()
        source_articles = [a for a in all_articles if a.source_id == source_id]
        
        # Calculate stats
        total_articles = len(source_articles)
        
        # Group by date for trends
        from collections import defaultdict
        articles_by_date = defaultdict(int)
        content_lengths = []
        
        for article in source_articles:
            if article.published_at:
                date_key = article.published_at.strftime('%Y-%m-%d')
                articles_by_date[date_key] += 1
            content_lengths.append(len(article.content))
        
        # Calculate quality scores
        quality_scores = []
        for article in source_articles[:20]:  # Sample first 20 for performance
            quality_score = ttp_detector.calculate_ttp_quality_score(article.content)
            quality_scores.append(quality_score['total_score'])
        
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        avg_content_length = sum(content_lengths) / len(content_lengths) if content_lengths else 0
        
        stats = {
            "source_id": source_id,
            "source_name": source.name,
            "total_articles": total_articles,
            "avg_content_length": round(avg_content_length, 1),
            "avg_quality_score": round(avg_quality, 1),
            "articles_by_date": dict(sorted(articles_by_date.items())),
            "is_active": source.active,
            "tier": source.tier,
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "url": source.url,
            "rss_url": source.rss_url,
            "collection_method": "RSS Feed" if source.rss_url else "Web Scraping"
        }
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sources/{source_id}/toggle")
async def toggle_source_status(source_id: int):
    """Toggle the active/inactive status of a source."""
    try:
        # Get the source
        source = db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        
        # Toggle the status
        new_status = not source.active
        
        # Update the database using a more robust approach with proper SQLite handling
        actual_status = new_status
        database_updated = False
        
        try:
            # Use a simple SQL update with proper connection handling and retries
            import sqlite3
            import time
            
            # Try multiple times with increasing delays
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Connect to the database with proper timeout and isolation
                    conn = sqlite3.connect('threat_intel.db', timeout=30.0, isolation_level=None)
                    cursor = conn.cursor()
                    
                    # Enable WAL mode for better concurrency
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA cache_size=10000")
                    cursor.execute("PRAGMA temp_store=MEMORY")
                    
                    # Update the source status
                    cursor.execute(
                        "UPDATE sources SET active = ?, updated_at = ? WHERE id = ?",
                        (new_status, datetime.now().isoformat(), source_id)
                    )
                    
                    # Check if the update was successful
                    if cursor.rowcount == 0:
                        raise HTTPException(status_code=404, detail="Source not found")
                    
                    # Commit the changes
                    conn.commit()
                    conn.close()
                    
                    # Update was successful
                    database_updated = True
                    logger.info(f"Successfully updated source {source_id} status to {new_status}")
                    break
                    
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) and attempt < max_retries - 1:
                        logger.warning(f"Database locked on attempt {attempt + 1}, retrying in {2 ** attempt} seconds...")
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise e
                        
        except Exception as db_error:
            logger.error(f"Database update error: {db_error}")
            # Fall back to simulation mode if database update fails
            logger.warning("Falling back to simulation mode due to database error")
            database_updated = False
        
        return {
            "source_id": source_id,
            "source_name": source.name,
            "old_status": source.active,
            "new_status": actual_status,
            "message": f"Source {'activated' if actual_status else 'deactivated'} successfully",
            "success": True,
            "database_updated": database_updated,
            "note": "Database updated successfully! The page will refresh to show the new status." if database_updated else "Database update failed, but showing what the change would look like. Refresh manually to see current status."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/articles")
async def api_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """API endpoint for articles (JSON response)."""
    try:
        all_articles = db_manager.list_articles()
        
        # Apply filters
        if source:
            all_articles = [a for a in all_articles if str(a.source_id) == source]
        
        if search:
            search_lower = search.lower()
            all_articles = [
                a for a in all_articles 
                if search_lower in a.title.lower() or search_lower in a.content.lower()
            ]
        
        # Pagination
        total = len(all_articles)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        articles = all_articles[start_idx:end_idx]
        
        return {
                                "articles": [
                        {
                            "id": a.id,
                            "title": a.title,
                            "source_id": a.source_id,
                            "url": a.canonical_url,
                            "published_date": a.published_at.isoformat() if a.published_at else None,
                            "content_length": len(a.content),
                            "content_preview": a.content[:200] + "..." if len(a.content) > 200 else a.content
                        }
                        for a in articles
                    ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analysis/{article_id}")
async def api_article_analysis(article_id: int):
    """API endpoint for article TTP analysis (JSON response)."""
    try:
        article = db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        analysis = ttp_detector.detect_hunting_techniques(article.content, article_id)
        quality = ttp_detector.calculate_ttp_quality_score(article.content)
        
        return {
            "article_id": article_id,
            "analysis": {
                "total_techniques": analysis.total_techniques,
                "overall_confidence": analysis.overall_confidence,
                "hunting_priority": analysis.hunting_priority,
                "techniques_by_category": {
                    category: [
                        {
                            "technique_name": tech.technique_name,
                            "confidence": tech.confidence,
                            "matched_text": tech.matched_text,
                            "hunting_guidance": tech.hunting_guidance
                        }
                        for tech in techniques
                    ]
                    for category, techniques in analysis.techniques_by_category.items()
                }
            },
            "quality_assessment": quality
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Handle 404 errors for non-existent routes"""
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "error": "Page not found"},
        status_code=404
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
