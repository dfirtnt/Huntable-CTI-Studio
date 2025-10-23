"""
Manual scraping endpoint.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

from src.database.async_manager import async_db_manager
from src.utils.content import ContentCleaner, ThreatHuntingScorer
from src.web.dependencies import logger

router = APIRouter(tags=["Scrape"])


@router.post("/api/scrape-url")
async def api_scrape_url(request: dict):
    """Scrape a single URL manually."""
    try:
        url = request.get("url")
        title = request.get("title")
        force_scrape = request.get("force_scrape", False)

        if not url:
            raise HTTPException(status_code=400, detail="URL is required")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                raw_content = response.content
                content_encoding = response.headers.get("content-encoding", "").lower()

                try:
                    html_content = raw_content.decode("utf-8", errors="replace")
                except Exception:
                    try:
                        html_content = raw_content.decode("latin-1", errors="replace")
                    except Exception:
                        import chardet

                        detected = chardet.detect(raw_content)
                        encoding = detected.get("encoding", "utf-8")
                        html_content = raw_content.decode(encoding, errors="replace")

                if len(html_content) < 100 or not html_content.strip():
                    if content_encoding == "br":
                        import brotli

                        try:
                            html_content = brotli.decompress(raw_content).decode("utf-8", errors="replace")
                        except Exception:
                            html_content = raw_content.decode("utf-8", errors="replace")
                    elif content_encoding == "gzip":
                        import gzip

                        try:
                            html_content = gzip.decompress(raw_content).decode("utf-8", errors="replace")
                        except Exception:
                            html_content = raw_content.decode("utf-8", errors="replace")
                    else:
                        html_content = raw_content.decode("utf-8", errors="replace")

                html_content = html_content.replace("\x00", "").replace("\ufffd", "")
                html_content = "".join(c for c in html_content if ord(c) >= 32 or c in "\n\r\t")

            except httpx.RequestError as exc:
                raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}") from exc
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Failed to decode content: {exc}") from exc

        non_printable_in_html = sum(1 for c in html_content if ord(c) < 32 and c not in "\n\r\t")
        logger.info("Raw HTML validation: %s total chars, %s non-printable", len(html_content), non_printable_in_html)

        extracted_title = title
        if not extracted_title:
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                title_tag = soup.find("title")
                extracted_title = title_tag.get_text().strip() if title_tag else "Untitled Article"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error extracting title: %s", exc)
                extracted_title = "Untitled Article"

        try:
            soup = BeautifulSoup(html_content, "html.parser")
            for script in soup(["script", "style", "meta", "noscript", "iframe"]):
                script.decompose()
            content_text = soup.get_text(separator=" ", strip=True)

            sanitized_content = "".join(c for c in content_text if c.isprintable() or c in "\n\r\t")
            sanitized_content = re.sub(r"\s+", " ", sanitized_content).strip()

            if len(sanitized_content) > 10_000 and not force_scrape:
                sanitized_content = sanitized_content[:10_000] + "..."

        except Exception as exc:  # noqa: BLE001
            logger.error("Error extracting content: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to extract content: {exc}") from exc

        from src.utils.content import ContentCleaner

        content_hash = ContentCleaner.calculate_content_hash(extracted_title, sanitized_content)

        from src.models.article import ArticleCreate

        article_data = ArticleCreate(
            source_id=-1,
            url=url,
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
            },
            content_hash=content_hash,
        )

        threat_hunting_result = ThreatHuntingScorer.score_threat_hunting_content(
            article_data.title, article_data.content
        )
        article_data.article_metadata.update(threat_hunting_result)
        article_data.article_metadata.update(
            {
                "word_count": len(sanitized_content.split()),
                "quality_score": 50.0,
                "processing_status": "completed",
                "manual_scrape": True,
            }
        )

        try:
            created_article = await async_db_manager.create_article(article_data)

            if not created_article:
                logger.warning("Async database manager failed, trying direct insertion")
                from src.database.manager import DatabaseManager

                sync_db_manager = DatabaseManager()
                sanitized_content_sync = "".join(
                    c for c in sanitized_content if c.isprintable() or c in "\n\r\t"
                )
                sanitized_content_sync = re.sub(r"\s+", " ", sanitized_content_sync).strip()

                sanitized_article = ArticleCreate(
                    source_id=article_data.source_id,
                    canonical_url=article_data.canonical_url,
                    title=article_data.title,
                    published_at=article_data.published_at,
                    content=sanitized_content_sync,
                    summary=article_data.summary,
                    authors=article_data.authors,
                    tags=article_data.tags,
                    article_metadata=article_data.article_metadata,
                    content_hash=article_data.content_hash,
                )

                created_articles, errors = sync_db_manager.create_articles_bulk([sanitized_article])
                if errors:
                    raise HTTPException(status_code=500, detail=f"Sync database errors: {errors}")
                if not created_articles:
                    raise HTTPException(status_code=500, detail="No articles were created by sync manager")
                created_article = created_articles[0]

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
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Error saving processed manual article: %s", exc)
            raise HTTPException(status_code=500, detail=f"Failed to save article: {exc}") from exc

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("API scrape URL error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

