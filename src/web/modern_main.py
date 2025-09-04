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
from src.models.article import Article, ArticleUpdate
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
    threat_hunting_range: Optional[str] = None,
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
            "classification": classification or "",
            "threat_hunting_range": threat_hunting_range or ""
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
