#!/usr/bin/env python3
"""
Query subagent_evaluations and report top 10 best-scoring config versions
for CommandLine (cmdline), Proc Tree (process_lineage), and Hunt Queries (hunt_queries).
Uses same aggregation as /api/evaluations/subagent-eval-aggregate (nMAE, lower is better).

Usage (from repo root, with DB reachable):
  PYTHONPATH=. .venv/bin/python3 scripts/top_eval_config_versions.py
  # Or with explicit DB (e.g. local port-forward):
  DATABASE_URL=postgresql://user:pass@localhost:5432/cti_scraper PYTHONPATH=. \\
  .venv/bin/python3 scripts/top_eval_config_versions.py
"""

from pathlib import Path

import yaml

from src.database.manager import DatabaseManager
from src.database.models import SubagentEvaluationTable
from src.utils.subagent_utils import build_subagent_lookup_values

EXCLUDED_EVAL_ARTICLE_IDS = frozenset({62})
_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config" / "eval_articles.yaml"


def _load_preset_expected_by_url(subagent: str) -> dict[str, int]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
    subagents = config.get("subagents", {})
    canonical, _ = build_subagent_lookup_values(subagent)
    key = canonical if canonical and canonical in subagents else subagent
    articles = subagents.get(key, [])
    if not isinstance(articles, list):
        return {}
    out = {}
    for a in articles:
        url = a.get("url")
        if url is not None:
            out[url] = a.get("expected_count", 0) if a.get("expected_count") is not None else 0
    return out


def _resolve_lookup(subagent: str) -> tuple[str, list[str]]:
    canonical, lookup_values = build_subagent_lookup_values(subagent)
    lookup_values = [subagent] if not lookup_values else list(lookup_values)
    if subagent == "hunt_queries" or canonical == "hunt_queries":
        lookup_values = list(set(lookup_values) | {"hunt_queries_edr"})
    canonical_name = canonical or (lookup_values[0] if lookup_values else subagent)
    return canonical_name, lookup_values


def _aggregate_by_config_version(
    records: list, preset_expected_by_url: dict[str, int]
) -> list[tuple[int, float | None, float, int]]:
    """Group by workflow_config_version, compute nMAE. Returns list of (version, nmae, perfect_pct, completed)."""
    by_version: dict[int, list] = {}
    for r in records:
        if r.article_id is not None and r.article_id in EXCLUDED_EVAL_ARTICLE_IDS:
            continue
        v = r.workflow_config_version
        if v is None:
            continue
        if v not in by_version:
            by_version[v] = []
        by_version[v].append(r)

    out = []
    for version, recs in by_version.items():
        completed = [r for r in recs if r.status == "completed" and r.actual_count is not None]
        if not completed:
            out.append((version, None, 0.0, 0))
            continue
        scores = []
        expected_counts = []
        for r in completed:
            expected = preset_expected_by_url.get(r.article_url)
            if expected is None:
                expected = r.expected_count if r.expected_count is not None else 0
            expected_counts.append(expected)
            scores.append((r.actual_count or 0) - expected)
        mean_expected = sum(expected_counts) / len(expected_counts) if expected_counts else 1.0
        divisor = max(mean_expected, 1.0)
        mae = sum(abs(s) for s in scores) / len(scores)
        nmae = min(mae / divisor, 1.0)
        perfect_pct = 100.0 * sum(1 for s in scores if s == 0) / len(completed)
        out.append((version, nmae, perfect_pct, len(completed)))
    return out


def main() -> None:
    db = DatabaseManager()
    session = db.get_session()
    try:
        subagents = [
            ("CommandLine", "cmdline"),
            ("Proc Tree", "process_lineage"),
            ("Hunt Queries", "hunt_queries"),
        ]
        results = {}
        # version -> { "cmdline": (nmae, perfect_pct), ... } for total-score calculation
        by_version_all: dict[int, dict[str, tuple[float | None, float]]] = {}
        for display_name, key in subagents:
            canonical, lookup_values = _resolve_lookup(key)
            preset = _load_preset_expected_by_url(key)
            rows = (
                session.query(SubagentEvaluationTable)
                .filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
                .order_by(
                    SubagentEvaluationTable.workflow_config_version.desc(),
                    SubagentEvaluationTable.created_at.desc(),
                )
                .all()
            )
            agg = _aggregate_by_config_version(rows, preset)
            for v, nmae, pct, _ in agg:
                if v not in by_version_all:
                    by_version_all[v] = {}
                by_version_all[v][key] = (nmae, pct)
            # Sort by nMAE ascending (best first), then by perfect_pct descending; None nMAE last
            agg.sort(key=lambda x: (x[1] is None, x[1] if x[1] is not None else 1.0, -x[2]))
            top10 = [(v, nmae, pct, n) for v, nmae, pct, n in agg[:10]]
            results[display_name] = top10

        # Report
        print("Top 10 best-scoring config versions (by nMAE, lower is better)\n")
        for display_name, top10 in results.items():
            print(f"## {display_name}")
            if not top10:
                print("  (no completed eval data)")
                print()
                continue
            for i, (ver, nmae, pct, n) in enumerate(top10, 1):
                nmae_str = f"{nmae:.4f}" if nmae is not None else "N/A"
                print(f"  {i:2}. config_version={ver}  nMAE={nmae_str}  perfect%={pct:.1f}  n={n}")
            print()

        # Overlap
        sets = {name: {t[0] for t in top} for name, top in results.items()}
        all_versions = set()
        for s in sets.values():
            all_versions |= s
        in_more_than_one = [v for v in all_versions if sum(1 for s in sets.values() if v in s) > 1]
        if in_more_than_one:
            print("## Config versions appearing in more than one list")
            for v in sorted(in_more_than_one):
                where = [name for name, s in sets.items() if v in s]
                print(f"  config_version={v}  in: {', '.join(where)}")

        # Best total score: configs with evals in all three subagents, ranked by avg nMAE (lower = better)
        keys = ["cmdline", "process_lineage", "hunt_queries"]
        total_scores = []
        for ver, per_sub in by_version_all.items():
            nmaes = []
            pcts = []
            for k in keys:
                t = per_sub.get(k)
                if t is None or t[0] is None:
                    break
                nmaes.append(t[0])
                pcts.append(t[1])
            if len(nmaes) == 3:
                avg_nmae = sum(nmaes) / 3
                total_scores.append((ver, avg_nmae, sum(pcts), nmaes, pcts))
        total_scores.sort(key=lambda x: (x[1], -x[2]))  # best avg nMAE, then higher perfect% sum
        print()
        print("## Best total score (configs with evals in all three subagents, by avg nMAE)")
        if not total_scores:
            print("  (no config has completed evals for all three)")
        else:
            ver, avg_nmae, sum_pct, nmaes, pcts = total_scores[0]
            print(f"  Best: config_version={ver}  avg_nMAE={avg_nmae:.4f}  sum(perfect%)={sum_pct:.1f}")
            print(
                f"    cmdline nMAE={nmaes[0]:.4f} perfect%={pcts[0]:.1f}  process_lineage "
                f"nMAE={nmaes[1]:.4f} perfect%={pcts[1]:.1f}  hunt_queries nMAE={nmaes[2]:.4f} perfect%={pcts[2]:.1f}"
            )
            if len(total_scores) > 1:
                print("  Next (top 5):")
                for ver, avg_nmae, sum_pct, _nmaes, _pcts in total_scores[1:6]:
                    print(f"    config_version={ver}  avg_nMAE={avg_nmae:.4f}  sum(perfect%)={sum_pct:.1f}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
