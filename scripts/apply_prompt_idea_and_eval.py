#!/usr/bin/env python3
"""
Apply one prompt idea (1, 2, or 3) from failure-bundle analysis to CmdlineExtract,
then run cmdline eval and report nMAE. Use one at a time to measure marginal effect.

  --idea 1: cmd.exe quoting normalization (treat /c X and \"/c X\" as same; output one form)
  --idea 2: exclude discovery-summary phrases unless full command on one literal line
  --idea 3: allow single-line commands inside script/code blocks

Usage: .venv/bin/python3 scripts/apply_prompt_idea_and_eval.py --idea 1 [--base-url URL]
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

IDEA_SENTENCES = {
    1: (
        'Treat cmd.exe /c X and cmd.exe "/c X" as the same command; '
        "output only one form (e.g. the form that appears first in the content)."
    ),
    2: (
        "Do not extract from 'commands executed', 'commands observed', "
        "or discovery-summary phrases unless the full command appears on one literal line."
    ),
    3: (
        "If a full command appears on one line inside a script or code block, extract it; "
        "do not exclude solely because of surrounding lines."
    ),
}


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


def add_idea_to_instructions(instructions: str, sentence: str) -> str:
    anchor = "Output ONLY the JSON object."
    if anchor in instructions:
        insert = f"\n\n{sentence}\n\n"
        return instructions.replace(anchor, insert + anchor, 1)
    return instructions.rstrip() + f"\n\n{sentence}\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply one prompt idea (1–3) and run cmdline eval")
    parser.add_argument("--idea", type=int, choices=[1, 2, 3], required=True)
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

    sentence = IDEA_SENTENCES[args.idea]
    print(f"Applying idea {args.idea}: {sentence[:60]}...")

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
    if sentence in instructions:
        print("Idea already present in prompt (idempotent).")
    prompt_obj["instructions"] = add_idea_to_instructions(instructions, sentence)
    cmdline = {**cmdline, "prompt": json.dumps(prompt_obj)}
    agent_prompts["CmdlineExtract"] = cmdline

    try:
        updated = put_config(
            base_url,
            {
                "agent_prompts": agent_prompts,
                "description": f"CmdlineExtract: prompt idea {args.idea} (bundle follow-up)",
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
