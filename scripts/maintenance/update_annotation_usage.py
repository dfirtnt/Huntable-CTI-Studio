#!/usr/bin/env python3
"""
Update annotation usage field directly in the database.

This script bypasses ORM-level immutability protection by using raw SQL.
Use with caution - only for administrative updates.
"""

import os
import sys

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text

from src.database.manager import DatabaseManager


def update_annotation_usage(annotation_ids: list[int], usage: str = "gold"):
    """
    Update annotation usage field for specified annotation IDs.

    Args:
        annotation_ids: List of annotation IDs to update
        usage: Target usage value ('train', 'eval', or 'gold')
    """
    if usage not in ("train", "eval", "gold"):
        raise ValueError(f"Invalid usage value: {usage}. Must be 'train', 'eval', or 'gold'")

    if not annotation_ids:
        print("No annotation IDs provided")
        return

    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        # First, verify the annotations exist
        # Use parameterized query with tuple for IN clause
        check_query = text("""
            SELECT id, usage, annotation_type 
            FROM article_annotations 
            WHERE id = ANY(:ids)
        """)
        result = session.execute(check_query, {"ids": annotation_ids})
        existing = result.fetchall()

        if len(existing) != len(annotation_ids):
            found_ids = {row[0] for row in existing}
            missing_ids = set(annotation_ids) - found_ids
            print(f"⚠️  Warning: {len(missing_ids)} annotation(s) not found: {missing_ids}")

        if not existing:
            print("❌ No annotations found to update")
            return

        # Show current state
        print("\n📋 Current state of annotations:")
        for row in existing:
            print(f"  ID {row[0]}: usage='{row[1]}', type='{row[2]}'")

        # Update the usage field
        update_query = text("""
            UPDATE article_annotations 
            SET usage = :usage, updated_at = NOW()
            WHERE id = ANY(:ids)
        """)

        result = session.execute(update_query, {"usage": usage, "ids": annotation_ids})
        session.commit()

        updated_count = result.rowcount
        print(f"\n✅ Updated {updated_count} annotation(s) to usage='{usage}'")

        # Verify the update
        verify_query = text("""
            SELECT id, usage 
            FROM article_annotations 
            WHERE id = ANY(:ids)
        """)
        verify_result = session.execute(verify_query, {"ids": annotation_ids})
        updated = verify_result.fetchall()

        print("\n📋 Updated state:")
        for row in updated:
            print(f"  ID {row[0]}: usage='{row[1]}'")

    except Exception as e:
        session.rollback()
        print(f"❌ Error updating annotations: {e}")
        raise
    finally:
        session.close()


def main():
    """CLI entry point."""
    # Annotation ID to mark as eval (correction: 292, not 992)
    annotation_ids = [292]
    usage = "eval"

    print(f"🔄 Updating {len(annotation_ids)} annotation(s) to usage='{usage}'")
    print(f"   IDs: {sorted(annotation_ids)}\n")

    update_annotation_usage(annotation_ids, usage)

    print("\n✅ Done")


if __name__ == "__main__":
    main()
