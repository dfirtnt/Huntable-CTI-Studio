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
from src.utils.chatbot import ThreatIntelligenceChatbot

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

# Sources management
@app.get("/sources", response_class=HTMLResponse)
async def sources_list(request: Request):
    """Sources management page."""
    try:
        sources = await async_db_manager.list_sources()
        return templates.TemplateResponse(
            "sources.html",
            {"request": request, "sources": sources}
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
    quality_min: Optional[str] = None,
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
        
        # Search filter
        if search:
            search_lower = search.lower()
            filtered_articles = [
                article for article in filtered_articles
                if (article.title and search_lower in article.title.lower()) or
                   (article.content and search_lower in article.content.lower())
            ]
        
        # Source filter
        if source and source.isdigit():
            source_id = int(source)
            filtered_articles = [
                article for article in filtered_articles
                if article.source_id == source_id
            ]
        
        # Quality filter
        if quality_min and quality_min.isdigit():
            min_quality = float(quality_min)
            filtered_articles = [
                article for article in filtered_articles
                if article.quality_score is not None and article.quality_score >= min_quality
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
            "quality_min": quality_min or ""
        }
        
        return templates.TemplateResponse(
            "articles.html",
            {
                "request": request,
                "articles": articles,
                "sources": sources,
                "source_lookup": source_lookup,
                "pagination": pagination,
                "filters": filters
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
        
                # Implement enhanced TTP analysis with advanced quality assessment
        from src.utils.enhanced_ttp_extractor import EnhancedThreatHuntingDetector
        from src.utils.advanced_quality_assessor import AdvancedQualityAssessor
        
        if article.content and len(article.content) > 100:
            try:
                hunting_detector = EnhancedThreatHuntingDetector()
                quality_assessor = AdvancedQualityAssessor()
                
                # Safely concatenate title and content
                title = str(article.title) if article.title else ""
                content = str(article.content) if article.content else ""
                full_text = f"{title} {content}".strip()
                
                # Enhanced TTP analysis
                analysis = hunting_detector.extract_enhanced_techniques(full_text)
                
                # Enhanced TTP analysis data
                ttp_analysis = {
                    "total_techniques": analysis.total_techniques,
                    "overall_confidence": analysis.overall_confidence,
                    "hunting_priority": analysis.hunting_priority,
                    "techniques_by_category": {
                        category: [
                            {
                                "technique_name": tech.technique_name,
                                "confidence": tech.confidence,
                                "hunting_guidance": tech.hunting_guidance,
                                "matched_text": tech.matched_text
                            } for tech in techniques
                        ] for category, techniques in analysis.techniques_by_category.items()
                    },
                    "threat_actors": analysis.threat_actors,
                    "malware_families": analysis.malware_families,
                    "attack_vectors": analysis.attack_vectors
                }
                
                # TTP quality score
                ttp_quality_analysis = hunting_detector.calculate_ttp_quality_score(content)
                numeric_values = [v for v in ttp_quality_analysis.values() if isinstance(v, (int, float))]
                ttp_score = sum(numeric_values) if numeric_values else 0
                
                # NEW: Advanced quality assessment
                quality_assessment = quality_assessor.assess_content_quality(content, {
                    'total_techniques': analysis.total_techniques,
                    'techniques_by_category': analysis.techniques_by_category
                })
                
                # Enhanced quality data combining TTP and advanced assessment
                quality_data = {
                    "ttp_score": ttp_score,
                    "quality_score": quality_assessment.overall_quality_score,
                    "combined_score": (ttp_score + quality_assessment.overall_quality_score) / 2,
                    "quality_level": quality_assessment.quality_level,
                    # New assessment attributes
                    "artifact_coverage_score": quality_assessment.artifact_coverage_score,
                    "technical_depth_score": quality_assessment.technical_depth_score,
                    "actionable_intelligence_score": quality_assessment.actionable_intelligence_score,
                    "threat_context_score": quality_assessment.threat_context_score,
                    "detection_quality_score": quality_assessment.detection_quality_score,
                    "classification": quality_assessment.quality_level,
                    "hunting_priority": quality_assessment.hunting_priority,
                    "hunting_confidence": quality_assessment.hunting_confidence,
                    "recommendations": quality_assessment.recommendations,
                    "max_possible": 100,
                    "sigma_rules_present": ttp_quality_analysis.get('sigma_rules_present', 0),
                    "mitre_attack_mapping": ttp_quality_analysis.get('mitre_attack_mapping', 0),
                    "iocs_present": ttp_quality_analysis.get('iocs_present', 0)
                }
                
            except Exception as e:
                logger.warning(f"TTP analysis failed for article {article.id}: {e}")
                ttp_analysis = {
                    "total_techniques": 0,
                    "overall_confidence": 0.0,
                    "hunting_priority": "Analysis Failed",
                    "techniques_by_category": {}
                }
                quality_data = {
                    "total_score": 0,
                    "max_possible": 75,
                    "quality_level": "Analysis Failed",
                    "sigma_rules_present": 0,
                    "mitre_attack_mapping": 0,
                    "iocs_present": 0,
                    "recommendation": "TTP analysis encountered an error"
                }
        else:
            ttp_analysis = {
                "total_techniques": 0,
                "overall_confidence": 0.0,
                "hunting_priority": "Insufficient Content",
                "techniques_by_category": {}
            }
            quality_data = {
                "total_score": 0,
                "max_possible": 75,
                "quality_level": "Insufficient Content",
                "sigma_rules_present": 0,
                "mitre_attack_mapping": 0,
                "iocs_present": 0,
                "recommendation": "Article content too short for meaningful analysis"
            }
        
        return templates.TemplateResponse(
            "article_detail.html",
            {
                "request": request, 
                "article": article, 
                "source": source,
                "ttp_analysis": ttp_analysis,
                "quality_data": quality_data
            }
        )
    except Exception as e:
        logger.error(f"Article detail error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

# TTP Analysis page
@app.get("/analysis", response_class=HTMLResponse)
async def ttp_analysis(request: Request):
    """TTP Analysis page with enhanced LLM quality assessment."""
    try:
        stats = await async_db_manager.get_database_stats()
        articles = await async_db_manager.list_articles(limit=20)
        
        # Import enhanced TTP detector and advanced quality assessor
        from src.utils.enhanced_ttp_extractor import EnhancedThreatHuntingDetector
        from src.utils.advanced_quality_assessor import AdvancedQualityAssessor
        
        hunting_detector = EnhancedThreatHuntingDetector()
        quality_assessor = AdvancedQualityAssessor()
        
        # Analyze articles for TTP content and quality
        total_techniques_detected = 0
        high_priority_articles = 0
        ttp_quality_scores = []
        llm_quality_scores = []
        technique_categories = defaultdict(int)
        recent_analyses = []
        
        # Quality distribution tracking
        quality_distribution = {"Excellent": 0, "Good": 0, "Fair": 0, "Limited": 0}
        tactical_distribution = {"Tactical": 0, "Strategic": 0, "Hybrid": 0}
        
        for article in articles:
            if article.content and len(article.content) > 100:
                try:
                    # Safely concatenate title and content
                    title = str(article.title) if article.title else ""
                    content = str(article.content) if article.content else ""
                    full_text = f"{title} {content}".strip()
                    
                    # Run enhanced TTP analysis
                    ttp_analysis = hunting_detector.extract_enhanced_techniques(full_text)
                    
                    total_techniques_detected += ttp_analysis.total_techniques
                    
                    if ttp_analysis.hunting_priority in ["High", "Medium"]:
                        high_priority_articles += 1
                    
                    # Count technique categories
                    for category, techniques in ttp_analysis.techniques_by_category.items():
                        technique_categories[category] += len(techniques)
                    
                    # Calculate TTP quality score (existing functionality)
                    ttp_quality_analysis = hunting_detector.calculate_ttp_quality_score(content)
                    numeric_values = [v for v in ttp_quality_analysis.values() if isinstance(v, (int, float))]
                    ttp_score = sum(numeric_values) if numeric_values else 0
                    # Normalize TTP score to 0-100 range
                    ttp_score = min(ttp_score, 100)
                    ttp_quality_scores.append(ttp_score)
                    
                    # NEW: Run advanced quality assessment
                    quality_assessment = quality_assessor.assess_content_quality(content, {
                        'total_techniques': ttp_analysis.total_techniques,
                        'techniques_by_category': ttp_analysis.techniques_by_category
                    })
                    
                    llm_quality_scores.append(quality_assessment.overall_quality_score)
                    
                    # Track quality distributions with proper mapping
                    # Map new quality levels to expected template levels
                    quality_level_mapping = {
                        "Critical": "Excellent",
                        "High": "Good", 
                        "Medium": "Fair",
                        "Low": "Limited"
                    }
                    mapped_quality_level = quality_level_mapping.get(quality_assessment.quality_level, "Limited")
                    quality_distribution[mapped_quality_level] += 1
                    
                    # Map hunting priority to tactical distribution
                    priority_mapping = {
                        "Critical": "Tactical",
                        "High": "Tactical",
                        "Medium": "Hybrid", 
                        "Low": "Strategic"
                    }
                    mapped_priority = priority_mapping.get(quality_assessment.hunting_priority, "Strategic")
                    tactical_distribution[mapped_priority] += 1
                    
                    # Add to recent analyses (top 5) with enhanced data
                    if len(recent_analyses) < 5:
                        recent_analyses.append({
                            "article": article,
                            "ttp_analysis": ttp_analysis,
                            "ttp_quality_score": ttp_score,
                            "quality_assessment": quality_assessment,
                            "combined_score": (ttp_score + quality_assessment.overall_quality_score) / 2
                        })
                    
                except Exception as e:
                    logger.warning(f"Analysis failed for article {article.id}: {e}")
                    continue
        
        # Calculate summary statistics
        avg_ttp_quality = sum(ttp_quality_scores) / len(ttp_quality_scores) if ttp_quality_scores else 0.0
        avg_llm_quality = sum(llm_quality_scores) / len(llm_quality_scores) if llm_quality_scores else 0.0
        
        # Enhanced analysis summary
        analysis_summary = {
            "total_techniques_detected": total_techniques_detected,
            "high_priority_articles": high_priority_articles,
            "mitre_coverage": len([cat for cat in technique_categories if "MITRE" in cat.upper()]),
            "recent_analysis": recent_analyses,
            "quality_distribution": quality_distribution,
            "tactical_distribution": tactical_distribution
        }
        
        # Enhanced quality stats
        quality_stats = {
            "ttp_average_score": avg_ttp_quality,
            "llm_average_score": avg_llm_quality,
            "combined_average_score": (avg_ttp_quality + avg_llm_quality) / 2,
            "total_analyzed": len(llm_quality_scores),
            "quality_distribution": quality_distribution,
            "tactical_distribution": tactical_distribution
        }
        
        return templates.TemplateResponse(
            "analysis.html",
            {
                "request": request,
                "stats": stats,
                "articles": articles,
                "analysis_summary": analysis_summary,
                "quality_stats": quality_stats,
                "analyses": recent_analyses
            }
        )
    except Exception as e:
        logger.error(f"Analysis page error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

@app.get("/api/articles")
async def api_articles_list(limit: Optional[int] = 100):
    """API endpoint for listing articles."""
    try:
        articles = await async_db_manager.list_articles(limit=limit)
        return {"articles": [article.dict() for article in articles]}
    except Exception as e:
        logger.error(f"API articles list error: {e}")
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

# Chatbot routes
@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface page."""
    try:
        return templates.TemplateResponse(
            "chat.html",
            {"request": request}
        )
    except Exception as e:
        logger.error(f"Chat page error: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)},
            status_code=500
        )

@app.post("/api/chat")
async def chat_api(request: Request):
    """API endpoint for chatbot interactions."""
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Initialize chatbot
        chatbot = ThreatIntelligenceChatbot(async_db_manager)
        
        # Get response
        response = await chatbot.chat(user_message)
        
        return {
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "sources": chatbot.get_conversation_history()[-1].get("metadata", {}).get("sources", [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/history")
async def chat_history():
    """Get chat conversation history."""
    try:
        chatbot = ThreatIntelligenceChatbot(async_db_manager)
        return {"history": chatbot.get_conversation_history()}
    except Exception as e:
        logger.error(f"Chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/clear")
async def clear_chat_history():
    """Clear chat conversation history."""
    try:
        chatbot = ThreatIntelligenceChatbot(async_db_manager)
        chatbot.clear_history()
        return {"message": "Chat history cleared"}
    except Exception as e:
        logger.error(f"Clear chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/train")
async def train_chatbot():
    """Train the chatbot on blog content."""
    try:
        chatbot = ThreatIntelligenceChatbot(async_db_manager)
        result = await chatbot.train_on_blog_content()
        return {"message": result}
    except Exception as e:
        logger.error(f"Train chatbot error: {e}")
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
