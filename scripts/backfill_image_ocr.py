"""One-shot backfill of server-side OCR for historical articles.
See docs/superpowers/specs/2026-06-15-image-ocr-ingest-design.md §4.6."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, ContentHashTable
from src.services.vision_ocr_service import (
    OcrConfig,
    OcrStatus,
    _build_safe_client,
    _parse_existing_ocr_urls,
    ocr_article_images,
    resolve_ocr_config,
)
from src.utils.content import ContentCleaner
from src.utils.simhash import compute_article_simhash

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SELECT SQL (defensive image_count cast per §4.6)
# ---------------------------------------------------------------------------

SELECT_SQL = """
SELECT id, source_id, canonical_url, title, content, content_hash, article_metadata
FROM articles
WHERE (article_metadata->>'ocr_status' IS NULL
       OR article_metadata->>'ocr_status' IN ('skipped_disabled','failed_timeout','failed_error'))
  AND ( article_metadata->'original_img_urls' IS NOT NULL
        OR (CASE WHEN article_metadata->>'image_count' ~ '^[0-9]+$'
                 THEN (article_metadata->>'image_count')::int ELSE 0 END) > 0 )
  AND (:source_id IS NULL OR source_id = :source_id)
ORDER BY id
LIMIT :max_articles
"""


# ---------------------------------------------------------------------------
# Pure helpers (testable without DB or network)
# ---------------------------------------------------------------------------


def detect_hash_basis(stored_hash: str, title: str, content: str) -> str | None:
    """Recover the row's content_hash basis by comparison against the CURRENT content.

    This is retry-stable: detection is by stored-hash comparison, NEVER by
    content_hashes-row existence (the upsert below creates such a row for async
    articles, which would flip the discriminator on a retry).

    Returns 'async_raw' | 'sync' | None (unknown / content changed out-of-band).
    """
    if stored_hash == hashlib.sha256(content.encode("utf-8")).hexdigest():
        return "async_raw"
    if stored_hash == ContentCleaner.calculate_content_hash(title, content):
        return "sync"
    return None


def recompute_hash(basis: str, title: str, content: str) -> str:
    """Recompute content_hash on the same basis the row already uses."""
    if basis == "async_raw":
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ContentCleaner.calculate_content_hash(title, content)


def append_ocr_plaintext(content: str, blocks: list[tuple[str, str]]) -> str:
    """Append (marker, ocr_text) pairs as plain text, skipping URLs already present.

    Backfill persisted content is already cleaned plain text (not HTML), so we
    append plain text rather than injecting HTML nodes.

    Deduplication is by URL extracted from the marker header. Existing markers
    in *content* (from a previous run) are detected via _parse_existing_ocr_urls.
    """
    done = _parse_existing_ocr_urls(content)
    add: list[str] = []
    for marker, ocr_text in blocks:
        m = re.search(r"\[Image OCR:\s*([^\]]+)\]", marker)
        url = m.group(1).strip() if m else None
        if url and url in done:
            continue
        add.append(f"{marker}\n{ocr_text}")
    if not add:
        return content
    return (content.rstrip() + "\n\n" + "\n".join(add)).strip()


# ---------------------------------------------------------------------------
# Per-article transform: factored out so it can be unit-tested without DB
# ---------------------------------------------------------------------------


@dataclass
class ArticleUpdateIntent:
    """All fields that main() would write in one transaction. Testable without DB."""

    new_content: str
    new_content_hash: str
    new_word_count: int
    new_simhash: int
    new_simhash_bucket: int
    new_metadata: dict
    upsert_content_hash: bool  # True = insert/update content_hashes row
    basis: str
    skipped: bool = False
    skip_reason: str = ""


def compute_article_update(
    *,
    article_id: int,
    title: str,
    content: str,
    stored_content_hash: str,
    article_metadata: dict,
    ocr_blocks: list[tuple[str, str]],
    ocr_status: OcrStatus,
    original_img_urls: list[str],
    processed_img_urls: list[str],
    error_counts: dict,
    existing_hash_basis: str | None,
    collision_content_hash: str | None,  # stored articles.content_hash that would collide
) -> ArticleUpdateIntent:
    """Pure function: given a row + OCR result, return the intended DB write (or a skip).

    Arguments:
        existing_hash_basis: value already stored in metadata['ocr_content_hash_basis']
            from a prior run; None if first backfill.
        collision_content_hash: if the caller already detected that the new_hash would
            collide with another row, pass that hash here; otherwise None.
    """
    # Recover/confirm basis
    basis = existing_hash_basis or detect_hash_basis(stored_content_hash, title, content)
    if basis is None:
        return ArticleUpdateIntent(
            new_content=content,
            new_content_hash=stored_content_hash,
            new_word_count=len(content.split()),
            new_simhash=0,
            new_simhash_bucket=0,
            new_metadata=article_metadata,
            upsert_content_hash=False,
            basis="",
            skipped=True,
            skip_reason=f"article {article_id}: content_hash basis unknown (content changed out-of-band?)",
        )

    new_content = append_ocr_plaintext(content, ocr_blocks)
    new_hash = recompute_hash(basis, title, new_content)

    if collision_content_hash is not None:
        return ArticleUpdateIntent(
            new_content=content,
            new_content_hash=stored_content_hash,
            new_word_count=len(content.split()),
            new_simhash=0,
            new_simhash_bucket=0,
            new_metadata=article_metadata,
            upsert_content_hash=False,
            basis=basis,
            skipped=True,
            skip_reason=(
                f"article {article_id}: new content_hash {new_hash[:8]}… collides with "
                f"another row; skipping to avoid corruption"
            ),
        )

    new_simhash, new_simhash_bucket = compute_article_simhash(new_content, title)
    new_word_count = len(new_content.split())

    # Marker count = all [Image OCR:] blocks now in content
    total_marker_count = len(_parse_existing_ocr_urls(new_content))

    new_metadata = dict(article_metadata) | {
        "ocr_status": ocr_status.value,
        "ocr_image_count": total_marker_count,
        "ocr_ran_at": datetime.now(UTC).isoformat(),
        "original_img_urls": original_img_urls,
        "ocr_processed_img_urls": processed_img_urls,
        "ocr_error_counts": error_counts,
        "ocr_content_hash_basis": basis,
        "word_count": new_word_count,
        "content_length": len(new_content),
    }

    return ArticleUpdateIntent(
        new_content=new_content,
        new_content_hash=new_hash,
        new_word_count=new_word_count,
        new_simhash=new_simhash,
        new_simhash_bucket=new_simhash_bucket,
        new_metadata=new_metadata,
        upsert_content_hash=True,
        basis=basis,
    )


# ---------------------------------------------------------------------------
# Async OCR fetch (driven from sync main via asyncio.run)
# ---------------------------------------------------------------------------


async def _ocr_url_list(
    url_list: list[str],
    article_url: str,
    config: OcrConfig,
    already_processed: set[str],
    existing_status: str | None,
) -> tuple[list[tuple[str, str]], list[str], list[str], OcrStatus, dict]:
    """Fetch + OCR a list of image URLs.  Returns (blocks, original_urls, processed_urls,
    status, error_counts)."""
    from bs4 import BeautifulSoup

    # Build a synthetic soup containing only the candidate <img> tags so we can
    # re-use ocr_article_images (which calls _filter_images on a soup root).
    soup = BeautifulSoup("", "lxml")
    body = soup.new_tag("body")
    soup.append(body)
    for u in url_list:
        img = soup.new_tag("img", src=u)
        body.append(img)

    async with _build_safe_client(config) as client:
        outcome = await ocr_article_images(
            client,
            body,
            article_url,
            config,
            already_processed=already_processed,
            existing_status=existing_status,
        )
    return (
        outcome.blocks,
        outcome.original_img_urls,
        outcome.processed_img_urls,
        outcome.status,
        outcome.error_counts,
    )


async def _ocr_refetch(
    canonical_url: str,
    config: OcrConfig,
    already_processed: set[str],
    existing_status: str | None,
) -> tuple[list[tuple[str, str]], list[str], list[str], OcrStatus, dict]:
    """Refetch canonical_url, parse, filter images, OCR.  Returns same shape as
    _ocr_url_list."""

    from bs4 import BeautifulSoup

    async with _build_safe_client(config) as client:
        try:
            resp = await client.get(canonical_url, follow_redirects=True)
            html = resp.text
        except Exception as exc:
            logger.warning("backfill: failed to refetch %s: %s", canonical_url, exc)
            return [], [], [], OcrStatus.failed_error, {}

    soup = BeautifulSoup(html, "lxml")
    ContentCleaner.prepare_soup_for_selection(soup)
    target = ContentCleaner.find_main_content_node(soup) or soup.body or soup

    outcome = await ocr_article_images(
        client,
        target,
        canonical_url,
        config,
        already_processed=already_processed,
        existing_status=existing_status,
    )
    return (
        outcome.blocks,
        outcome.original_img_urls,
        outcome.processed_img_urls,
        outcome.status,
        outcome.error_counts,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _get_source_stub(source_id: int, db: DatabaseManager) -> Any:
    """Return a minimal duck-typed object with .config for resolve_ocr_config."""

    class _SourceStub:
        def __init__(self, config_dict):
            self.config = config_dict

    with db.get_session() as session:
        from src.database.models import SourceTable

        row = session.query(SourceTable).filter(SourceTable.id == source_id).first()
        if row is None:
            return _SourceStub({})
        return _SourceStub(row.config or {})


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    ap = argparse.ArgumentParser(
        description="Backfill server-side OCR for historical articles."
    )
    ap.add_argument(
        "--max-articles", type=int, default=100,
        help="Maximum number of articles to process (default: 100).",
    )
    ap.add_argument(
        "--source-id", type=int, default=None,
        help="Restrict to a single source ID.",
    )
    ap.add_argument(
        "--allow-refetch", action="store_true",
        help="If original_img_urls absent, re-fetch canonical_url to discover images.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Log intended changes without writing to the database.",
    )
    args = ap.parse_args()

    db = DatabaseManager()

    # -----------------------------------------------------------------------
    # 1. SELECT candidate rows (read-only)
    # -----------------------------------------------------------------------
    with db.get_session() as session:
        rows = session.execute(
            text(SELECT_SQL),
            {"source_id": args.source_id, "max_articles": args.max_articles},
        ).fetchall()

    if not rows:
        logger.info("backfill: no candidate articles found")
        return

    logger.info("backfill: %d candidate articles", len(rows))

    skipped = processed = 0

    for row in rows:
        article_id = row.id
        source_id = row.source_id
        canonical_url = row.canonical_url
        title = row.title or ""
        content = row.content or ""
        stored_hash = row.content_hash or ""
        meta: dict = dict(row.article_metadata or {})

        # -----------------------------------------------------------------------
        # 2. Resolve OCR config for this source
        # -----------------------------------------------------------------------
        source_stub = _get_source_stub(source_id, db)
        ocr_config = resolve_ocr_config(source_stub)
        if ocr_config is None:
            logger.info(
                "backfill: article %d source %d: OCR disabled; skipping", article_id, source_id
            )
            skipped += 1
            continue

        # -----------------------------------------------------------------------
        # 3. Determine image URL candidates
        # -----------------------------------------------------------------------
        already_processed: set[str] = set(meta.get("ocr_processed_img_urls") or [])
        already_processed |= _parse_existing_ocr_urls(content)
        existing_status: str | None = meta.get("ocr_status")
        existing_hash_basis: str | None = meta.get("ocr_content_hash_basis")

        original_img_urls: list[str] = meta.get("original_img_urls") or []

        if original_img_urls:
            # Preferred path: OCR the stored candidate list directly
            blocks, orig_urls, proc_urls, status, err_counts = asyncio.run(
                _ocr_url_list(
                    original_img_urls,
                    canonical_url,
                    ocr_config,
                    already_processed,
                    existing_status,
                )
            )
        elif args.allow_refetch:
            logger.info(
                "backfill: article %d: no stored image URLs; re-fetching %s",
                article_id, canonical_url,
            )
            blocks, orig_urls, proc_urls, status, err_counts = asyncio.run(
                _ocr_refetch(canonical_url, ocr_config, already_processed, existing_status)
            )
        else:
            logger.info(
                "backfill: article %d: no stored image URLs and --allow-refetch not set; skipping",
                article_id,
            )
            skipped += 1
            continue

        # -----------------------------------------------------------------------
        # 4. Detect hash collision BEFORE computing the update intent
        # -----------------------------------------------------------------------
        # We only need to check for collision if there are new blocks to append.
        collision_hash: str | None = None
        if blocks:
            # Determine the basis first (needed for new hash preview)
            basis_preview = existing_hash_basis or detect_hash_basis(stored_hash, title, content)
            if basis_preview is not None:
                new_content_preview = append_ocr_plaintext(content, blocks)
                new_hash_preview = recompute_hash(basis_preview, title, new_content_preview)
                if new_hash_preview != stored_hash:
                    with db.get_session() as session:
                        # Check both articles.content_hash and content_hashes table
                        colliding_article = (
                            session.query(ArticleTable)
                            .filter(ArticleTable.content_hash == new_hash_preview)
                            .filter(ArticleTable.id != article_id)
                            .first()
                        )
                        colliding_ch = (
                            session.query(ContentHashTable)
                            .filter(ContentHashTable.content_hash == new_hash_preview)
                            .filter(ContentHashTable.article_id != article_id)
                            .first()
                        ) if colliding_article is None else colliding_article
                    if colliding_article is not None or (
                        colliding_ch is not None and colliding_ch is not colliding_article
                    ):
                        collision_hash = new_hash_preview

        # -----------------------------------------------------------------------
        # 5. Compute update intent (pure, testable)
        # -----------------------------------------------------------------------
        intent = compute_article_update(
            article_id=article_id,
            title=title,
            content=content,
            stored_content_hash=stored_hash,
            article_metadata=meta,
            ocr_blocks=blocks,
            ocr_status=status,
            original_img_urls=orig_urls,
            processed_img_urls=list(already_processed | set(proc_urls)),
            error_counts=err_counts,
            existing_hash_basis=existing_hash_basis,
            collision_content_hash=collision_hash,
        )

        if intent.skipped:
            logger.warning("backfill: %s", intent.skip_reason)
            skipped += 1
            continue

        if args.dry_run:
            logger.info(
                "backfill [DRY-RUN] article %d: would append %d block(s); "
                "basis=%s new_hash=%s… word_count=%d->%d",
                article_id, len(blocks), intent.basis,
                intent.new_content_hash[:8], len(content.split()), intent.new_word_count,
            )
            processed += 1
            continue

        # -----------------------------------------------------------------------
        # 6. Write in ONE transaction per article
        # -----------------------------------------------------------------------
        try:
            with db.get_session() as session:
                # Update the article row
                db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).one()
                db_article.content = intent.new_content
                db_article.content_hash = intent.new_content_hash
                db_article.word_count = intent.new_word_count
                db_article.simhash = intent.new_simhash
                db_article.simhash_bucket = intent.new_simhash_bucket
                db_article.article_metadata = intent.new_metadata

                # UPSERT content_hashes (insert-if-absent, update-if-present)
                # Async-ingested rows have NO row; sync-ingested rows have one.
                # Do NOT touch simhash_buckets — no ingest path writes it.
                existing_ch = (
                    session.query(ContentHashTable)
                    .filter(ContentHashTable.article_id == article_id)
                    .first()
                )
                if existing_ch is None:
                    session.add(
                        ContentHashTable(
                            content_hash=intent.new_content_hash,
                            article_id=article_id,
                        )
                    )
                else:
                    existing_ch.content_hash = intent.new_content_hash

                session.commit()

            logger.info(
                "backfill: article %d OK — blocks=%d basis=%s hash=%s…",
                article_id, len(blocks), intent.basis, intent.new_content_hash[:8],
            )
            processed += 1

        except Exception as exc:
            logger.error("backfill: article %d FAILED: %s", article_id, exc)
            skipped += 1

    logger.info(
        "backfill complete: processed=%d skipped/errors=%d", processed, skipped
    )


if __name__ == "__main__":
    main()
