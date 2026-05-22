#!/usr/bin/env python3
"""
Build the ML model holdout evaluation set from curated labeled chunks.

Reads human-labeled chunk data from config/labeled_chunks/, applies schema
mapping and length filtering, and writes outputs/evaluation_data/eval_set.csv.

Run once on a fresh install (after seed_model.py) to activate the ModelEvaluator.
Re-run if new labeled source files are added to config/labeled_chunks/.

Usage:
    python scripts/prepare_eval_set.py
    python scripts/prepare_eval_set.py --min-length 500   # stricter filter
    python scripts/prepare_eval_set.py --dry-run          # show stats, skip write
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LABELED_CHUNKS_DIR = ROOT / "config" / "labeled_chunks"
DEFAULT_OUTPUT = ROOT / "outputs" / "evaluation_data" / "eval_set.csv"
DEFAULT_MIN_LENGTH = 200

# Maps source classification values → ModelEvaluator label values.
# ModelEvaluator validates against {"huntable", "not_huntable"} exactly.
LABEL_MAP = {
    "Huntable": "huntable",
    "Not Huntable": "not_huntable",
}

OUTPUT_FIELDS = [
    "annotation_id",
    "chunk_text",
    "label",
    "article_id",
    "source_file",
    "classification_date",
]


def load_source_files(source_dir: Path) -> list[dict]:
    """Load all CSV files from config/labeled_chunks/."""
    csv_files = sorted(source_dir.glob("*.csv"))
    if not csv_files:
        print(f"❌  No CSV files found in {source_dir}")
        sys.exit(1)

    all_rows = []
    for path in csv_files:
        with open(path) as f:
            rows = list(csv.DictReader(f))
        print(f"  {path.name}: {len(rows)} rows")
        for row in rows:
            row["_source_file"] = path.name
        all_rows.extend(rows)

    return all_rows


def build_eval_rows(source_rows: list[dict], min_length: int) -> tuple[list[dict], list[dict]]:
    """Map source schema → eval schema, drop rows below min_length."""
    kept = []
    dropped = []

    for i, row in enumerate(source_rows, start=1):
        text = row.get("highlighted_text", "").strip()
        raw_label = row.get("classification", "").strip()

        if len(text) < min_length:
            dropped.append({"length": len(text), "label": raw_label, "preview": text[:60]})
            continue

        label = LABEL_MAP.get(raw_label)
        if label is None:
            print(f"⚠️   Unknown label {raw_label!r} on row {i} — skipping")
            dropped.append({"length": len(text), "label": raw_label, "preview": text[:60]})
            continue

        kept.append({
            "annotation_id":       row.get("record_number", str(i)),
            "chunk_text":          text,
            "label":               label,
            "article_id":          0,   # source file has no DB article ID
            "source_file":         row["_source_file"],
            "classification_date": row.get("classification_date", ""),
        })

    return kept, dropped


def print_stats(kept: list[dict], dropped: list[dict]) -> None:
    from collections import Counter
    label_counts = Counter(r["label"] for r in kept)
    print(f"\n  Kept   : {len(kept)} rows")
    for label, count in sorted(label_counts.items()):
        print(f"    {label}: {count}")
    print(f"  Dropped: {len(dropped)} rows (below min-length or unknown label)")
    if kept:
        lengths = [len(r["chunk_text"]) for r in kept]
        print(f"  Lengths: min={min(lengths)}  max={max(lengths)}  mean={sum(lengths)//len(lengths)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build eval_set.csv from curated labeled chunks")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output CSV path")
    parser.add_argument("--min-length", type=int, default=DEFAULT_MIN_LENGTH,
                        help=f"Minimum chunk character length (default: {DEFAULT_MIN_LENGTH})")
    parser.add_argument("--dry-run", action="store_true", help="Show stats, skip writing")
    args = parser.parse_args()

    output_path = Path(args.output)

    print("🧪  Preparing ML model evaluation set")
    print("=" * 55)
    print(f"\n📂  Loading labeled chunks from {LABELED_CHUNKS_DIR} ...")

    source_rows = load_source_files(LABELED_CHUNKS_DIR)
    print(f"     {len(source_rows)} total rows across all source files")

    print(f"\n✂️   Filtering (min-length={args.min_length}) and mapping schema ...")
    kept, dropped = build_eval_rows(source_rows, args.min_length)
    print_stats(kept, dropped)

    if not kept:
        print("❌  No rows passed the filter — check source files and min-length setting.")
        sys.exit(1)

    if args.dry_run:
        print("\n🔍  [DRY RUN] Skipping write.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(kept)

    print(f"\n💾  Eval set written → {output_path}")
    print(f"     {len(kept)} rows  ({sum(1 for r in kept if r['label'] == 'huntable')} huntable"
          f" / {sum(1 for r in kept if r['label'] == 'not_huntable')} not_huntable)")
    print("\n✅  ModelEvaluator will use this set on the next retrain.")


if __name__ == "__main__":
    main()
