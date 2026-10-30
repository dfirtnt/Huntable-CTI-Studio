#!/usr/bin/env python3
"""Sync eval expected_count values from canonical xlsx → eval_articles.yaml + DB.

Canonical source: HuntableCTI-Europa-ExtractionEvals-7.0.0.xlsx (OneDrive).
Sheet: articles_table. Status=Active rows only. HuntableType → subagent mapping is fixed.

Three-way comparison:
  - xlsx (canonical)
  - config/eval_articles.yaml (runtime read, populates new SubagentEvaluationTable rows)
  - subagent_evaluations latest row per (article_id, subagent_name)

By default this is a DRY RUN: prints the planned yaml file + DB UPDATE statements
without writing. Pass --apply to actually rewrite the yaml and execute the DB updates.

Run from repo root:
    .venv/bin/python scripts/sync_eval_expected_from_xlsx.py
    .venv/bin/python scripts/sync_eval_expected_from_xlsx.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.database.manager import DatabaseManager  # noqa: E402

XLSX_PATH = Path(
    "/Users/starlord/Library/CloudStorage/OneDrive-Personal/Andrew Documents/Documents/"
    "HuntableCTI-Europa-ExtractionEvals-7.0.0.xlsx"
)
YAML_PATH = REPO_ROOT / "config" / "eval_articles.yaml"

# xlsx HuntableType → DB subagent_name (and yaml key)
TYPE_MAP = {
    "CmdLine": "cmdline",
    "ProcTree": "process_lineage",
    "HuntRule": "hunt_queries",
    "RegExtract": "registry_artifacts",
    "ServicesExtract": "windows_services",
    "SchedTask": "scheduled_tasks",
    # SigmaOutput intentionally unmapped — not a subagent.
}

SUBAGENT_ORDER = [
    "cmdline",
    "process_lineage",
    "hunt_queries",
    "registry_artifacts",
    "windows_services",
    "scheduled_tasks",
]


def norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def load_xlsx() -> dict[tuple[str, str], tuple[int, str, str]]:
    """Return {(url_norm, subagent): (expected_count, raw_url, title)}."""
    df = pd.read_excel(XLSX_PATH, sheet_name="articles_table")
    df = df[df["Status"].astype(str).str.lower() == "active"]
    out: dict[tuple[str, str], tuple[int, str, str]] = {}
    for _, r in df.iterrows():
        subagent = TYPE_MAP.get(str(r["HuntableType"]).strip())
        if not subagent:
            continue
        url = str(r["URL"]).strip()
        if not url or url == "nan":
            continue
        cnt = r["Count"]
        if pd.isna(cnt):
            continue
        out[(norm_url(url), subagent)] = (int(cnt), url, str(r.get("Title", "")).strip())
    return out


def load_yaml() -> dict[tuple[str, str], tuple[int, str]]:
    """Return {(url_norm, subagent): (expected_count, raw_url)}."""
    with open(YAML_PATH) as f:
        data = yaml.safe_load(f) or {}
    out: dict[tuple[str, str], tuple[int, str]] = {}
    for subagent, entries in (data.get("subagents") or {}).items():
        for e in entries or []:
            url = str(e.get("url", "")).strip()
            if not url:
                continue
            out[(norm_url(url), subagent)] = (int(e.get("expected_count", 0) or 0), url)
    return out


def load_db_latest() -> dict[tuple[str, str], tuple[int, int, int]]:
    """Return {(url_norm, subagent): (latest_row_id, article_id, expected_count)}."""
    sql = text(
        """
        SELECT a.id AS article_id, a.canonical_url, se.subagent_name,
               se.expected_count, se.id AS row_id
        FROM subagent_evaluations se
        JOIN articles a ON a.id = se.article_id
        WHERE se.status = 'completed'
          AND se.id IN (
              SELECT MAX(id) FROM subagent_evaluations
              WHERE status = 'completed'
              GROUP BY article_id, subagent_name
          )
        """
    )
    mgr = DatabaseManager()
    sess = mgr.get_session()
    try:
        rows = sess.execute(sql).fetchall()
    finally:
        sess.close()
    out: dict[tuple[str, str], tuple[int, int, int]] = {}
    for art_id, url, sub, exp, row_id in rows:
        out[(norm_url(url), sub)] = (int(row_id), int(art_id), int(exp))
    return out


def render_yaml(xlsx: dict[tuple[str, str], tuple[int, str, str]]) -> str:
    """Render eval_articles.yaml from xlsx canonical, preserving subagent order."""
    by_sub: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (_url_norm, subagent), (cnt, raw_url, _title) in xlsx.items():
        by_sub[subagent].append((raw_url, cnt))
    for sub in by_sub:
        by_sub[sub].sort(key=lambda t: t[0])

    lines = [
        "# Evaluation Articles for Extractor Subagents",
        "# Stores full URLs and expected observable counts for each subagent",
        "# URLs are used instead of article IDs to survive database rehydration",
        "",
        "subagents:",
    ]
    for sub in SUBAGENT_ORDER:
        if sub not in by_sub:
            continue
        lines.append(f"  {sub}:")
        for url, cnt in by_sub[sub]:
            lines.append(f'    - url: "{url}"')
            lines.append(f"      expected_count: {cnt}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Actually write yaml and execute DB updates")
    args = ap.parse_args()

    xlsx = load_xlsx()
    yml = load_yaml()
    db = load_db_latest()

    print(f"xlsx canonical pairs : {len(xlsx)}")
    print(f"yaml entries         : {len(yml)}")
    print(f"db latest pairs      : {len(db)}")
    print()

    keys = sorted(set(xlsx) | set(yml) | set(db))

    yaml_changes: list[str] = []
    db_updates: list[tuple[int, int, int, str, int]] = []  # (row_id, art_id, new, sub, old)

    for k in keys:
        url_norm, sub = k
        in_x = k in xlsx
        in_y = k in yml
        in_d = k in db
        x_cnt = xlsx[k][0] if in_x else None
        y_cnt = yml[k][0] if in_y else None
        d_cnt = db[k][2] if in_d else None
        raw_url = (xlsx[k][1] if in_x else (yml[k][1] if in_y else "?"))

        if in_x and not in_y:
            yaml_changes.append(f"  + ADD     {sub:<18} {x_cnt:>3}   {raw_url}")
        elif in_y and not in_x:
            yaml_changes.append(f"  - REMOVE  {sub:<18} (yaml={y_cnt})  {raw_url}")
        elif in_x and in_y and x_cnt != y_cnt:
            yaml_changes.append(f"  ~ UPDATE  {sub:<18} {y_cnt}→{x_cnt}   {raw_url}")

        if in_x and in_d and x_cnt != d_cnt:
            row_id, art_id, _old = db[k]
            db_updates.append((row_id, art_id, x_cnt, sub, d_cnt))

    print("=== YAML changes (config/eval_articles.yaml) ===")
    if yaml_changes:
        for line in yaml_changes:
            print(line)
    else:
        print("  (none — yaml matches xlsx)")
    print()

    print("=== DB UPDATEs (latest subagent_evaluations row per (article, subagent)) ===")
    if db_updates:
        for row_id, art_id, new, sub, old in db_updates:
            print(f"  UPDATE id={row_id:<5} art={art_id:<5} {sub:<18} {old}→{new}")
    else:
        print("  (none — db latest matches xlsx)")
    print()

    if not yaml_changes and not db_updates:
        print("Nothing to do.")
        return 0

    if not args.apply:
        print("DRY RUN — no files written, no DB writes. Pass --apply to commit.")
        print()
        print("=== Proposed eval_articles.yaml content ===")
        print(render_yaml(xlsx))
        return 0

    # --apply path
    new_yaml = render_yaml(xlsx)
    YAML_PATH.write_text(new_yaml)
    print(f"Wrote {YAML_PATH} ({len(new_yaml.splitlines())} lines)")

    mgr = DatabaseManager()
    sess = mgr.get_session()
    try:
        for row_id, _art_id, new, _sub, _old in db_updates:
            sess.execute(
                text(
                    "UPDATE subagent_evaluations "
                    "SET expected_count = :n, score = COALESCE(actual_count, 0) - :n "
                    "WHERE id = :id"
                ),
                {"n": new, "id": row_id},
            )
        sess.commit()
        print(f"Updated {len(db_updates)} db rows.")
    finally:
        sess.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
