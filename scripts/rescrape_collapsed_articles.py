"""One-shot backfill: re-scrape articles whose stored content has no newlines.

The early scrape pipeline used soup.get_text(strip=True) which collapses all
block-level newlines into spaces. ContentCleaner.clean_html() was later fixed
to preserve newlines via normalize_whitespace_keep_newlines(). This script
retroactively fetches the raw HTML for collapsed rows and re-processes it
through the fixed path.

HARD CONSTRAINT: eval-pinned URLs (config/eval_articles.yaml and every
config/eval_articles_data/*/articles.json) are EXCLUDED and never touched.
Eval doctrine is forward-only; ground truth is never changed to chase a
pipeline bug.

Usage:
    uv run --frozen scripts/rescrape_collapsed_articles.py --dry-run
    uv run --frozen scripts/rescrape_collapsed_articles.py --limit 50
    uv run --frozen scripts/rescrape_collapsed_articles.py            # all

Options:
    --dry-run        Print which articles would be updated; make no DB writes.
    --limit N        Stop after processing N articles (default: unlimited).
    --delay SECS     Seconds to sleep between fetches (default: 1.5).
    --min-length N   Minimum content length to consider collapsed (default: 5000).
    --source-id N    Restrict to a single source_id (optional).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib
import sys
import time
from datetime import datetime
from typing import Any

import httpx
import yaml
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Path setup — run from repo root via `uv run --frozen scripts/<this>.py`
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.database.manager import DatabaseManager
from src.utils.content import ContentCleaner
from src.utils.simhash import compute_article_simhash

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Eval URL set — everything in this set is NEVER touched
# ---------------------------------------------------------------------------

EVAL_YAML = ROOT / "config" / "eval_articles.yaml"
EVAL_DATA_DIR = ROOT / "config" / "eval_articles_data"


def _load_eval_urls() -> frozenset[str]:
    urls: set[str] = set()

    if EVAL_YAML.exists():
        with open(EVAL_YAML) as fh:
            data = yaml.safe_load(fh) or {}
        for subagent_entries in (data.get("subagents") or {}).values():
            for entry in subagent_entries or []:
                if isinstance(entry, dict) and "url" in entry:
                    urls.add(entry["url"].rstrip("/"))

    import json

    for articles_json in EVAL_DATA_DIR.glob("*/articles.json"):
        try:
            rows = json.loads(articles_json.read_text())
            for row in rows:
                if "url" in row:
                    urls.add(row["url"].rstrip("/"))
        except Exception as exc:
            logger.warning("Could not read %s: %s", articles_json, exc)

    logger.info("Loaded %d eval-pinned URLs (excluded from re-scrape)", len(urls))
    return frozenset(urls)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

SELECT_COLLAPSED = """
SELECT id, canonical_url, title, word_count
FROM articles
WHERE length(content) >= :min_length
  AND array_length(string_to_array(content, chr(10)), 1) - 1 = 0
  AND archived = FALSE
  {source_filter}
ORDER BY id
"""


def _fetch_collapsed_rows(
    db: DatabaseManager,
    min_length: int,
    source_id: int | None,
) -> list[dict[str, Any]]:
    source_filter = "AND source_id = :source_id" if source_id is not None else ""
    sql = SELECT_COLLAPSED.format(source_filter=source_filter)
    params: dict[str, Any] = {"min_length": min_length}
    if source_id is not None:
        params["source_id"] = source_id

    with db.get_session() as session:
        rows = session.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]


def _update_article_content(
    db: DatabaseManager,
    article_id: int,
    new_content: str,
    new_hash: str,
    new_word_count: int,
) -> None:
    with db.get_session() as session:
        session.execute(
            text(
                """
                UPDATE articles
                SET content = :content,
                    content_hash = :hash,
                    word_count = :wc,
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {
                "content": new_content,
                "hash": new_hash,
                "wc": new_word_count,
                "id": article_id,
            },
        )
        session.commit()


# ---------------------------------------------------------------------------
# HTTP fetch + re-process
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}


async def _fetch_html(url: str, timeout: float = 30.0) -> str | None:
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)  # noqa: S113 — URL validated by eval-exclude list
            resp.raise_for_status()
            return resp.content.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
        return None


def _reprocess(html: str, title: str) -> tuple[str, str, int]:
    """Return (new_content, new_hash, new_word_count) for a fresh HTML blob."""
    new_content = ContentCleaner.clean_html(html)
    new_hash = ContentCleaner.calculate_content_hash(title, new_content)
    new_word_count = len(new_content.split())
    return new_content, new_hash, new_word_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(
    dry_run: bool,
    limit: int | None,
    delay: float,
    min_length: int,
    source_id: int | None,
) -> None:
    eval_urls = _load_eval_urls()
    db = DatabaseManager()

    rows = _fetch_collapsed_rows(db, min_length, source_id)
    logger.info("Found %d collapsed articles in DB", len(rows))

    # Filter eval-pinned
    candidates = [r for r in rows if r["canonical_url"].rstrip("/") not in eval_urls]
    excluded = len(rows) - len(candidates)
    logger.info(
        "Excluded %d eval-pinned rows; %d remain to process",
        excluded,
        len(candidates),
    )

    if limit is not None:
        candidates = candidates[:limit]
        logger.info("Limiting to %d articles (--limit)", limit)

    updated = skipped = errors = 0

    for i, row in enumerate(candidates, 1):
        article_id = row["id"]
        url = row["canonical_url"]
        title = row["title"] or ""

        logger.info("[%d/%d] id=%d  %s", i, len(candidates), article_id, url[:80])

        if dry_run:
            logger.info("  DRY-RUN — would re-scrape")
            skipped += 1
            continue

        html = await _fetch_html(url)
        if html is None:
            logger.warning("  SKIP — fetch failed")
            errors += 1
        else:
            try:
                new_content, new_hash, new_wc = _reprocess(html, title)
                new_newlines = new_content.count("\n")
                if new_newlines == 0:
                    logger.warning(
                        "  SKIP — re-processed content still has 0 newlines (site may block scraping)"
                    )
                    skipped += 1
                else:
                    _update_article_content(db, article_id, new_content, new_hash, new_wc)
                    logger.info("  OK — restored %d newlines, %d words", new_newlines, new_wc)
                    updated += 1
            except Exception as exc:
                logger.error("  ERROR — %s", exc)
                errors += 1

        if i < len(candidates):
            time.sleep(delay)

    logger.info(
        "Done. updated=%d  skipped=%d  errors=%d  (dry_run=%s)",
        updated,
        skipped,
        errors,
        dry_run,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print plan; make no DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between fetches")
    parser.add_argument("--min-length", type=int, default=5000, help="Min content chars to consider")
    parser.add_argument("--source-id", type=int, default=None, help="Restrict to a single source_id")
    args = parser.parse_args()

    asyncio.run(
        main(
            dry_run=args.dry_run,
            limit=args.limit,
            delay=args.delay,
            min_length=args.min_length,
            source_id=args.source_id,
        )
    )
