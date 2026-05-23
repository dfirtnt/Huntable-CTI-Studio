#!/usr/bin/env python3
"""Repair misattributed article source_id values.

Finds non-archived articles whose canonical_url hostname doesn't match their
source's hostname, then takes one of three actions per row:

  archive   — a correctly-sourced twin already exists; this row is a duplicate.
  repoint   — the URL host maps unambiguously to exactly one source in the DB;
              update source_id to point there.
  review    — ambiguous; log for human decision.

Dry-run by default.  Pass --apply to execute changes.

Usage
-----
    # Audit only (no writes):
    python scripts/repair_source_attribution.py

    # Apply fixes:
    python scripts/repair_source_attribution.py --apply

    # Verbose row-by-row output:
    python scripts/repair_source_attribution.py --verbose

Exit codes: 0 = success (or dry-run complete), 1 = fatal error.
"""

import argparse
import logging
import os
import sys
from urllib.parse import urlparse

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import ArticleTable, SourceTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Allowlist — benign cross-domain pairs that must not be flagged as errors.
# Each entry is (article_host_substring, source_name_substring), case-insensitive.
# Add new entries here when a legitimate CDN/mirror/rebrand is identified.
# ---------------------------------------------------------------------------
_ALLOWLIST: list[tuple[str, str]] = [
    ("security.com", "symantec"),
    ("broadcom.com", "symantec"),
    ("cisa.gov", "cert"),
    ("us-cert.gov", "cert"),
    ("us-cert.cisa.gov", "cert"),
    ("microsoft.com", "microsoft"),
    ("techcommunity.microsoft.com", "microsoft"),
    ("blogs.microsoft.com", "microsoft"),
]

# Eval Articles source is intentionally cross-domain — skip entirely.
_EVAL_SOURCE_NAME = "Eval Articles"


def _host(url: str) -> str:
    """Return lowercase hostname from a URL, or empty string on parse failure."""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _is_allowlisted(article_host: str, source_name: str) -> bool:
    ah = article_host.lower()
    sn = source_name.lower()
    return any(ah_sub in ah and sn_sub in sn for ah_sub, sn_sub in _ALLOWLIST)


def run(apply: bool = False, verbose: bool = False) -> dict:
    """Main repair loop.  Returns summary counts."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)

    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(db_url)

    counts = {"scanned": 0, "allowlisted": 0, "archived": 0, "repointed": 0, "review": 0, "errors": 0}

    with Session(engine) as session:
        # Build hostname → [source] map for re-pointing decisions.
        sources = session.query(SourceTable).all()
        host_to_sources: dict[str, list[SourceTable]] = {}
        for src in sources:
            h = _host(src.url)
            if h:
                host_to_sources.setdefault(h, []).append(src)

        # Find all non-archived mismatched articles in one pass.
        rows = (
            session.query(ArticleTable, SourceTable)
            .join(SourceTable, ArticleTable.source_id == SourceTable.id)
            .filter(ArticleTable.archived == False)  # noqa: E712
            .all()
        )

        for article, source in rows:
            if source.name == _EVAL_SOURCE_NAME:
                continue

            article_host = _host(article.canonical_url)
            source_host = _host(source.url)

            if not article_host or article_host == source_host:
                continue  # matches or unparseable — skip

            counts["scanned"] += 1

            if _is_allowlisted(article_host, source.name):
                counts["allowlisted"] += 1
                if verbose:
                    logger.info("ALLOWLIST  article=%d url=%s source=%s", article.id, article.canonical_url, source.name)
                continue

            # Decision 1: archive if a correctly-sourced twin exists.
            correct_sources = host_to_sources.get(article_host, [])
            correct_source_ids = {s.id for s in correct_sources}
            twin = (
                session.query(ArticleTable)
                .filter(
                    ArticleTable.canonical_url == article.canonical_url,
                    ArticleTable.source_id.in_(correct_source_ids),
                    ArticleTable.archived == False,  # noqa: E712
                )
                .first()
                if correct_source_ids
                else None
            )

            if twin is not None:
                counts["archived"] += 1
                if verbose or not apply:
                    logger.info(
                        "ARCHIVE  article=%d url=%s wrong_source=%s(%d) twin=%d correct_source=%d",
                        article.id, article.canonical_url, source.name, source.id, twin.id, twin.source_id,
                    )
                if apply:
                    try:
                        article.archived = True
                        session.flush()
                    except Exception as exc:
                        logger.error("Failed to archive article=%d: %s", article.id, exc)
                        session.rollback()
                        counts["errors"] += 1
                continue

            # Decision 2: re-point if URL host maps unambiguously to one source.
            if len(correct_sources) == 1:
                target = correct_sources[0]
                counts["repointed"] += 1
                if verbose or not apply:
                    logger.info(
                        "REPOINT  article=%d url=%s wrong_source=%s(%d) -> correct_source=%s(%d)",
                        article.id, article.canonical_url, source.name, source.id, target.name, target.id,
                    )
                if apply:
                    try:
                        article.source_id = target.id
                        session.flush()
                    except Exception as exc:
                        logger.error("Failed to repoint article=%d: %s", article.id, exc)
                        session.rollback()
                        counts["errors"] += 1
                continue

            # Decision 3: needs human review.
            counts["review"] += 1
            logger.info(
                "REVIEW   article=%d url=%s wrong_source=%s(%d) candidates=%s",
                article.id,
                article.canonical_url,
                source.name,
                source.id,
                [s.name for s in correct_sources] if correct_sources else "none",
            )

        if apply and counts["errors"] == 0:
            session.commit()
            logger.info("Changes committed.")
        elif apply and counts["errors"] > 0:
            session.rollback()
            logger.warning("%d error(s) — all changes rolled back.", counts["errors"])
        else:
            logger.info("Dry-run complete — no changes written.  Pass --apply to execute.")

    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Execute changes (default: dry-run)")
    parser.add_argument("--verbose", action="store_true", help="Log every row, including allowlisted ones")
    args = parser.parse_args()

    counts = run(apply=args.apply, verbose=args.verbose)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    logger.info(
        "%s summary — scanned=%d allowlisted=%d archived=%d repointed=%d review=%d errors=%d",
        mode,
        counts["scanned"],
        counts["allowlisted"],
        counts["archived"],
        counts["repointed"],
        counts["review"],
        counts["errors"],
    )

    sys.exit(1 if counts["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
