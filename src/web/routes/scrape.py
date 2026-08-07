"""
Manual scraping endpoint - FIXED VERSION.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

from src.utils.input_validation import ValidationError, validate_url_for_scraping
from src.utils.langfuse_client import log_llm_completion, log_llm_error, trace_llm_call
from src.utils.safe_fetch import UnsafeURLError, safe_fetch_text
from src.web.dependencies import logger

router = APIRouter(tags=["Scrape"])

_VISION_PROMPT = (
    "Extract all visible text from this image exactly as it appears. "
    "Return only the extracted text with no commentary or formatting changes."
)


@router.post("/api/vision/extract")
async def api_vision_extract(request: dict):
    """Proxy image-to-text extraction to OpenAI or Anthropic using server-side API keys."""
    provider = request.get("provider", "openai")
    image_data_url = request.get("imageDataUrl", "")

    if not image_data_url:
        raise HTTPException(status_code=400, detail="imageDataUrl is required")
    if provider not in ("openai", "anthropic"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Resolve API key from DB settings with env fallback
    import asyncio
    import os

    from src.database.manager import DatabaseManager
    from src.database.models import AppSettingsTable

    _KEY_MAP = {
        "openai": ("WORKFLOW_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "anthropic": ("WORKFLOW_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    }

    def _resolve_api_key():
        db_manager = DatabaseManager()
        with db_manager.get_session() as session:
            for env_key in _KEY_MAP[provider]:
                row = session.query(AppSettingsTable).filter(AppSettingsTable.key == env_key).first()
                if row and row.value:
                    return row.value
        return None

    api_key = await asyncio.to_thread(_resolve_api_key)
    if not api_key:
        for env_key in _KEY_MAP[provider]:
            api_key = os.getenv(env_key)
            if api_key:
                break

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"No API key configured for provider '{provider}'. Add one in app settings.",
        )

    try:
        model = "gpt-4o" if provider == "openai" else "claude-sonnet-4-6"
        messages = [{"role": "user", "content": [{"type": "text", "text": _VISION_PROMPT}, {"type": "image"}]}]
        response_metadata: dict = {}
        with trace_llm_call(
            name="vision_extract",
            model=model,
            metadata={
                "agent_name": "vision_extract",
                "attempt": 1,
                "provider": provider,
                "messages": messages,
                "image_data_redacted": True,
                "image_data_length": len(image_data_url),
            },
        ) as generation:
            try:
                if provider == "openai":
                    result = await _call_openai_vision(image_data_url, api_key, response_metadata=response_metadata)
                else:
                    result = await _call_anthropic_vision(image_data_url, api_key, response_metadata=response_metadata)
            except Exception as error:
                log_llm_error(generation, error, metadata={"provider": provider})
                raise

            log_llm_completion(
                generation,
                input_messages=messages,
                output=result["text"],
                usage=response_metadata.get("usage"),
                metadata={"agent_name": "vision_extract", "attempt": 1, "provider": provider},
            )
            return result
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"{provider} API error: {exc.response.status_code}") from exc
    except Exception as exc:
        logger.error("Vision extract error (%s): %s", provider, exc)
        raise HTTPException(status_code=502, detail="Vision extraction failed") from exc


async def _call_openai_vision(image_data_url: str, api_key: str, response_metadata: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                            {"type": "text", "text": _VISION_PROMPT},
                        ],
                    }
                ],
            },
        )
        resp.raise_for_status()
        response_data = resp.json()
        if response_metadata is not None:
            response_metadata.update({"model": response_data.get("model"), "usage": response_data.get("usage")})
        return {"text": response_data["choices"][0]["message"]["content"].strip()}


async def _call_anthropic_vision(image_data_url: str, api_key: str, response_metadata: dict | None = None) -> dict:
    match = re.match(r"^data:(image/[a-z]+);base64,(.+)$", image_data_url)
    if not match:
        raise HTTPException(status_code=400, detail="imageDataUrl must be a base64 data URL")
    media_type, b64_data = match.group(1), match.group(2)
    # Validate it is valid base64 before forwarding
    base64.b64decode(b64_data, validate=True)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
                            {"type": "text", "text": _VISION_PROMPT},
                        ],
                    }
                ],
            },
        )
        resp.raise_for_status()
        response_data = resp.json()
        if response_metadata is not None:
            response_metadata.update({"model": response_data.get("model"), "usage": response_data.get("usage")})
        return {"text": response_data["content"][0]["text"].strip()}


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
            return await _scrape_single_url(
                url,
                request.get("title"),
                request.get("force_scrape", False),
                request.get("content"),  # Optional pre-scraped content (e.g., from browser extension with OCR)
            )
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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


async def _scrape_single_url(
    url: str,
    title: str | None,
    force_scrape: bool,
    pre_scraped_content: str | None = None,
) -> dict:
    """Scrape a single URL - extracted for reuse."""
    html_content = None

    try:
        validate_url_for_scraping(url)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {exc}") from exc

    # Use pre-scraped content if provided (e.g., from browser extension with OCR)
    if pre_scraped_content:
        sanitized_content = re.sub(r"\s+", " ", pre_scraped_content).strip()
        # Still need to fetch HTML for title extraction if not provided
        if not title:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
            }
            try:
                result = await safe_fetch_text(url, timeout=30.0, headers=headers)
                html_content = result.content.decode("utf-8", errors="replace")
            except UnsafeURLError as exc:
                # SSRF redirect/rebind must not be silently swallowed even on the
                # title-only fetch path -- refuse the request rather than risk it.
                raise HTTPException(status_code=400, detail=f"Invalid URL: {exc}") from exc
            except (httpx.HTTPStatusError, httpx.RequestError):
                # Genuine upstream failure: fall back to the pre-scraped content.
                pass
    else:
        # Scrape content using the working approach from test endpoint
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        }

        try:
            result = await safe_fetch_text(url, timeout=30.0, headers=headers)
        except UnsafeURLError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid URL: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"HTTP {exc.response.status_code} error fetching URL: {exc.response.reason_phrase}",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning(f"Failed to fetch URL {url}: {exc}")
            raise HTTPException(status_code=400, detail="Failed to fetch URL") from exc

        html_content = result.content.decode("utf-8", errors="replace")

        soup = BeautifulSoup(html_content, "html.parser")
        for script in soup(["script", "style", "meta", "noscript", "iframe"]):
            script.decompose()
        content_text = soup.get_text(separator=" ", strip=True)

        # Conservative sanitization
        sanitized_content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
        sanitized_content = re.sub(r"\s+", " ", sanitized_content).strip()

    # Extract title
    extracted_title = title
    if not extracted_title and html_content:
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            title_tag = soup.find("title")
            extracted_title = title_tag.get_text().strip() if title_tag else "Untitled Article"
        except Exception as exc:
            logger.warning("Error extracting title: %s", exc)
            extracted_title = "Untitled Article"
    elif not extracted_title:
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
                        raise HTTPException(
                            status_code=500, detail=f"Failed to get or create manual source: {exc}"
                        ) from exc
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
                        raise HTTPException(
                            status_code=500, detail=f"Failed to get or create manual source: {exc}"
                        ) from exc

    if not manual_source_id:
        raise HTTPException(status_code=500, detail="Failed to get or create manual source")

    # Check for existing URL if force_scrape is False
    if not force_scrape:
        with sync_db_manager.get_session() as session:
            existing = (
                session.query(ArticleTable).filter(ArticleTable.canonical_url == url, ~ArticleTable.archived).first()
            )
            if existing:
                # If OCR blocks are present in the new content, append any that are
                # not already stored — preserves the server-scraped text while adding
                # image context that only the browser extension can provide.
                if pre_scraped_content:
                    safe_content = pre_scraped_content[:50_000]
                    ocr_blocks = re.findall(r"\[Image OCR:[^\]]{0,2000}\]\n[^\[]{0,10000}", safe_content)
                    existing_content = existing.content or ""
                    new_blocks = [b for b in ocr_blocks if b.strip() not in existing_content]
                    if new_blocks:
                        from src.database.async_manager import AsyncDatabaseManager
                        from src.models.article import ArticleUpdate

                        appended = existing_content + "\n\n" + "\n\n".join(new_blocks).strip()
                        async_db_manager = AsyncDatabaseManager()
                        await async_db_manager.update_article(existing.id, ArticleUpdate(content=appended))
                        logger.info("Appended %d OCR block(s) to existing article %s", len(new_blocks), existing.id)
                        return {
                            "success": True,
                            "article_id": existing.id,
                            "article_title": existing.title,
                            "message": f"Article updated with {len(new_blocks)} OCR block(s)",
                            "existing": True,
                        }

                logger.info(f"Article already exists for URL: {url} (ID: {existing.id})")
                return {
                    "success": True,
                    "article_id": existing.id,
                    "article_title": existing.title,
                    "message": "Article already exists in database",
                    "existing": True,
                }

    # When force_scrape is True, still short-circuit on identical content hash.
    # The DB schema enforces uniqueness on content_hash, so attempting to insert
    # would raise an IntegrityError regardless. Return the existing article as a
    # success rather than an error so the caller gets a usable article_id.
    if force_scrape:
        with sync_db_manager.get_session() as session:
            existing = (
                session.query(ArticleTable)
                .filter(ArticleTable.content_hash == content_hash, ~ArticleTable.archived)
                .first()
            )
            if existing:
                logger.info(f"Force scrape: identical content already stored (ID: {existing.id}), returning existing")
                return {
                    "success": True,
                    "article_id": existing.id,
                    "article_title": existing.title,
                    "message": "Article with identical content already exists in database",
                    "existing": True,
                }

            # Also guard against canonical_url conflicts — a different content_hash
            # (e.g. OCR-enriched content) still cannot be INSERTed over an existing URL.
            # Apply the same OCR-append logic used in the force_scrape=False path.
            existing_by_url = (
                session.query(ArticleTable).filter(ArticleTable.canonical_url == url, ~ArticleTable.archived).first()
            )
            if existing_by_url:
                if pre_scraped_content:
                    safe_content = pre_scraped_content[:50_000]
                    ocr_blocks = re.findall(r"\[Image OCR:[^\]]{0,2000}\]\n[^\[]{0,10000}", safe_content)
                    existing_content = existing_by_url.content or ""
                    new_blocks = [b for b in ocr_blocks if b.strip() not in existing_content]
                    if new_blocks:
                        from src.database.async_manager import AsyncDatabaseManager
                        from src.models.article import ArticleUpdate

                        appended = existing_content + "\n\n" + "\n\n".join(new_blocks).strip()
                        async_db_manager = AsyncDatabaseManager()
                        await async_db_manager.update_article(existing_by_url.id, ArticleUpdate(content=appended))
                        logger.info(
                            "Force scrape: appended %d OCR block(s) to existing article %s",
                            len(new_blocks),
                            existing_by_url.id,
                        )
                        return {
                            "success": True,
                            "article_id": existing_by_url.id,
                            "article_title": existing_by_url.title,
                            "message": f"Article updated with {len(new_blocks)} OCR block(s)",
                            "existing": True,
                        }
                logger.info(f"Force scrape: URL already stored (ID: {existing_by_url.id}), returning existing")
                return {
                    "success": True,
                    "article_id": existing_by_url.id,
                    "article_title": existing_by_url.title,
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
        raise HTTPException(status_code=500, detail="Internal server error")
    if not articles:
        raise HTTPException(status_code=500, detail="No articles were created (may be duplicate content)")

    created_article = articles[0]

    # Calculate actual threat hunting score (similar to PDF upload)
    try:
        from src.database.async_manager import AsyncDatabaseManager
        from src.models.article import ArticleUpdate
        from src.utils.content import ThreatHuntingScorer
        from src.utils.keyword_registry import build_os_classification

        threat_hunting_result = ThreatHuntingScorer.score_threat_hunting_content(extracted_title, sanitized_content)

        # Update article metadata with calculated score
        if not created_article.article_metadata:
            created_article.article_metadata = {}

        created_article.article_metadata.update(threat_hunting_result)
        # OS classification at scoring time (Phase 2)
        created_article.article_metadata["os_classification"] = build_os_classification(sanitized_content)

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
            # HTTPExceptions have status_code and detail; we log full detail but
            # only return a generic message to avoid leaking exception data
            status_code = exc.status_code if hasattr(exc, "status_code") else 500
            internal_detail = exc.detail if hasattr(exc, "detail") else str(exc)
            logger.error(f"Failed to scrape URL {url}: [{status_code}] {internal_detail}")
            results.append(
                {
                    "url": url,
                    "success": False,
                    "error": "Scrape failed",
                    "status_code": status_code,
                }
            )
            failed += 1
        except Exception as exc:
            logger.error(f"Failed to scrape URL {url}: {exc}", exc_info=True)
            results.append(
                {
                    "url": url,
                    "success": False,
                    "error": "Scrape failed",
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
