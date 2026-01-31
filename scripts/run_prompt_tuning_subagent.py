#!/usr/bin/env python3
"""
Run the prompt-tuning subagent loop for cmdline extractor evals.

Uses APIs: run-subagent-eval, subagent-eval-results, subagent-eval-aggregate,
PUT /api/workflow/config, GET /api/evaluations/evals/{id}/export-bundle (POST with body).

Exit when nMAE <= 0.2 or 25 eval runs. Requires web app and Celery worker running.

Run from project root with venv: .venv/bin/python3 scripts/run_prompt_tuning_subagent.py [--max-runs N] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests
import yaml

# Project root (script in scripts/)
ROOT = Path(__file__).resolve().parent.parent
CONFIG_EVAL_ARTICLES = ROOT / "config" / "eval_articles.yaml"
SUBAGENT = "cmdline"
MAX_RUNS = 25
NMAE_TARGET = 0.2
POLL_INTERVAL = 30
POLL_TIMEOUT = 3600  # 1h max wait per run


def load_cmdline_urls() -> list[str]:
    with open(CONFIG_EVAL_ARTICLES) as f:
        data = yaml.safe_load(f)
    entries = (data.get("subagents") or {}).get(SUBAGENT) or []
    return [e.get("url") for e in entries if e.get("url")]


def run_eval(base_url: str, article_urls: list[str]) -> dict:
    r = requests.post(
        f"{base_url}/api/evaluations/run-subagent-eval",
        json={
            "subagent_name": SUBAGENT,
            "article_urls": article_urls,
            "use_active_config": True,
        },
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


def get_aggregate(base_url: str, config_version: int | None = None) -> dict:
    params = {"subagent": SUBAGENT}
    if config_version is not None:
        params["config_version"] = config_version
    r = requests.get(
        f"{base_url}/api/evaluations/subagent-eval-aggregate",
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_config(base_url: str) -> dict:
    r = requests.get(f"{base_url}/api/workflow/config", timeout=30)
    r.raise_for_status()
    return r.json()


def put_config(base_url: str, payload: dict) -> dict:
    r = requests.put(f"{base_url}/api/workflow/config", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def wait_until_complete(base_url: str, run_config_version: int) -> None:
    """Poll subagent-eval-results until no pending for this config version."""
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        data = get_results(base_url)
        pending = [
            x
            for x in data.get("results", [])
            if x.get("status") == "pending" and x.get("config_version") == run_config_version
        ]
        if not pending:
            return
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Eval run (config_version={run_config_version}) did not complete within {POLL_TIMEOUT}s")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run prompt-tuning subagent (cmdline evals until nMAE<=0.2 or 25 runs)"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("CTI_SCRAPER_URL", "http://localhost:8001"), help="Web app base URL"
    )
    parser.add_argument("--max-runs", type=int, default=MAX_RUNS, help=f"Max eval runs (default {MAX_RUNS})")
    parser.add_argument(
        "--dry-run", action="store_true", help="Only run one eval and print aggregate, no config changes"
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    if not CONFIG_EVAL_ARTICLES.exists():
        print(f"Missing {CONFIG_EVAL_ARTICLES}", file=sys.stderr)
        return 1
    article_urls = load_cmdline_urls()
    if not article_urls:
        print("No cmdline article URLs in config", file=sys.stderr)
        return 1

    try:
        cfg = get_config(base_url)
        run_config_version = cfg.get("version")
    except requests.RequestException as e:
        print(f"Failed to get workflow config: {e}. Is the app running at {base_url}?", file=sys.stderr)
        return 1

    run_count = 0
    best_nmae = None
    best_version = run_config_version

    while run_count < args.max_runs:
        run_count += 1
        print(f"\n--- Run {run_count}/{args.max_runs} (config_version={run_config_version}) ---")
        try:
            out = run_eval(base_url, article_urls)
            print(f"Triggered {out.get('found_articles', 0)}/{out.get('total_articles', 0)} executions")
        except requests.RequestException as e:
            print(f"Run eval failed: {e}", file=sys.stderr)
            return 1

        try:
            wait_until_complete(base_url, run_config_version)
        except TimeoutError as e:
            print(e, file=sys.stderr)
            return 1

        agg_data = get_aggregate(base_url, run_config_version)
        aggregates = agg_data.get("aggregates") or []
        if not aggregates:
            print("No aggregates for this config version")
            continue
        agg = aggregates[0]
        nmae = agg.get("mean_absolute_error")
        raw_mae = agg.get("raw_mae")
        perfect = agg.get("perfect_matches", 0)
        total = agg.get("completed", 0)
        pending = agg.get("pending", 0)
        failed = agg.get("failed", 0)
        print(f"nMAE={nmae} raw_mae={raw_mae} perfect={perfect}/{total} pending={pending} failed={failed}")

        if nmae is not None and (best_nmae is None or nmae < best_nmae):
            best_nmae = nmae
            best_version = run_config_version

        if nmae is not None and nmae <= NMAE_TARGET:
            print(f"\nTarget reached: nMAE={nmae} <= {NMAE_TARGET}. Stopping.")
            break

        if args.dry_run:
            print("Dry run: stopping after one eval.")
            break

        # Propose one change: try lowering CmdlineExtract temperature slightly
        cfg = get_config(base_url)
        models = (cfg.get("agent_models") or {}).copy()
        key_temp = "CmdlineExtract_temperature"
        key_provider = "CmdlineExtract_provider"
        current_temp = models.get(key_temp)
        if current_temp is None:
            current_temp = 0.0
        try:
            current_temp = float(current_temp)
        except (TypeError, ValueError):
            current_temp = 0.0
        # Step temperature down by 0.1, floor 0; or if already 0, try 0.2 then 0.1
        next_temp = max(0.0, current_temp - 0.1) if current_temp > 0 else 0.2
        models[key_temp] = round(next_temp, 2)
        payload = {
            "agent_models": models,
            "description": f"Prompt-tuning run {run_count}: CmdlineExtract_temperature={next_temp}",
        }
        try:
            updated = put_config(base_url, payload)
            run_config_version = updated.get("version", run_config_version)
            print(f"Updated config to version {run_config_version} (CmdlineExtract_temperature={next_temp})")
        except requests.RequestException as e:
            print(f"Config update failed: {e}", file=sys.stderr)
            break

    print("\n--- Summary ---")
    print(f"Runs: {run_count}, best nMAE: {best_nmae} (config_version={best_version})")
    if best_nmae is not None and best_nmae <= NMAE_TARGET:
        print("Exit: target nMAE reached.")
    else:
        print("Exit: max runs or update failure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
