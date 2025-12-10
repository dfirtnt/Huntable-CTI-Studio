#!/usr/bin/env python3
"""
Utility to refresh the curated OpenAI/Anthropic model lists used by the workflow UI.

Usage:
    python scripts/maintenance/update_provider_model_catalogs.py --write

Requires:
    OPENAI_API_KEY and/or ANTHROPIC_API_KEY environment variables.
    When keys are missing the script falls back to existing values in workflow.html.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List

import requests

from src.services.provider_model_catalog import load_catalog, save_catalog


@dataclass
class ProviderConfig:
    name: str
    env_var: str
    url: str
    headers_builder: Callable[[str], Dict[str, str]]
    filter_fn: Callable[[List[str]], List[str]]
    params_builder: Callable[[str], Dict[str, str]] = lambda _: {}


def default_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def openai_filter(model_ids: List[str]) -> List[str]:
    pattern = re.compile(r"^(gpt|o\d|o[1-9]|o-|o[a-z]|omni|text-davinci|davinci|curie|babbage|ada)", re.IGNORECASE)
    filtered = [mid for mid in model_ids if pattern.match(mid)]
    return sorted(set(filtered))


def anthropic_filter(model_ids: List[str]) -> List[str]:
    filtered = [mid for mid in model_ids if mid.lower().startswith("claude")]
    return sorted(set(filtered))


def gemini_filter(model_ids: List[str]) -> List[str]:
    cleaned = []
    for mid in model_ids:
        if not mid:
            continue
        normalized = mid.split("/")[-1]
        if normalized.lower().startswith("gemini"):
            cleaned.append(normalized)
    return sorted(set(cleaned))


PROVIDERS = [
    ProviderConfig(
        name="openai",
        env_var="OPENAI_API_KEY",
        url="https://api.openai.com/v1/models",
        headers_builder=default_headers,
        filter_fn=openai_filter,
    ),
    ProviderConfig(
        name="anthropic",
        env_var="ANTHROPIC_API_KEY",
        url="https://api.anthropic.com/v1/models?limit=200",
        headers_builder=lambda api_key: {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        filter_fn=anthropic_filter,
    ),
    ProviderConfig(
        name="gemini",
        env_var="GEMINI_API_KEY",
        url="https://generativelanguage.googleapis.com/v1beta/models",
        headers_builder=lambda _: {"Content-Type": "application/json"},
        filter_fn=gemini_filter,
        params_builder=lambda api_key: {"key": api_key},
    ),
]


def fetch_models(provider: ProviderConfig) -> List[str]:
    api_key = os.getenv(provider.env_var)
    if not api_key:
        print(f"⚠️  {provider.name}: missing {provider.env_var}; retaining existing list.", file=sys.stderr)
        return []

    try:
        response = requests.get(
            provider.url,
            headers=provider.headers_builder(api_key),
            params=provider.params_builder(api_key),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"⚠️  {provider.name}: failed to fetch models ({exc})", file=sys.stderr)
        return []

    data = response.json()
    # OpenAI returns {data: [{id: ...}, ...]}, Anthropic returns {data: [{id/name/model}...]}
    raw_ids: List[str] = []
    if isinstance(data, dict):
        payload = data.get("data") or data.get("models") or data
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict):
                    candidate = entry.get("id") or entry.get("model") or entry.get("name")
                    if candidate:
                        raw_ids.append(candidate.strip())
        elif isinstance(payload, dict):
            # Occasionally Anthropic wraps with {"models": [{"model": "..."}]}
            for entry in payload.values():
                if isinstance(entry, list):
                    for item in entry:
                        candidate = None
                        if isinstance(item, dict):
                            candidate = item.get("id") or item.get("model") or item.get("name")
                        if candidate:
                            raw_ids.append(candidate.strip())
    filtered = provider.filter_fn(raw_ids)
    print(f"→ {provider.name}: fetched {len(filtered)} models after filtering.")
    return filtered


def main(write: bool) -> None:
    existing = load_catalog()

    new_catalog: Dict[str, List[str]] = {}
    for provider in PROVIDERS:
        fetched = fetch_models(provider)
        if fetched:
            new_catalog[provider.name] = fetched
        else:
            new_catalog[provider.name] = existing[provider.name]

    if not write:
        print("Preview of updated catalog:\n")
        print(json.dumps(new_catalog, indent=2))
        return

    save_catalog(new_catalog)
    print("✅ Updated provider model catalog JSON")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh curated OpenAI/Anthropic model lists.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes back to workflow.html (default: preview only).",
    )
    args = parser.parse_args()
    main(write=args.write)
