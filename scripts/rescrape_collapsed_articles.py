"""One-shot backfill: re-scrape articles whose stored content needs repair.

The early scrape pipeline used soup.get_text(strip=True) which collapses all
block-level newlines into spaces. ContentCleaner.clean_html() was later fixed
to preserve newlines via normalize_whitespace_keep_newlines(). This script
retroactively fetches the raw HTML for collapsed rows and re-processes it
through the fixed path.

HARD CONSTRAINT: eval-pinned URLs (config/eval_articles.yaml and every
config/eval_articles_data/*/articles.json) are EXCLUDED and never touched.
Eval doctrine is forward-only; ground truth is never changed to chase a
pipeline bug.

CONTENT-LOSS GUARD: publishers edit articles after we capture them, so a fresh
fetch that is materially smaller than what we stored is drift, not a repair.
Articles below --min-ratio are SKIPPED rather than overwritten, and the
fresh/stored ratio is logged on every skip and every write so drift is visible
in the run output.

Usage:
    uv run --frozen scripts/rescrape_collapsed_articles.py --dry-run
    uv run --frozen scripts/rescrape_collapsed_articles.py --limit 50
    uv run --frozen scripts/rescrape_collapsed_articles.py            # all
    uv run --frozen scripts/rescrape_collapsed_articles.py \
        --all-content --min-hunt-score 90 --min-length 0
    uv run --frozen scripts/rescrape_collapsed_articles.py --min-ratio 0.5  # lossy

Options:
    --dry-run        Print which articles would be updated; make no DB writes.
    --limit N        Stop after processing N articles (default: unlimited).
    --delay SECS     Seconds to sleep between fetches (default: 1.5).
    --min-length N   Minimum content length to consider collapsed (default: 5000).
    --source-id N    Restrict to a single source_id (optional).
    --min-hunt-score N  Restrict to articles with a higher hunt score (optional).
    --all-content    Include structured rows; requires --min-hunt-score.
    --min-ratio R    Require fresh content >= R x the stored length (default: 0.95).
                     Use 0.5 to deliberately allow lossy overwrites.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib
import sys
import time
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
SELECT id, canonical_url, content, title, word_count
FROM articles
WHERE length(content) >= :min_length
  {content_filter}
  AND archived = FALSE
  {hunt_score_filter}
  {source_filter}
ORDER BY id
"""


def _fetch_rows(
    db: DatabaseManager,
    min_length: int,
    source_id: int | None,
    min_hunt_score: float | None,
    all_content: bool,
) -> list[dict[str, Any]]:
    source_filter = "AND source_id = :source_id" if source_id is not None else ""
    content_filter = "" if all_content else "AND array_length(string_to_array(content, chr(10)), 1) - 1 = 0"
    hunt_score_filter = ""
    if min_hunt_score is not None:
        hunt_score_filter = """
        AND CASE
            WHEN article_metadata ->> 'threat_hunting_score' ~ '^[0-9]+([.][0-9]+)?$'
            THEN (article_metadata ->> 'threat_hunting_score')::numeric
            ELSE 0
        END > :min_hunt_score
        """
    sql = SELECT_COLLAPSED.format(
        content_filter=content_filter,
        hunt_score_filter=hunt_score_filter,
        source_filter=source_filter,
    )
    params: dict[str, Any] = {"min_length": min_length}
    if source_id is not None:
        params["source_id"] = source_id
    if min_hunt_score is not None:
        params["min_hunt_score"] = min_hunt_score

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


MIN_REFRESH_CONTENT_CHARS = 500

# Default drift floor. Upstream publishers routinely edit articles after we
# capture them, so a re-scrape that comes back materially smaller is a silent
# content-loss event, not a repair. Measured case: article 6759 (Sekoia) stored
# 18,177 chars but re-fetched at ~14,200 (0.78x) after the publisher edited the
# page — a permissive floor would have destroyed 4,000 chars of archived CTI.
DEFAULT_MIN_EXISTING_CONTENT_RATIO = 0.95

# Explicit escape hatch for operators who knowingly accept lossy overwrites,
# e.g. `--min-ratio 0.5`. Never the default.
LOOSE_MIN_EXISTING_CONTENT_RATIO = 0.5


def _content_ratio(existing_content: str, fresh_content: str) -> float:
    """Fresh/existing length ratio; inf when nothing was stored to lose."""
    existing_length = len(existing_content)
    if existing_length == 0:
        return float("inf")
    return len(fresh_content) / existing_length


def _validate_refresh_content(
    existing_content: str,
    fresh_content: str,
    min_ratio: float = DEFAULT_MIN_EXISTING_CONTENT_RATIO,
) -> float:
    """Reject title shells and content regressions before a DB update.

    Returns the fresh/existing length ratio so callers can log drift.
    """
    fresh_length = len(fresh_content)
    existing_length = len(existing_content)
    ratio = _content_ratio(existing_content, fresh_content)

    if fresh_length < MIN_REFRESH_CONTENT_CHARS:
        raise ValueError(f"fresh content too short ({fresh_length} < {MIN_REFRESH_CONTENT_CHARS})")
    if fresh_length < existing_length * min_ratio:
        raise ValueError(
            f"fresh content regressed to {ratio:.2f}x of stored, below the "
            f"{min_ratio:.2f}x floor ({fresh_length} < {existing_length * min_ratio:.0f} chars)"
        )
    if fresh_content.count("\n") == 0:
        raise ValueError("fresh content has 0 newlines")
    return ratio


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(
    dry_run: bool,
    limit: int | None,
    delay: float,
    min_length: int,
    source_id: int | None,
    min_hunt_score: float | None,
    all_content: bool,
    min_ratio: float = DEFAULT_MIN_EXISTING_CONTENT_RATIO,
) -> None:
    eval_urls = _load_eval_urls()
    db = DatabaseManager()

    logger.info(
        "Content-loss floor: fresh content must be >= %.2fx the stored length",
        min_ratio,
    )

    rows = _fetch_rows(db, min_length, source_id, min_hunt_score, all_content)
    selection_description = "eligible articles" if all_content else "collapsed articles"
    logger.info("Found %d %s in DB", len(rows), selection_description)

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
                existing_content = row["content"] or ""
                ratio = _content_ratio(existing_content, new_content)
                try:
                    _validate_refresh_content(existing_content, new_content, min_ratio)
                except ValueError as exc:
                    logger.warning(
                        "  SKIP — %s [ratio %.2fx: stored %d chars -> fresh %d chars]",
                        exc,
                        ratio,
                        len(existing_content),
                        len(new_content),
                    )
                    skipped += 1
                else:
                    _update_article_content(db, article_id, new_content, new_hash, new_wc)
                    logger.info(
                        "  OK — ratio %.2fx (stored %d chars -> fresh %d chars), %d newlines, %d words",
                        ratio,
                        len(existing_content),
                        len(new_content),
                        new_content.count("\n"),
                        new_wc,
                    )
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print plan; make no DB writes")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between fetches")
    parser.add_argument("--min-length", type=int, default=5000, help="Min content chars to consider")
    parser.add_argument("--source-id", type=int, default=None, help="Restrict to a single source_id")
    parser.add_argument("--min-hunt-score", type=float, default=None, help="Require a higher hunt score")
    parser.add_argument(
        "--all-content",
        action="store_true",
        help="Include structured rows; requires --min-hunt-score",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=DEFAULT_MIN_EXISTING_CONTENT_RATIO,
        help=(
            "Skip an article unless the fresh content is at least this multiple of the "
            f"stored length (default: {DEFAULT_MIN_EXISTING_CONTENT_RATIO}). "
            f"Pass --min-ratio {LOOSE_MIN_EXISTING_CONTENT_RATIO} to accept lossy overwrites."
        ),
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.all_content and args.min_hunt_score is None:
        parser.error("--all-content requires --min-hunt-score to prevent a broad re-scrape")

    if args.min_ratio <= 0:
        parser.error("--min-ratio must be greater than 0")

    asyncio.run(
        main(
            dry_run=args.dry_run,
            limit=args.limit,
            delay=args.delay,
            min_length=args.min_length,
            source_id=args.source_id,
            min_hunt_score=args.min_hunt_score,
            all_content=args.all_content,
            min_ratio=args.min_ratio,
        )
    )
