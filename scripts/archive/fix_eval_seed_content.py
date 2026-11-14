"""
One-off script: backfill eval article static JSON files with content from the DB.

For each stub/empty entry in config/eval_articles_data/*/articles.json,
look for a full-content DB row and write it back to the static file so
new builds never need to pull from the live internet.

Run from repo root:
    python scripts/fix_eval_seed_content.py
"""

import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable

logging.basicConfig(level=logging.WARNING)

STUB_SIGNALS = ["Access DFIR Labs", "View the latest DFIR Report", "All Rights Reserved"]
DATA_DIR = Path(__file__).resolve().parent.parent / "config" / "eval_articles_data"


def is_stub(content: str) -> bool:
    if not content:
        return True
    # True stubs are short paywall/nav blobs (< 2000 chars). Longer content that
    # happens to start with nav text still contains the real article body.
    if len(content) < 2000 and any(s in content[:500] for s in STUB_SIGNALS):
        return True
    return False


def best_db_content(session, url: str) -> tuple[str, str] | None:
    """Return (title, content) for the largest non-stub row, or None."""
    rows = session.query(ArticleTable).filter(ArticleTable.canonical_url == url).all()
    candidates = [r for r in rows if not is_stub(r.content or "")]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: len(r.content or ""))
    return best.title or "", best.content or ""


def process_file(path: Path, session) -> tuple[int, list[str]]:
    """Update one articles.json. Returns (fixed_count, still_broken_urls)."""
    with open(path) as f:
        articles: list[dict] = json.load(f)

    changed = 0
    still_broken: list[str] = []

    for article in articles:
        url = article.get("url", "")
        content = article.get("content", "")
        if not is_stub(content):
            continue

        result = best_db_content(session, url)
        if result is None:
            still_broken.append(url)
            continue

        title, new_content = result
        article["content"] = new_content
        if title and not article.get("title"):
            article["title"] = title
        changed += 1

    if changed:
        with open(path, "w") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return changed, still_broken


def main() -> None:
    db = DatabaseManager()
    total_fixed = 0
    all_broken: dict[str, list[str]] = {}  # category -> [urls]

    with db.get_session() as session:
        for subdir in sorted(DATA_DIR.iterdir()):
            if not subdir.is_dir():
                continue
            aj = subdir / "articles.json"
            if not aj.exists():
                continue
            fixed, broken = process_file(aj, session)
            total_fixed += fixed
            if broken:
                all_broken[subdir.name] = broken
            print(f"  {subdir.name}: fixed {fixed}, still broken {len(broken)}")

    print(f"\nTotal articles updated in static files: {total_fixed}")

    if all_broken:
        print("\nURLs with no full content anywhere in DB -- need manual import:")
        for category, urls in all_broken.items():
            for url in urls:
                print(f"  [{category}] {url}")
    else:
        print("\nAll eval articles now have full content in static files.")


if __name__ == "__main__":
    main()
