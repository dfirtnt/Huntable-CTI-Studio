"""
Manual scraping endpoint - FIXED VERSION.
"""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(tags=["Scrape"])


@router.post("/api/scrape-url")
async def api_scrape_url(request: dict):
    """Scrape one or more URLs manually - supports batch processing."""
    try:
        # Support both single URL (backward compatible) and batch URLs
        urls = request.get("urls")
        url = request.get("url")  # Single URL for backward compatibility

        if urls and isinstance(urls, list):
            # Batch processing mode
            if len(urls) == 0:
                raise HTTPException(status_code=400, detail="At least one URL is required")

            return await _scrape_urls_batch(urls, request.get("force_scrape", False))
        if url:
            # Single URL mode (backward compatible)
            return await _scrape_single_url(url, request.get("title"), request.get("force_scrape", False))
        raise HTTPException(status_code=400, detail="URL or URLs list is required")
    except httpx.RequestError as exc:
        logger.error("Request error: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc
    except UnicodeDecodeError as exc:
        logger.error("Unicode decode error: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to decode content: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Scrape error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def _scrape_single_url(url: str, title: str | None, force_scrape: bool) -> dict:
    """Scrape a single URL - extracted for reuse."""
    # Scrape content using the working approach from test endpoint
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"HTTP {exc.response.status_code} error fetching URL: {exc.response.status_text}",
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(exc)}")

        html_content = response.content.decode("utf-8", errors="replace")

        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup(["script", "style", "meta", "noscript", "iframe"]):
            script.decompose()
        content_text = soup.get_text(separator=" ", strip=True)

        # Conservative sanitization
        sanitized_content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
        sanitized_content = re.sub(r"\s+", " ", sanitized_content).strip()

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

    content_hash = hashlib.sha256(f"{extracted_title}\n{sanitized_content}".encode()).hexdigest()

    # Compute SimHash for near-duplicate detection
    from src.utils.simhash import compute_article_simhash

    simhash, simhash_bucket = compute_article_simhash(sanitized_content, extracted_title)

    # Store directly using sync manager (proven to work)
    from src.database.manager import DatabaseManager
    from src.database.models import ArticleTable, SourceTable
    from src.models.article import ArticleCreate

    sync_db_manager = DatabaseManager()

    # Get or create manual source (handles race conditions using PostgreSQL ON CONFLICT)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.exc import IntegrityError

    manual_source_id = None

    # First, try to get existing manual source
    with sync_db_manager.get_session() as session:
        manual_source = session.query(SourceTable).filter(SourceTable.identifier == "manual").first()
        if manual_source:
            manual_source_id = manual_source.id

    # If not found, create it using atomic INSERT ... ON CONFLICT
    if not manual_source_id:
        with sync_db_manager.get_session() as session:
            try:
                # Use PostgreSQL INSERT ... ON CONFLICT DO NOTHING for atomic upsert
                now = datetime.now()
                stmt = (
                    pg_insert(SourceTable)
                    .values(
                        identifier="manual",
                        name="Manual",
                        url="manual://scraped",
                        rss_url=None,
                        check_frequency=3600,
                        lookback_days=180,
                        active=False,
                        config={},
                        consecutive_failures=0,
                        total_articles=0,
                        average_response_time=0.0,
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["identifier"])
                )

                session.execute(stmt)
                session.commit()

                # Query in fresh session to get the source (handles race conditions)
                manual_source = session.query(SourceTable).filter(SourceTable.identifier == "manual").first()

                if manual_source:
                    manual_source_id = manual_source.id
                    logger.info(f"Created or found manual source with ID: {manual_source_id}")
                else:
                    # If still not found, query again in a completely fresh session
                    # (in case another transaction created it)
                    with sync_db_manager.get_session() as fresh_session:
                        manual_source = (
                            fresh_session.query(SourceTable).filter(SourceTable.identifier == "manual").first()
                        )
                        if manual_source:
                            manual_source_id = manual_source.id
                            logger.info(f"Found manual source in fresh session with ID: {manual_source_id}")
                        else:
                            raise HTTPException(
                                status_code=500, detail="Failed to create manual source - database constraint violation"
                            )

            except HTTPException:
                raise
            except IntegrityError as exc:
                # Handle both identifier conflicts and primary key conflicts (sequence issues)
                session.rollback()
                logger.warning(
                    f"IntegrityError creating manual source (likely race condition or sequence issue): {exc}"
                )
                # Query for existing source - it might have been created by another request
                with sync_db_manager.get_session() as retry_session:
                    manual_source = retry_session.query(SourceTable).filter(SourceTable.identifier == "manual").first()
                    if manual_source:
                        manual_source_id = manual_source.id
                        logger.info(f"Found manual source after IntegrityError with ID: {manual_source_id}")
                    else:
                        # If still not found, raise the original error
                        raise HTTPException(status_code=500, detail=f"Failed to get or create manual source: {exc}")
            except Exception as exc:
                session.rollback()
                logger.error(f"Error creating manual source: {exc}")
                # Try one more time to get existing source
                with sync_db_manager.get_session() as retry_session:
                    manual_source = retry_session.query(SourceTable).filter(SourceTable.identifier == "manual").first()
                    if manual_source:
                        manual_source_id = manual_source.id
                        logger.info(f"Found manual source after error with ID: {manual_source_id}")
                    else:
                        raise HTTPException(status_code=500, detail=f"Failed to get or create manual source: {exc}")

    if not manual_source_id:
        raise HTTPException(status_code=500, detail="Failed to get or create manual source")

    # Check for existing URL if force_scrape is False
    if not force_scrape:
        with sync_db_manager.get_session() as session:
            existing = (
                session.query(ArticleTable)
                .filter(ArticleTable.canonical_url == url, ArticleTable.archived == False)
                .first()
            )
            if existing:
                logger.info(f"Article already exists for URL: {url} (ID: {existing.id})")
                return {
                    "success": True,
                    "article_id": existing.id,
                    "article_title": existing.title,
                    "message": "Article already exists in database",
                    "existing": True,
                }

    article_data = ArticleCreate(
        source_id=manual_source_id,
        canonical_url=url,
        title=extracted_title,
        published_at=datetime.now(),
        content=sanitized_content,
        summary=sanitized_content[:500],
        authors=[],
        tags=[],
        article_metadata={
            "scraped_manually": True,
            "manual_scrape_timestamp": datetime.now().isoformat(),
            "source_url": url,
            "title": extracted_title,
            "word_count": len(sanitized_content.split()),
            "content_length": len(sanitized_content),
            "content_hash": content_hash,
            "simhash": simhash,
            "simhash_bucket": simhash_bucket,
            "processing_status": "completed",
            "manual_scrape": True,
        },
        content_hash=content_hash,
    )

    articles, errors = sync_db_manager.create_articles_bulk([article_data])
    if errors:
        error_msg = errors[0] if errors else "Unknown database error"
        # Check if it's a duplicate error
        if "Duplicate" in error_msg or "already exists" in error_msg.lower():
            raise HTTPException(status_code=409, detail=f"Duplicate article: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Database error: {error_msg}")
    if not articles:
        raise HTTPException(status_code=500, detail="No articles were created (may be duplicate content)")

    created_article = articles[0]

    # Calculate actual threat hunting score (similar to PDF upload)
    try:
        from src.database.async_manager import AsyncDatabaseManager
        from src.models.article import ArticleUpdate
        from src.utils.content import ThreatHuntingScorer

        threat_hunting_result = ThreatHuntingScorer.score_threat_hunting_content(extracted_title, sanitized_content)

        # Update article metadata with calculated score
        if not created_article.article_metadata:
            created_article.article_metadata = {}

        created_article.article_metadata.update(threat_hunting_result)

        # Save updated metadata
        async_db_manager = AsyncDatabaseManager()
        update_data = ArticleUpdate(article_metadata=created_article.article_metadata)
        await async_db_manager.update_article(created_article.id, update_data)

        score = threat_hunting_result.get("threat_hunting_score", 0)
        logger.info(
            "Successfully scraped and processed manual URL: %s -> Article ID: %s, Hunt Score: %s",
            url,
            created_article.id,
            score,
        )
    except Exception as exc:
        logger.warning("Failed to generate threat hunting score for manual scrape: %s", exc)
        logger.info(
            "Successfully scraped manual URL: %s -> Article ID: %s (score calculation failed)",
            url,
            created_article.id,
        )

    return {
        "success": True,
        "article_id": created_article.id,
        "article_title": created_article.title,
        "message": "Article scraped and processed successfully with threat hunting scoring",
    }


async def _scrape_urls_batch(urls: list, force_scrape: bool) -> dict:
    """Scrape multiple URLs in batch."""
    results = []
    successful = 0
    failed = 0

    for idx, url in enumerate(urls, 1):
        try:
            logger.info(f"Processing URL {idx}/{len(urls)}: {url}")
            result = await _scrape_single_url(url, None, force_scrape)
            results.append(
                {
                    "url": url,
                    "success": True,
                    "article_id": result.get("article_id"),
                    "article_title": result.get("article_title"),
                }
            )
            successful += 1
        except HTTPException as exc:
            # HTTPExceptions have status_code and detail
            error_msg = exc.detail if hasattr(exc, "detail") else str(exc)
            status_code = exc.status_code if hasattr(exc, "status_code") else 500
            logger.error(f"Failed to scrape URL {url}: [{status_code}] {error_msg}")
            results.append(
                {
                    "url": url,
                    "success": False,
                    "error": error_msg,
                    "status_code": status_code,
                }
            )
            failed += 1
        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"Failed to scrape URL {url}: {error_msg}", exc_info=True)
            results.append(
                {
                    "url": url,
                    "success": False,
                    "error": error_msg,
                }
            )
            failed += 1

    return {
        "success": True,
        "total": len(urls),
        "successful": successful,
        "failed": failed,
        "results": results,
        "message": f"Batch scraping completed: {successful} succeeded, {failed} failed",
    }
