#!/usr/bin/env python3
"""
Verify that gold/eval annotations were not used for training.
"""

import os
import sys

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text
from src.database.manager import DatabaseManager


def verify_training_usage():
    """Check which annotations were used for training."""
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    try:
        # Check gold annotations
        gold_query = text("""
            SELECT id, usage, used_for_training, annotation_type
            FROM article_annotations 
            WHERE usage = 'gold' AND annotation_type = 'CMD'
            ORDER BY id
        """)
        gold_result = session.execute(gold_query)
        gold_annotations = gold_result.fetchall()
        
        # Check eval annotations
        eval_query = text("""
            SELECT id, usage, used_for_training, annotation_type
            FROM article_annotations 
            WHERE usage = 'eval' AND annotation_type = 'CMD'
            ORDER BY id
        """)
        eval_result = session.execute(eval_query)
        eval_annotations = eval_result.fetchall()
        
        # Check train annotations that were used
        train_used_query = text("""
            SELECT id, usage, used_for_training, annotation_type
            FROM article_annotations 
            WHERE usage = 'train' AND annotation_type = 'CMD' AND used_for_training = TRUE
            ORDER BY id
        """)
        train_used_result = session.execute(train_used_query)
        train_used_annotations = train_used_result.fetchall()
        
        print("=" * 80)
        print("TRAINING USAGE VERIFICATION")
        print("=" * 80)
        
        # Gold annotations
        print(f"\n📊 GOLD Annotations (should NOT be used for training):")
        print(f"   Total: {len(gold_annotations)}")
        gold_used = [ann for ann in gold_annotations if ann[2] is True]
        gold_unused = [ann for ann in gold_annotations if ann[2] is False]
        print(f"   ✅ Unused: {len(gold_unused)}")
        print(f"   ❌ Used: {len(gold_used)}")
        if gold_used:
            print(f"   ⚠️  WARNING: {len(gold_used)} gold annotation(s) marked as used:")
            for ann in gold_used:
                print(f"      ID {ann[0]}: used_for_training={ann[2]}")
        else:
            print(f"   ✅ All gold annotations correctly excluded from training")
        
        # Eval annotations
        print(f"\n📊 EVAL Annotations (should NOT be used for training):")
        print(f"   Total: {len(eval_annotations)}")
        eval_used = [ann for ann in eval_annotations if ann[2] is True]
        eval_unused = [ann for ann in eval_annotations if ann[2] is False]
        print(f"   ✅ Unused: {len(eval_unused)}")
        print(f"   ❌ Used: {len(eval_used)}")
        if eval_used:
            print(f"   ⚠️  WARNING: {len(eval_used)} eval annotation(s) marked as used:")
            for ann in eval_used:
                print(f"      ID {ann[0]}: used_for_training={ann[2]}")
        else:
            print(f"   ✅ All eval annotations correctly excluded from training")
        
        # Train annotations used
        print(f"\n📊 TRAIN Annotations (used for training):")
        print(f"   Total used: {len(train_used_annotations)}")
        if len(train_used_annotations) > 0:
            print(f"   ✅ Training used {len(train_used_annotations)} train annotations")
            print(f"   Sample IDs (first 10): {[ann[0] for ann in train_used_annotations[:10]]}")
        
        # Summary
        print(f"\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        if gold_used or eval_used:
            print(f"❌ ISSUE FOUND: Some gold/eval annotations were used for training!")
            print(f"   Gold used: {len(gold_used)}")
            print(f"   Eval used: {len(eval_used)}")
        else:
            print(f"✅ VERIFIED: No gold/eval annotations were used for training")
            print(f"   Gold annotations: {len(gold_annotations)} total, all unused")
            print(f"   Eval annotations: {len(eval_annotations)} total, all unused")
            print(f"   Train annotations: {len(train_used_annotations)} used for training")
        
    except Exception as e:
        print(f"❌ Error verifying training usage: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    verify_training_usage()



