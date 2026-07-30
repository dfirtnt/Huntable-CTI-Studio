#!/usr/bin/env python3
"""
Fetch eval article content from URLs and write static JSON (maintainer script).

Reads config/eval_articles.yaml, fetches each external URL, and writes
config/eval_articles_data/{subagent}/articles.json. Run when adding or changing
URLs in eval_articles.yaml; then commit the updated JSON so the repo stays
self-contained (no dependency on articles being online). Normal installs use the
committed copies and seed from them at startup.

Localhost URLs are skipped; use dump_eval_articles_static.py when the DB has those.

Usage:
    python3 scripts/fetch_eval_articles_static.py   # re-execs with .venv if present
"""

import asyncio
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Re-exec with project .venv so httpx/yaml/bs4 are available when run as python3 script
_project_root = Path(__file__).resolve().parent.parent
_venv_dir = _project_root / ".venv"
_venv_python = _venv_dir / "bin" / ("python3" if (_venv_dir / "bin" / "python3").exists() else "python")
if _venv_python.exists():
    _prefix_real = os.path.realpath(sys.prefix)
    _venv_real = os.path.realpath(str(_venv_dir))
    if _prefix_real != _venv_real:
        os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

try:
    import httpx
    import yaml
except ModuleNotFoundError as e:
    print(
        "Missing dependency:",
        e.name or "httpx/yaml/beautifulsoup4",
        file=sys.stderr,
    )
    if not _venv_python.exists():
        print(
            "Create project venv: python3 -m venv .venv && .venv/bin/pip3 install -r requirements.txt",
            file=sys.stderr,
        )
    sys.exit(1)

project_root = _project_root
sys.path.insert(0, str(project_root))

from src.utils.content import ContentCleaner  # noqa: E402

CONFIG_EVAL_ARTICLES = project_root / "config" / "eval_articles.yaml"
DATA_DIR = project_root / "config" / "eval_articles_data"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MIN_EVAL_ARTICLE_CHARS = 500
MIN_EXISTING_CONTENT_RATIO = 0.5
NEVER_REFRESH_URLS = frozenset(
    {
        "https://www.proofpoint.com/us/blog/threat-insight/bitter-end-unraveling-eight-years-espionage-antics-part-one",
    }
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

    content = ContentCleaner.clean_html(html)
    _validate_content_length(content)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = ContentCleaner.html_to_text(title_match.group(1)) if title_match else "Untitled Article"
    return title or "Untitled Article", content


def _validate_content_length(content: str, existing_content: str | None = None) -> None:
    """Reject bot-wall shells and unexpectedly truncated refreshes."""
    content_length = len(content.strip())
    if content_length < MIN_EVAL_ARTICLE_CHARS:
        raise ValueError(
            f"cleaned article content is too short ({content_length} chars; "
            f"minimum {MIN_EVAL_ARTICLE_CHARS})"
        )
    if existing_content and content_length < len(existing_content.strip()) * MIN_EXISTING_CONTENT_RATIO:
        raise ValueError(
            f"cleaned article content regressed from {len(existing_content.strip())} to {content_length} chars"
        )


def _validate_ground_truth_retention(
    content: str,
    existing_content: str | None,
    expected_items: list[str],
) -> None:
    """Reject a refresh that removes a ground-truth item the fixture previously supported."""
    if not existing_content or not expected_items:
        return

    existing_normalized = _normalize_ground_truth_text(existing_content)
    refreshed_normalized = _normalize_ground_truth_text(content)
    lost_items = [
        item
        for item in expected_items
        if _normalize_ground_truth_text(item) in existing_normalized
        and _normalize_ground_truth_text(item) not in refreshed_normalized
    ]
    if lost_items:
        raise ValueError(f"refresh lost {len(lost_items)} previously supported ground-truth item(s): {lost_items[0]!r}")


def _normalize_ground_truth_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


@dataclass
class RefreshOutcome:
    articles: list[dict] | None
    refreshed: int
    kept_existing: list[tuple[str, str]]
    failed: list[tuple[str, str]]


async def process_subagent(
    subagent_key: str,
    articles_def: list[dict],
    sem: asyncio.Semaphore,
    fetched_by_url: dict[str, tuple[str, str]],
    fetch_failures_by_url: dict[str, Exception],
    existing_by_url: dict[str, dict],
    expected_by_url: dict[str, list[str]],
    rejected_by_url: dict[str, str],
) -> RefreshOutcome:
    """Refresh a subagent's URLs, retaining an existing fixture when a URL fails."""
    if not isinstance(articles_def, list) or not articles_def:
        return RefreshOutcome([], 0, [], [])
    out: list[dict] = []
    refreshed = 0
    kept_existing: list[tuple[str, str]] = []
    failed: list[tuple[str, str]] = []
    for article_def in articles_def:
        url = article_def.get("url")
        if not url:
            continue
        if _is_localhost_url(url):
            print(f"  Skip (localhost): {url[:60]}...")
            continue
        expected_count = article_def.get("expected_count", 0)
        existing = existing_by_url.get(url)
        try:
            if url in NEVER_REFRESH_URLS:
                raise ValueError("URL is permanently retained after ground-truth retention failure")
            if url in rejected_by_url:
                raise ValueError(rejected_by_url[url])
            if url in fetch_failures_by_url:
                raise fetch_failures_by_url[url]
            if url not in fetched_by_url:
                try:
                    async with sem:
                        fetched_by_url[url] = await fetch_article(url)
                except Exception as exc:
                    fetch_failures_by_url[url] = exc
                    raise
            title, content = fetched_by_url[url]
            existing_content = existing.get("content", "") if existing else None
            _validate_content_length(content, existing_content)
            _validate_ground_truth_retention(content, existing_content, expected_by_url.get(url, []))
            out.append(
                {
                    "url": url,
                    "title": title,
                    "content": content,
                    "expected_count": expected_count,
                }
            )
            refreshed += 1
            print(f"  OK: {url[:55]}... ({len(content)} chars)")
        except Exception as e:
            reason = str(e)
            if existing is not None:
                retained_article = existing.copy()
                retained_article["expected_count"] = expected_count
                out.append(retained_article)
                kept_existing.append((url, reason))
                if url in fetched_by_url:
                    rejected_by_url.setdefault(url, reason)
                print(f"  KEEP: {url[:55]}... ({reason})")
                continue
            failed.append((url, reason))
            print(f"  FAIL: {url[:55]}... ({reason})")
    return RefreshOutcome(None if failed else out, refreshed, kept_existing, failed)


def _write_articles_atomically(path: Path, articles: list[dict]) -> None:
    """Write one complete fixture file without exposing a partially written version."""
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as temporary_file:
        json.dump(articles, temporary_file, indent=2)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        temporary_path = Path(temporary_file.name)
    os.replace(temporary_path, path)


async def main_async() -> bool:
    if not CONFIG_EVAL_ARTICLES.exists():
        print(f"Config not found: {CONFIG_EVAL_ARTICLES}")
        sys.exit(1)

    with open(CONFIG_EVAL_ARTICLES) as f:
        config = yaml.safe_load(f) or {}
    subagents = config.get("subagents", {})
    if not subagents:
        print("No subagents in config.")
        return False

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(3)  # limit concurrent fetches
    fetched_by_url: dict[str, tuple[str, str]] = {}
    fetch_failures_by_url: dict[str, Exception] = {}
    rejected_by_url: dict[str, str] = {}
    had_partial_refresh = False
    prepared_subagents: list[tuple[str, Path, list[dict], dict[str, dict], dict[str, list[str]]]] = []

    for subagent_key, articles_def in subagents.items():
        if not isinstance(articles_def, list) or not articles_def:
            continue
        urls = [a.get("url") for a in articles_def if a.get("url")]
        external = [u for u in urls if u and not _is_localhost_url(u)]
        if not external:
            print(f"{subagent_key}: no external URLs to fetch (only localhost or empty).")
            continue
        print(f"{subagent_key}: fetching {len(external)} URL(s)...")
        out_path = DATA_DIR / subagent_key / "articles.json"
        existing_by_url: dict[str, dict] = {}
        if out_path.exists():
            with open(out_path) as f:
                existing_by_url = {
                    article["url"]: article
                    for article in json.load(f)
                    if isinstance(article, dict) and article.get("url")
                }
        expected_by_url: dict[str, list[str]] = {}
        ground_truth_path = DATA_DIR / subagent_key / "ground_truth.json"
        if ground_truth_path.exists():
            with open(ground_truth_path) as f:
                expected_by_url = {
                    article["url"]: article["expected_items"]
                    for article in json.load(f)
                    if isinstance(article, dict)
                    and article.get("url")
                    and isinstance(article.get("expected_items"), list)
                }
        prepared_subagents.append((subagent_key, out_path, articles_def, existing_by_url, expected_by_url))

    outcomes: dict[str, RefreshOutcome] = {}
    for subagent_key, _out_path, articles_def, existing_by_url, expected_by_url in prepared_subagents:
        outcomes[subagent_key] = await process_subagent(
            subagent_key,
            articles_def,
            sem,
            fetched_by_url,
            fetch_failures_by_url,
            existing_by_url,
            expected_by_url,
            rejected_by_url,
        )

    if rejected_by_url:
        print("Rebuilding affected sets with shared rejected URLs kept from existing fixtures.")
        for subagent_key, _out_path, articles_def, existing_by_url, expected_by_url in prepared_subagents:
            outcomes[subagent_key] = await process_subagent(
                subagent_key,
                articles_def,
                sem,
                fetched_by_url,
                fetch_failures_by_url,
                existing_by_url,
                expected_by_url,
                rejected_by_url,
            )

    for subagent_key, out_path, _articles_def, _existing_by_url, _expected_by_url in prepared_subagents:
        outcome = outcomes[subagent_key]
        kept_reasons = "; ".join(reason for _url, reason in outcome.kept_existing) or "none"
        print(
            f"  Summary: {outcome.refreshed} refreshed, "
            f"{len(outcome.kept_existing)} kept-existing ({kept_reasons}), "
            f"{len(outcome.failed)} failed"
        )
        if outcome.kept_existing or outcome.failed:
            had_partial_refresh = True
        if outcome.articles is None:
            print(f"  No fixture written for {subagent_key}; at least one URL has no existing fallback.\n")
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        _write_articles_atomically(out_path, outcome.articles)
        print(f"  Wrote {len(outcome.articles)} articles to {out_path}\n")
    return had_partial_refresh


def main() -> None:
    sys.exit(1 if asyncio.run(main_async()) else 0)


if __name__ == "__main__":
    main()
