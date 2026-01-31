#!/usr/bin/env python3
"""
Check training dataset files to verify which annotation IDs were actually included.
"""

import json
import os
import sys
from pathlib import Path

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text

from src.database.manager import DatabaseManager


def check_training_datasets():
    """Check training dataset files for gold/eval annotation IDs."""

    # Get gold/eval annotation IDs
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        # Get gold annotation IDs
        gold_query = text("""
            SELECT id FROM article_annotations 
            WHERE usage = 'gold' AND annotation_type = 'CMD'
            ORDER BY id
        """)
        gold_result = session.execute(gold_query)
        gold_ids = {row[0] for row in gold_result.fetchall()}

        # Get eval annotation IDs
        eval_query = text("""
            SELECT id FROM article_annotations 
            WHERE usage = 'eval' AND annotation_type = 'CMD'
            ORDER BY id
        """)
        eval_result = session.execute(eval_query)
        eval_ids = {row[0] for row in eval_result.fetchall()}

        print("=" * 80)
        print("TRAINING DATASET VERIFICATION")
        print("=" * 80)
        print(f"\nGold annotation IDs: {sorted(gold_ids)}")
        print(f"Eval annotation IDs: {sorted(eval_ids)}")

        # Check training dataset files
        dataset_dir = Path("outputs/evaluation_data/observables/cmd")
        if not dataset_dir.exists():
            print(f"\n❌ Dataset directory not found: {dataset_dir}")
            return

        training_files = sorted(dataset_dir.glob("cmd_*.jsonl"), reverse=True)

        if not training_files:
            print(f"\n❌ No training dataset files found in {dataset_dir}")
            return

        print(f"\n📁 Found {len(training_files)} training dataset file(s)")

        for dataset_file in training_files[:3]:  # Check most recent 3
            print(f"\n{'=' * 80}")
            print(f"Checking: {dataset_file.name}")
            print(f"{'=' * 80}")

            dataset_ids = set()
            gold_found = []
            eval_found = []

            with open(dataset_file, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        record = json.loads(line.strip())
                        ann_id = record.get("annotation_id")
                        usage = record.get("usage", "unknown")

                        if ann_id:
                            dataset_ids.add(ann_id)

                            if ann_id in gold_ids:
                                gold_found.append((ann_id, usage, line_num))
                            if ann_id in eval_ids:
                                eval_found.append((ann_id, usage, line_num))
                    except json.JSONDecodeError as e:
                        print(f"  ⚠️  Error parsing line {line_num}: {e}")
                        continue

            print(f"  Total annotations in dataset: {len(dataset_ids)}")

            if gold_found:
                print(f"  ❌ FOUND {len(gold_found)} GOLD annotation(s) in training dataset:")
                for ann_id, usage, line_num in gold_found:
                    print(f"     ID {ann_id} (usage={usage}) at line {line_num}")
            else:
                print("  ✅ No gold annotations found in this dataset")

            if eval_found:
                print(f"  ❌ FOUND {len(eval_found)} EVAL annotation(s) in training dataset:")
                for ann_id, usage, line_num in eval_found:
                    print(f"     ID {ann_id} (usage={usage}) at line {line_num}")
            else:
                print("  ✅ No eval annotations found in this dataset")

        # Summary
        print(f"\n{'=' * 80}")
        print("SUMMARY")
        print(f"{'=' * 80}")

        all_gold_found = set()
        all_eval_found = set()
        for dataset_file in training_files[:3]:
            with open(dataset_file, encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        ann_id = record.get("annotation_id")
                        if ann_id in gold_ids:
                            all_gold_found.add(ann_id)
                        if ann_id in eval_ids:
                            all_eval_found.add(ann_id)
                    except:
                        continue

        if all_gold_found or all_eval_found:
            print("❌ ISSUE CONFIRMED: Gold/eval annotations WERE included in training datasets")
            if all_gold_found:
                print(f"   Gold IDs found: {sorted(all_gold_found)}")
            if all_eval_found:
                print(f"   Eval IDs found: {sorted(all_eval_found)}")
            print("\n   The training code needs to be fixed to exclude gold/eval annotations.")
        else:
            print("✅ VERIFIED: No gold/eval annotations found in training datasets")
            print("   Training code correctly excludes gold/eval annotations")

    except Exception as e:
        print(f"❌ Error checking training datasets: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    check_training_datasets()
