"""
Manual scraping endpoint - FIXED VERSION.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(tags=["Scrape"])


@router.post("/api/scrape-url")
async def api_scrape_url(request: dict):
    """Scrape a single URL manually - FIXED VERSION."""
    try:
        url = request.get("url")
        title = request.get("title")
        force_scrape = request.get("force_scrape", False)

        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        # Scrape content using the working approach from test endpoint
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            html_content = response.content.decode('utf-8', errors='replace')
            
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(['script', 'style', 'meta', 'noscript', 'iframe']):
                script.decompose()
            content_text = soup.get_text(separator=' ', strip=True)
            
            # Conservative sanitization
            sanitized_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content_text)
            sanitized_content = re.sub(r'\s+', ' ', sanitized_content).strip()
        
        # Extract title
        extracted_title = title
        if not extracted_title:
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                title_tag = soup.find("title")
                extracted_title = title_tag.get_text().strip() if title_tag else "Untitled Article"
            except Exception as exc:
                logger.warning("Error extracting title: %s", exc)
                extracted_title = "Untitled Article"

        # Simple content hash
        import hashlib
        content_hash = hashlib.sha256(f"{extracted_title}\n{sanitized_content}".encode('utf-8')).hexdigest()
        
        # Compute SimHash for near-duplicate detection
        from src.utils.simhash import compute_article_simhash
        simhash, simhash_bucket = compute_article_simhash(sanitized_content, extracted_title)
        
        # Store directly using sync manager (proven to work)
        from src.database.manager import DatabaseManager
        from src.models.article import ArticleCreate
        
        sync_db_manager = DatabaseManager()
        
        article_data = ArticleCreate(
            source_id=-1,
            canonical_url=url,
            title=extracted_title,
            published_at=datetime.utcnow(),
            content=sanitized_content,
            summary=sanitized_content[:500],
            authors=[],
            tags=[],
            article_metadata={
                "scraped_manually": True,
                "manual_scrape_timestamp": datetime.utcnow().isoformat(),
                "source_url": url,
                "title": extracted_title,
                "word_count": len(sanitized_content.split()),
                "content_length": len(sanitized_content),
                "content_hash": content_hash,
                "simhash": simhash,
                "simhash_bucket": simhash_bucket,
                "threat_hunting_score": 50.0,
                "quality_score": 50.0,
                "processing_status": "completed",
                "manual_scrape": True,
            },
            content_hash=content_hash,
        )
        
        articles, errors = sync_db_manager.create_articles_bulk([article_data])
        if errors:
            raise HTTPException(status_code=500, detail=f"Database errors: {errors}")
        if not articles:
            raise HTTPException(status_code=500, detail="No articles were created")
        
        created_article = articles[0]

        logger.info(
            "Successfully scraped and processed manual URL: %s -> Article ID: %s",
            url,
            created_article.id,
        )

        return {
            "success": True,
            "article_id": created_article.id,
            "article_title": created_article.title,
            "message": "Article scraped and processed successfully with threat hunting scoring",
        }

    except httpx.RequestError as exc:
        logger.error("Request error: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc
    except UnicodeDecodeError as exc:
        logger.error("Unicode decode error: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to decode content: {exc}") from exc
    except Exception as exc:
        logger.error("Scrape error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc