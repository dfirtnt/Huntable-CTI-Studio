#!/usr/bin/env python3
"""
Find the best CommandLine eval that uses a Qwen model.
Queries agentic_workflow_config.agent_models for CmdlineExtract_model containing 'qwen',
then ranks by nMAE (lower is better) among cmdline subagent_evaluations.

Usage (from repo root, DB reachable):
  PYTHONPATH=. .venv/bin/python3 scripts/best_cmdline_eval_qwen.py
"""

from pathlib import Path

import yaml

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable, SubagentEvaluationTable
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
    return canonical or (lookup_values[0] if lookup_values else subagent), lookup_values


def _is_qwen_config(agent_models: dict | None) -> bool:
    if not agent_models:
        return False
    model = agent_models.get("CmdlineExtract_model") or agent_models.get("CmdlineExtract") or ""
    return "qwen" in str(model).lower()


def _aggregate_cmdline_by_version(records: list, preset: dict[str, int]) -> list[tuple[int, float | None, float, int]]:
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
            expected = preset.get(r.article_url)
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
        # Config versions that use Qwen for CmdlineExtract
        configs = session.query(AgenticWorkflowConfigTable).all()
        qwen_versions = set()
        version_to_model = {}
        for c in configs:
            if _is_qwen_config(c.agent_models):
                qwen_versions.add(c.version)
                model = (
                    (c.agent_models or {}).get("CmdlineExtract_model")
                    or (c.agent_models or {}).get("CmdlineExtract")
                    or ""
                )
                version_to_model[c.version] = model

        if not qwen_versions:
            print("No workflow config found with Qwen as CmdlineExtract model.")
            return

        # Cmdline eval aggregates
        _, lookup_values = _resolve_lookup("cmdline")
        preset = _load_preset_expected_by_url("cmdline")
        rows = (
            session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.subagent_name.in_(lookup_values))
            .all()
        )
        agg = _aggregate_cmdline_by_version(rows, preset)
        # Keep only Qwen configs with valid nMAE
        qwen_agg = [(v, nmae, pct, n) for v, nmae, pct, n in agg if v in qwen_versions and nmae is not None]
        qwen_agg.sort(key=lambda x: (x[1], -x[2]))  # best nMAE, then higher perfect%

        print("Best CommandLine eval using Qwen (by nMAE, lower is better)\n")
        if not qwen_agg:
            print("No completed cmdline evals found for any Qwen config.")
            return
        ver, nmae, pct, n = qwen_agg[0]
        model = version_to_model.get(ver, "?")
        print(f"  config_version={ver}  nMAE={nmae:.4f}  perfect%={pct:.1f}  n={n}")
        print(f"  CmdlineExtract model: {model}")
        print("\nAll Qwen cmdline evals (best first):")
        for i, (ver, nmae, pct, n) in enumerate(qwen_agg[:15], 1):
            m = version_to_model.get(ver, "?")
            print(f"  {i:2}. v{ver}  nMAE={nmae:.4f}  perfect%={pct:.1f}  n={n}  model={m}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
