#!/usr/bin/env python3
"""Fetch 4 article URLs (from screenshots) and add to process_lineage eval articles with localhost keys."""
import asyncio
import json
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "config" / "eval_articles_data" / "process_lineage"
ARTICLES_JSON = DATA_DIR / "articles.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Screenshot URLs -> (localhost_url, expected_count) from eval_articles.yaml
URLS_TO_FETCH = [
    ("https://www.huntress.com/blog/velociraptor-misuse-part-one-wsus-up", "http://127.0.0.1:8001/articles/68", 1),
    ("https://thedfirreport.com/2024/04/01/from-onenote-to-ransomnote-an-ice-cold-intrusion/", "http://127.0.0.1:8001/articles/762", 2),
    ("https://thedfirreport.com/2021/06/03/weblogic-rce-leads-to-xmrig/", "http://127.0.0.1:8001/articles/989", 0),
    ("https://www.picussecurity.com/resource/blog/cve-2025-59287-explained-wsus-unauthenticated-rce-vulnerability", "http://127.0.0.1:8001/articles/1523", 2),
]


async def fetch_article(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        html = r.content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "meta", "noscript", "iframe"]):
        tag.decompose()
    content_text = soup.get_text(separator=" ", strip=True)
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    title_tag = soup.find("title")
    title = (title_tag.get_text().strip() if title_tag else "") or "Untitled Article"
    return title, sanitized


async def main():
    articles = json.loads(ARTICLES_JSON.read_text()) if ARTICLES_JSON.exists() else []
    existing_localhost = {a["url"] for a in articles if a.get("url", "").startswith("http://127.0.0.1")}
    for fetch_url, localhost_url, expected_count in URLS_TO_FETCH:
        if localhost_url in existing_localhost:
            print(f"Skip (already have): {localhost_url}")
            continue
        try:
            title, content = await fetch_article(fetch_url)
            entry = {
                "url": localhost_url,
                "title": title,
                "content": content,
                "filtered_content": content,
                "expected_count": expected_count,
            }
            articles.append(entry)
            existing_localhost.add(localhost_url)
            print(f"OK: {localhost_url} <- {fetch_url[:50]}... ({len(content)} chars)")
        except Exception as e:
            print(f"FAIL: {fetch_url[:50]}... {e}")
    ARTICLES_JSON.parent.mkdir(parents=True, exist_ok=True)
    ARTICLES_JSON.write_text(json.dumps(articles, indent=2))
    print(f"Wrote {len(articles)} articles to {ARTICLES_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
