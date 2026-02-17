#!/usr/bin/env python3
"""
Fetch eval article content from URLs and write static JSON for filesystem-based evals.

Reads config/eval_articles.yaml, fetches each external URL, and writes
config/eval_articles_data/{subagent}/articles.json so the Agent Evals page
shows articles as "Found" and evals can run without the DB.

Localhost URLs (e.g. http://127.0.0.1:8001/articles/123) are skipped; use
dump_eval_articles_static.py when the DB contains those articles.

Usage:
    python3 scripts/fetch_eval_articles_static.py
    .venv/bin/python scripts/fetch_eval_articles_static.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml
from bs4 import BeautifulSoup

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

CONFIG_EVAL_ARTICLES = project_root / "config" / "eval_articles.yaml"
DATA_DIR = project_root / "config" / "eval_articles_data"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc in (
        "127.0.0.1:8001",
        "localhost:8001",
        "127.0.0.1",
        "localhost",
    )


async def fetch_article(url: str) -> tuple[str, str]:
    """Fetch URL and return (title, content)."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        html = response.content.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "meta", "noscript", "iframe"]):
        tag.decompose()
    content_text = soup.get_text(separator=" ", strip=True)
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    title_tag = soup.find("title")
    title = (title_tag.get_text().strip() if title_tag else "") or "Untitled Article"
    return title, sanitized


async def process_subagent(
    subagent_key: str,
    articles_def: list[dict],
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Fetch all external URLs for a subagent and return list of article dicts."""
    if not isinstance(articles_def, list) or not articles_def:
        return []
    out: list[dict] = []
    for article_def in articles_def:
        url = article_def.get("url")
        if not url:
            continue
        if _is_localhost_url(url):
            print(f"  Skip (localhost): {url[:60]}...")
            continue
        expected_count = article_def.get("expected_count", 0)
        async with sem:
            try:
                title, content = await fetch_article(url)
                out.append(
                    {
                        "url": url,
                        "title": title,
                        "content": content,
                        "filtered_content": content,
                        "expected_count": expected_count,
                    }
                )
                print(f"  OK: {url[:55]}... ({len(content)} chars)")
            except Exception as e:
                print(f"  FAIL: {url[:55]}... {e}")
    return out


async def main_async() -> None:
    if not CONFIG_EVAL_ARTICLES.exists():
        print(f"Config not found: {CONFIG_EVAL_ARTICLES}")
        sys.exit(1)

    with open(CONFIG_EVAL_ARTICLES) as f:
        config = yaml.safe_load(f) or {}
    subagents = config.get("subagents", {})
    if not subagents:
        print("No subagents in config.")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(3)  # limit concurrent fetches

    for subagent_key, articles_def in subagents.items():
        if not isinstance(articles_def, list) or not articles_def:
            continue
        urls = [a.get("url") for a in articles_def if a.get("url")]
        external = [u for u in urls if u and not _is_localhost_url(u)]
        if not external:
            print(f"{subagent_key}: no external URLs to fetch (only localhost or empty).")
            continue
        print(f"{subagent_key}: fetching {len(external)} URL(s)...")
        out_articles = await process_subagent(subagent_key, articles_def, sem)
        if not out_articles:
            print(f"  No articles fetched for {subagent_key}.")
            continue
        subdir = DATA_DIR / subagent_key
        subdir.mkdir(parents=True, exist_ok=True)
        out_path = subdir / "articles.json"
        with open(out_path, "w") as f:
            json.dump(out_articles, f, indent=2)
        print(f"  Wrote {len(out_articles)} articles to {out_path}\n")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
