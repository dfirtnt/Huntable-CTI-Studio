#!/usr/bin/env python3
"""
Run a short cmdline eval loop: (1) eval at current config, wait, aggregate + export under/over
bundles; (2) apply CmdlineExtract distinct-once tweak, eval again, aggregate. Prints both nMAEs
and bundle paths.

Usage: .venv/bin/python3 scripts/run_eval_loop.py [--base-url URL]
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
BUNDLES_DIR = ROOT / "scripts" / "eval_bundles"

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


def export_bundle(base_url: str, execution_id: int) -> dict:
    r = requests.post(
        f"{base_url}/api/evaluations/evals/{execution_id}/export-bundle",
        json={"agent_name": "CmdlineExtract"},
        timeout=60,
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


def apply_tweak(agent_prompts: dict) -> dict:
    cmdline = (agent_prompts.get("CmdlineExtract") or {}).copy()
    if not cmdline:
        return agent_prompts
    prompt_str = cmdline.get("prompt") or "{}"
    try:
        prompt_obj = json.loads(prompt_str)
    except json.JSONDecodeError:
        return agent_prompts
    instructions = prompt_obj.get("instructions") or ""
    anchor = "Output ONLY the JSON object."
    if anchor in instructions:
        insert = f"\n\n{TWEAK_SENTENCE}\n\n"
        prompt_obj["instructions"] = instructions.replace(anchor, insert + anchor, 1)
    else:
        prompt_obj["instructions"] = instructions.rstrip() + f"\n\n{TWEAK_SENTENCE}\n"
    cmdline["prompt"] = json.dumps(prompt_obj)
    out = {**agent_prompts, "CmdlineExtract": cmdline}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cmdline eval loop: baseline + tweak, export bundles")
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

    BUNDLES_DIR.mkdir(parents=True, exist_ok=True)

    try:
        cfg = get_config(base_url)
    except requests.RequestException as e:
        print(f"GET config failed: {e}. Is the app at {base_url}?", file=sys.stderr)
        return 1

    version_baseline = cfg.get("version")
    print(f"--- Run 1: current config (version {version_baseline}) ---")
    try:
        out = run_eval(base_url, article_urls)
        print(f"Triggered {out.get('found_articles', 0)}/{out.get('total_articles', 0)} executions")
    except requests.RequestException as e:
        print(f"Run eval failed: {e}", file=sys.stderr)
        return 1
    try:
        wait_until_complete(base_url, version_baseline)
    except TimeoutError as e:
        print(e, file=sys.stderr)
        return 1

    agg_data = get_aggregate(base_url, version_baseline)
    aggregates = agg_data.get("aggregates") or []
    if not aggregates:
        print("No aggregates for config version", version_baseline)
        return 1
    agg = aggregates[0]
    nmae1 = agg.get("mean_absolute_error")
    perfect1 = agg.get("perfect_matches", 0)
    total1 = agg.get("completed", 0)
    print(f"nMAE={nmae1} perfect={perfect1}/{total1}")

    results = get_results(base_url)
    by_version = [
        r
        for r in results.get("results", [])
        if r.get("config_version") == version_baseline and r.get("status") == "completed"
    ]
    under = [
        r
        for r in by_version
        if r.get("actual_count") is not None
        and r.get("expected_count") is not None
        and r["actual_count"] < r["expected_count"]
    ]
    over = [
        r
        for r in by_version
        if r.get("actual_count") is not None
        and r.get("expected_count") is not None
        and r["actual_count"] > r["expected_count"]
    ]
    under_id = under[0].get("execution_id") if under else None
    over_id = over[0].get("execution_id") if over else None
    if under_id:
        try:
            b = export_bundle(base_url, under_id)
            path = BUNDLES_DIR / f"under_{under_id}.json"
            with open(path, "w") as f:
                json.dump(b, f, indent=2)
            print(f"Exported under-extraction bundle: {path}")
        except requests.RequestException as e:
            print(f"Export under bundle failed: {e}", file=sys.stderr)
    if over_id:
        try:
            b = export_bundle(base_url, over_id)
            path = BUNDLES_DIR / f"over_{over_id}.json"
            with open(path, "w") as f:
                json.dump(b, f, indent=2)
            print(f"Exported over-extraction bundle: {path}")
        except requests.RequestException as e:
            print(f"Export over bundle failed: {e}", file=sys.stderr)

    print("--- Run 2: apply distinct-once tweak, eval ---")
    agent_prompts = (cfg.get("agent_prompts") or {}).copy()
    agent_prompts = apply_tweak(agent_prompts)
    try:
        updated = put_config(
            base_url,
            {"agent_prompts": agent_prompts, "description": "CmdlineExtract: distinct-once + no list/enumeration"},
        )
        version_tweak = updated.get("version")
    except requests.RequestException as e:
        print(f"PUT config failed: {e}", file=sys.stderr)
        return 1
    try:
        run_eval(base_url, article_urls)
    except requests.RequestException as e:
        print(f"Run eval failed: {e}", file=sys.stderr)
        return 1
    try:
        wait_until_complete(base_url, version_tweak)
    except TimeoutError as e:
        print(e, file=sys.stderr)
        return 1

    agg_data2 = get_aggregate(base_url, version_tweak)
    aggregates2 = agg_data2.get("aggregates") or []
    if not aggregates2:
        print("No aggregates for config version", version_tweak)
        return 1
    agg2 = aggregates2[0]
    nmae2 = agg2.get("mean_absolute_error")
    perfect2 = agg2.get("perfect_matches", 0)
    total2 = agg2.get("completed", 0)
    print(f"nMAE={nmae2} perfect={perfect2}/{total2}")

    print("--- Summary ---")
    print(f"Run 1 (v{version_baseline}): nMAE={nmae1} perfect={perfect1}/{total1}")
    print(f"Run 2 (v{version_tweak}, tweak): nMAE={nmae2} perfect={perfect2}/{total2}")
    if under_id or over_id:
        print(f"Bundles: {BUNDLES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
