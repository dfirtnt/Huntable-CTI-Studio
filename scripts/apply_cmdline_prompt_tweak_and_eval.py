#!/usr/bin/env python3
"""
Apply one small CmdlineExtract prompt tweak (distinct-once + no list/enumeration extraction)
then run cmdline eval at current config (temp 0) and report nMAE.

Evidence: bundle inspection showed over-extraction from same command in multiple phrasings
and from inline/list enumerations; this edit targets those without changing structure.

Usage: .venv/bin/python3 scripts/apply_cmdline_prompt_tweak_and_eval.py [--base-url URL]
Requires: web app and Celery worker running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_EVAL_ARTICLES = ROOT / "config" / "eval_articles.yaml"
SUBAGENT = "cmdline"
POLL_INTERVAL = 30
POLL_TIMEOUT = 3600

# One sentence to add before "Output ONLY the JSON" (or at end of instructions).
# Targets over-extraction: same command in multiple phrasings, list/enumeration extraction.
TWEAK_SENTENCE = (
    "Output each distinct command exactly once; do not list the same command in multiple "
    "phrasings (e.g. quoted vs unquoted). Do not extract from inline lists, bulleted lists, "
    "or 'such as' / 'including' enumerations."
)


def load_cmdline_urls() -> list[str]:
    with open(CONFIG_EVAL_ARTICLES) as f:
        data = yaml.safe_load(f)
    entries = (data.get("subagents") or {}).get(SUBAGENT) or []
    return [e.get("url") for e in entries if e.get("url")]


def get_config(base_url: str) -> dict:
    r = requests.get(f"{base_url}/api/workflow/config", timeout=30)
    r.raise_for_status()
    return r.json()


def put_config(base_url: str, payload: dict) -> dict:
    r = requests.put(f"{base_url}/api/workflow/config", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def run_eval(base_url: str, article_urls: list[str]) -> dict:
    r = requests.post(
        f"{base_url}/api/evaluations/run-subagent-eval",
        json={"subagent_name": SUBAGENT, "article_urls": article_urls, "use_active_config": True},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def get_results(base_url: str) -> dict:
    r = requests.get(
        f"{base_url}/api/evaluations/subagent-eval-results",
        params={"subagent": SUBAGENT},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_aggregate(base_url: str, config_version: int) -> dict:
    r = requests.get(
        f"{base_url}/api/evaluations/subagent-eval-aggregate",
        params={"subagent": SUBAGENT, "config_version": config_version},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def wait_until_complete(base_url: str, config_version: int) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        data = get_results(base_url)
        pending = [
            x
            for x in data.get("results", [])
            if x.get("status") == "pending" and x.get("config_version") == config_version
        ]
        if not pending:
            return
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Eval (config_version={config_version}) did not complete within {POLL_TIMEOUT}s")


def apply_tweak_to_instructions(instructions: str) -> str:
    anchor = "Output ONLY the JSON object."
    if anchor in instructions:
        insert = f"\n\n{TWEAK_SENTENCE}\n\n"
        return instructions.replace(anchor, insert + anchor, 1)
    return instructions.rstrip() + f"\n\n{TWEAK_SENTENCE}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply CmdlineExtract tweak and run one eval")
    parser.add_argument("--base-url", default=os.environ.get("CTI_SCRAPER_URL", "http://localhost:8001"))
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    if not CONFIG_EVAL_ARTICLES.exists():
        print(f"Missing {CONFIG_EVAL_ARTICLES}", file=sys.stderr)
        return 1
    article_urls = load_cmdline_urls()
    if not article_urls:
        print("No cmdline article URLs", file=sys.stderr)
        return 1

    try:
        cfg = get_config(base_url)
    except requests.RequestException as e:
        print(f"GET config failed: {e}. Is the app at {base_url}?", file=sys.stderr)
        return 1

    agent_prompts = (cfg.get("agent_prompts") or {}).copy()
    cmdline = agent_prompts.get("CmdlineExtract")
    if not cmdline or not isinstance(cmdline, dict):
        print("CmdlineExtract prompt not found in config", file=sys.stderr)
        return 1

    prompt_str = cmdline.get("prompt") or "{}"
    try:
        prompt_obj = json.loads(prompt_str)
    except json.JSONDecodeError as e:
        print(f"CmdlineExtract prompt is not valid JSON: {e}", file=sys.stderr)
        return 1

    instructions = prompt_obj.get("instructions") or ""
    if TWEAK_SENTENCE in instructions:
        print("Tweak already present in prompt; applying anyway (idempotent).")
    prompt_obj["instructions"] = apply_tweak_to_instructions(instructions)
    cmdline = {**cmdline, "prompt": json.dumps(prompt_obj)}
    agent_prompts["CmdlineExtract"] = cmdline

    try:
        updated = put_config(
            base_url,
            {
                "agent_prompts": agent_prompts,
                "description": "CmdlineExtract: distinct-once + no list/enumeration extraction",
            },
        )
        new_version = updated.get("version")
        print(f"Config updated to version {new_version}. Running eval...")
    except requests.RequestException as e:
        print(f"PUT config failed: {e}", file=sys.stderr)
        return 1

    try:
        out = run_eval(base_url, article_urls)
        print(f"Triggered {out.get('found_articles', 0)}/{out.get('total_articles', 0)} executions")
    except requests.RequestException as e:
        print(f"Run eval failed: {e}", file=sys.stderr)
        return 1

    try:
        wait_until_complete(base_url, new_version)
    except TimeoutError as e:
        print(e, file=sys.stderr)
        return 1

    agg_data = get_aggregate(base_url, new_version)
    aggregates = agg_data.get("aggregates") or []
    if not aggregates:
        print("No aggregates for this config version")
        return 1
    agg = aggregates[0]
    nmae = agg.get("mean_absolute_error")
    raw_mae = agg.get("raw_mae")
    perfect = agg.get("perfect_matches", 0)
    total = agg.get("completed", 0)
    print(f"nMAE={nmae} raw_mae={raw_mae} perfect={perfect}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
