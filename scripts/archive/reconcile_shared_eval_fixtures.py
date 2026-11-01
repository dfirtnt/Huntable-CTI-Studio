#!/usr/bin/env python3
"""Reconcile divergent shared eval-fixture URLs from existing local copies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "config" / "eval_articles_data"

# URL: (source fixture set, target fixture set)
RECONCILIATIONS = {
    "https://thedfirreport.com/2022/02/07/qbot-likes-to-move-it-move-it/": (
        "scheduled_tasks",
        "windows_services",
    ),
    "https://thedfirreport.com/2025/01/27/cobalt-strike-and-a-pair-of-socks-lead-to-lockbit-ransomware/": (
        "scheduled_tasks",
        "windows_services",
    ),
    "https://www.huntress.com/blog/advanced-intrusion-targeting-executive-at-critical-marketing-research-company": (
        "registry_artifacts",
        "windows_services",
    ),
    "https://www.huntress.com/blog/cephalus-ransomware": (
        "scheduled_tasks",
        "windows_services",
    ),
    "https://thedfirreport.com/2021/11/01/from-zero-to-domain-admin/": (
        "scheduled_tasks",
        "windows_services",
    ),
    "https://cloud.google.com/blog/topics/threat-intelligence/analysis-of-unc1549-ttps-targeting-aerospace-defense": (
        "cmdline",
        "sigma",
    ),
    "https://levelblue.com/blogs/spiderlabs-blog/malicious-screen-connect-campaign-abuses-ai-themed-lures-for-xworm-delivery": (
        "cmdline",
        "sigma",
    ),
    "https://thedfirreport.com/2024/04/01/from-onenote-to-ransomnote-an-ice-cold-intrusion/": (
        "process_lineage",
        "sigma",
    ),
}


def _load_json(path: Path) -> tuple[list[dict], str, bool, str]:
    raw = path.read_text()
    data = json.loads(raw)
    for ensure_ascii in (True, False):
        for trailing_newline in ("", "\n"):
            if json.dumps(data, indent=2, ensure_ascii=ensure_ascii) + trailing_newline == raw:
                return data, raw, ensure_ascii, trailing_newline
    raise ValueError(f"Unsupported JSON serialization: {path}")


def _support_count(content: str, expected_items: list[str]) -> int:
    from src.services.eval_item_scorer import _normalize

    normalized_content = _normalize(content)
    return sum(_normalize(item) in normalized_content for item in expected_items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write validated reconciliations")
    args = parser.parse_args()

    articles: dict[str, list[dict]] = {}
    metadata: dict[str, tuple[Path, str, bool, str]] = {}
    ground_truth: dict[str, dict[str, list[str]]] = {}
    for fixture_dir in sorted(DATA_DIR.iterdir()):
        articles_path = fixture_dir / "articles.json"
        if not articles_path.exists():
            continue
        data, raw, ensure_ascii, trailing_newline = _load_json(articles_path)
        articles[fixture_dir.name] = data
        metadata[fixture_dir.name] = (articles_path, raw, ensure_ascii, trailing_newline)
        gt_path = fixture_dir / "ground_truth.json"
        if gt_path.exists():
            ground_truth[fixture_dir.name] = {
                entry["url"]: entry.get("expected_items") or []
                for entry in json.loads(gt_path.read_text())
            }

    by_set_url = {
        fixture: {article["url"]: article for article in fixture_articles}
        for fixture, fixture_articles in articles.items()
    }
    changed_sets: set[str] = set()
    for url, (winner_set, target_set) in RECONCILIATIONS.items():
        winner = by_set_url[winner_set][url]
        target = by_set_url[target_set][url]
        for fixture, gt_by_url in ground_truth.items():
            expected_items = gt_by_url.get(url, [])
            winner_support = _support_count(winner["content"], expected_items)
            target_support = _support_count(target["content"], expected_items)
            if winner_support < target_support:
                raise ValueError(
                    f"{url}: {winner_set} would reduce {fixture} GT support "
                    f"from {target_support} to {winner_support}"
                )
        print(f"{url}\n  {winner_set} -> {target_set}")
        if args.write:
            target["title"] = winner["title"]
            target["content"] = winner["content"]
            changed_sets.add(target_set)

    if not args.write:
        return
    for fixture in sorted(changed_sets):
        path, _raw, ensure_ascii, trailing_newline = metadata[fixture]
        path.write_text(json.dumps(articles[fixture], indent=2, ensure_ascii=ensure_ascii) + trailing_newline)


if __name__ == "__main__":
    main()
