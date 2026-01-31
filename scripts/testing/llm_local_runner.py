#!/usr/bin/env python3
"""
Host-side LLM tester for CTIScraper.

Features:
- Fetch article JSON from http://localhost:8001/api/articles/<id>
- List LMStudio models from http://localhost:1234/v1/models
- Run N models × M prompts against LMStudio chat API
- Save results to CSV (outputs/exports/llm_tests.csv by default)

Usage examples:
  python scripts/testing/llm_local_runner.py --list-models
  python scripts/testing/llm_local_runner.py --article-id 68 --models modelA modelB --prompts \"Summarize the article\" \"List IOCs\"
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API = "http://localhost:8001"
DEFAULT_LMSTUDIO = "http://localhost:1234/v1"
DEFAULT_OUTPUT = Path("outputs/exports/llm_tests.csv")


def get_article(article_id: int, base_url: str = DEFAULT_API, timeout: float = 10.0) -> dict[str, Any]:
    url = f"{base_url}/api/articles/{article_id}"
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def list_models(lmstudio_url: str = DEFAULT_LMSTUDIO, timeout: float = 10.0) -> list[str]:
    resp = httpx.get(f"{lmstudio_url}/models", timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def run_chat(
    model: str, prompt: str, content: str, lmstudio_url: str = DEFAULT_LMSTUDIO, timeout: float = 30.0
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant for CTI analysis."},
            {"role": "user", "content": content},
        ],
        "temperature": 0.4,
        "max_tokens": 800,
    }
    resp = httpx.post(f"{lmstudio_url}/chat/completions", json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"raw": data, "message": msg}


def build_prompt(article: dict[str, Any], prompt_text: str) -> str:
    title = article.get("title", "")
    url = article.get("canonical_url", "")
    content = (article.get("content") or "")[:4000]
    return (
        f"Article Title: {title}\n"
        f"Article URL: {url}\n\n"
        f"Article Content (truncated to 4000 chars):\n{content}\n\n"
        f"Task: {prompt_text}"
    )


def write_csv(rows: Iterable[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run LMStudio tests against CTIScraper API articles.")
    parser.add_argument("--article-id", type=int, default=68, help="Article ID to fetch from the API.")
    parser.add_argument("--api-url", default=DEFAULT_API, help="Base URL for the CTIScraper web API.")
    parser.add_argument("--lmstudio-url", default=DEFAULT_LMSTUDIO, help="Base URL for LMStudio.")
    parser.add_argument("--models", nargs="+", help="Model IDs to test. If omitted, all available models are used.")
    parser.add_argument(
        "--prompts", nargs="+", required=False, help="Prompts to run. If omitted, a default prompt is used."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="CSV output path.")
    parser.add_argument("--list-models", action="store_true", help="List available LMStudio models and exit.")
    args = parser.parse_args(argv)

    try:
        available_models = list_models(args.lmstudio_url)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Failed to list LMStudio models: {exc}", file=sys.stderr)
        return 1

    if args.list_models:
        print("Available models:")
        for m in available_models:
            print(f"- {m}")
        return 0

    models = args.models or available_models
    if not models:
        print("❌ No models available; start LMStudio or pass --models.", file=sys.stderr)
        return 1

    prompts = args.prompts or [
        "Summarize the key IOCs and behaviors with bullet points.",
        "List any commands or tools that indicate malicious behavior.",
    ]

    try:
        article = get_article(args.article_id, base_url=args.api_url)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Failed to fetch article {args.article_id}: {exc}", file=sys.stderr)
        return 1

    results = []
    start_ts = datetime.now().isoformat()
    print(f"✅ Article {args.article_id} fetched; running {len(models)} models × {len(prompts)} prompts...")

    for model in models:
        for prompt_text in prompts:
            built_prompt = build_prompt(article, prompt_text)
            try:
                reply = run_chat(model, prompt_text, built_prompt, lmstudio_url=args.lmstudio_url)
                message = reply.get("message", "")
                status = "ok"
            except Exception as exc:  # noqa: BLE001
                message = f"ERROR: {exc}"
                status = "error"
            results.append(
                {
                    "timestamp": start_ts,
                    "article_id": args.article_id,
                    "article_title": article.get("title", "")[:120],
                    "model": model,
                    "prompt": prompt_text,
                    "response": message,
                    "response_length": len(message),
                    "status": status,
                }
            )
            print(f"- {model} | {prompt_text[:40]}... | {status}")

    out_path = Path(args.output)
    write_csv(results, out_path)
    print(f"📄 Results written to {out_path} ({len(results)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
