#!/usr/bin/env python3
"""
Seed the junk-filter ML model from the bundled eval article fixtures.

Run once on a fresh install or after a restore when models/content_filter.pkl
is missing.  Chunks each fixture article exactly as production does, labels
chunks against the ground-truth expected_items, then trains and saves the model.

Usage:
    python scripts/seed_model.py
    python scripts/seed_model.py --model-path models/content_filter.pkl
    python scripts/seed_model.py --dry-run          # show corpus stats, skip training
    python scripts/seed_model.py --no-register      # skip DB version registration
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.utils.content_filter import ContentFilter

FIXTURES_DIR = ROOT / "config" / "eval_articles_data"
DEFAULT_MODEL_PATH = "models/content_filter.pkl"
CHUNK_SIZE = 1000
OVERLAP = 200


def load_fixture_categories() -> list[dict]:
    """Load articles + ground truth from every fixture category."""
    categories = sorted(
        d
        for d in FIXTURES_DIR.iterdir()
        if d.is_dir() and (d / "articles.json").exists() and (d / "ground_truth.json").exists()
    )
    if not categories:
        print(f"❌  No fixture categories found under {FIXTURES_DIR}")
        sys.exit(1)

    result = []
    for cat_dir in categories:
        articles = json.loads((cat_dir / "articles.json").read_text())
        ground_truths = json.loads((cat_dir / "ground_truth.json").read_text())

        gt_by_url: dict[str, list[str]] = {
            g["url"]: [item.lower() for item in g.get("expected_items", [])] for g in ground_truths
        }

        for article in articles:
            url = article.get("url", "")
            content = article.get("content", "").strip()
            if not content:
                continue
            result.append(
                {
                    "category": cat_dir.name,
                    "url": url,
                    "content": content,
                    "expected_items": gt_by_url.get(url, []),
                }
            )

        print(f"  {cat_dir.name}: {len(articles)} articles")

    return result


def build_training_dataframe(fixture_articles: list[dict], cf: ContentFilter) -> pd.DataFrame:
    """Chunk articles and label each chunk from ground truth.

    Two sources of huntable signal:
    1. Full-length chunks that contain a ground-truth expected_item — realistic
       feature distribution, good "not huntable" samples for free.
    2. The expected_items themselves as direct huntable rows — boosts huntable
       count so the classifier isn't overwhelmed by the not-huntable majority.
    """
    rows: list[dict] = []
    chunk_huntable = 0
    chunk_not_huntable = 0
    direct_huntable = 0

    # Pass 1: full-length labeled chunks (realistic feature distribution)
    for article in fixture_articles:
        chunks = cf.chunk_content(article["content"], CHUNK_SIZE, OVERLAP)
        expected_lower = article["expected_items"]  # already lowercased

        for _start, _end, chunk_text in chunks:
            chunk_lower = chunk_text.lower()
            is_huntable = any(item in chunk_lower for item in expected_lower)
            label = "Huntable" if is_huntable else "Not Huntable"
            rows.append({"highlighted_text": chunk_text, "classification": label})
            if is_huntable:
                chunk_huntable += 1
            else:
                chunk_not_huntable += 1

    # Pass 2: expected_items verbatim — boosts huntable signal
    # Re-read ground truth to get original-case text.
    cats = sorted(d for d in FIXTURES_DIR.iterdir() if d.is_dir() and (d / "ground_truth.json").exists())
    for cat_dir in cats:
        ground_truths = json.loads((cat_dir / "ground_truth.json").read_text())
        for g in ground_truths:
            for item in g.get("expected_items", []):
                if item.strip():
                    rows.append({"highlighted_text": item, "classification": "Huntable"})
                    direct_huntable += 1

    total_huntable = chunk_huntable + direct_huntable
    total = total_huntable + chunk_not_huntable
    print(f"\n  Corpus: {total} rows across {len(fixture_articles)} articles")
    print(f"    Huntable (chunks):  {chunk_huntable:>5}")
    print(f"    Huntable (direct):  {direct_huntable:>5}  ← expected_items added verbatim")
    print(f"    Not Huntable:       {chunk_not_huntable:>5}")
    print(f"    Total huntable:     {total_huntable:>5} ({total_huntable / total * 100:.1f}%)")

    return pd.DataFrame(rows)


async def register_version(model_path: str, training_result: dict, sample_count: int) -> int | None:
    """Save a version record to the DB. Returns version id or None on failure."""
    import shutil

    try:
        from src.database.async_manager import AsyncDatabaseManager
        from src.utils.model_versioning import MLModelVersionManager

        db = AsyncDatabaseManager(pool_size=2, max_overflow=0)
        try:
            vm = MLModelVersionManager(db)
            version_id = await vm.save_model_version(
                metrics=training_result,
                _training_config={"source": "seed_model", "fixtures": str(FIXTURES_DIR)},
                feedback_count=0,
                model_file_path=model_path,
            )
            # Copy to a versioned artifact so rollback can restore this baseline
            versioned_path = str(Path(model_path).parent / f"content_filter_v{version_id}.pkl")
            shutil.copy2(model_path, versioned_path)
            await vm.set_version_artifact(version_id, versioned_path)
            return version_id
        finally:
            await db.close()
    except Exception as exc:
        print(f"⚠️   DB version registration skipped: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the junk-filter ML model from fixture data")
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH, help="Where to write the pkl")
    parser.add_argument("--dry-run", action="store_true", help="Build corpus and print stats, skip training")
    parser.add_argument("--no-register", action="store_true", help="Skip DB version registration")
    args = parser.parse_args()

    model_path = str(ROOT / args.model_path) if not os.path.isabs(args.model_path) else args.model_path

    print("🌱  Seeding ML junk-filter model from eval fixtures")
    print("=" * 55)

    if not args.dry_run and os.path.exists(model_path):
        print(f"⚠️   Model already exists at {model_path}")
        print("    Pass --dry-run to inspect corpus stats, or delete the file first.")
        sys.exit(0)

    print("\n📂  Loading fixture categories...")
    fixture_articles = load_fixture_categories()

    print("\n🔪  Chunking articles and labelling from ground truth...")
    cf = ContentFilter(model_path=model_path, feature_version="v3")
    df = build_training_dataframe(fixture_articles, cf)

    if df.empty:
        print("❌  No training samples produced — check fixture content fields.")
        sys.exit(1)

    if args.dry_run:
        print("\n🔍  [DRY RUN] Skipping training.")
        return

    # Save the labelled corpus alongside the model for auditability
    corpus_path = Path(model_path).parent / "seed_training_data.csv"
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(corpus_path, index=False)
    print(f"\n💾  Corpus saved → {corpus_path}")

    # Also populate the combined_training_data path that retrain_with_feedback.py
    # reads as its baseline so the first retrain uses normal-path (not seed-fallback).
    combined_path = ROOT / "outputs" / "training_data" / "combined_training_data.csv"
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(combined_path, index=False)
    print(f"💾  Combined training data saved → {combined_path}")

    print("\n🤖  Training RandomForest classifier...")
    training_result = cf.train_model(str(corpus_path))

    if not training_result or not training_result.get("success"):
        err = (training_result or {}).get("error", "unknown error")
        print(f"❌  Training failed: {err}")
        sys.exit(1)

    print(f"✅  Model trained  accuracy={training_result.get('accuracy', 0):.3f}")
    print(
        f"    F1 (huntable)={training_result.get('f1_score_huntable', 0):.3f}  "
        f"recall={training_result.get('recall_huntable', 0):.3f}"
    )
    print(f"    Saved → {model_path}")

    if not args.no_register:
        print("\n📝  Registering model version in database...")
        version_id = asyncio.run(register_version(model_path, training_result, len(df)))
        if version_id:
            print(f"    Version id: {version_id}")

    # Build (or refresh) the curated holdout eval set from config/labeled_chunks/.
    # This runs automatically so fresh installs get a working quality gate without
    # a separate manual step.  Failures are warnings only — the model is already saved.
    print("\n🧪  Building holdout eval set from config/labeled_chunks/ ...")
    try:
        import subprocess as _sp
        _prepare = ROOT / "scripts" / "prepare_eval_set.py"
        _result = _sp.run(
            [sys.executable, str(_prepare)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        for _line in _result.stdout.strip().splitlines():
            print(f"  {_line}")
        if _result.returncode != 0:
            print(f"⚠️   prepare_eval_set.py exited {_result.returncode}")
            if _result.stderr:
                print(_result.stderr.strip()[:400])
            print("    Run manually:  python3 scripts/prepare_eval_set.py")
    except Exception as _exc:
        print(f"⚠️   Could not build eval set: {_exc}")
        print("    Run:  python3 scripts/prepare_eval_set.py")

    print("\n🎉  Seed complete. Restart the server to activate the new model.")


if __name__ == "__main__":
    main()
