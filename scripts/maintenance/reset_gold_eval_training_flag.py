#!/usr/bin/env python3
"""
Reset used_for_training flag for gold/eval annotations.

These annotations should NOT be used for training, so we need to reset
the flag if it was incorrectly set.
"""

import os
import sys

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sqlalchemy import text
from src.database.manager import DatabaseManager


def reset_training_flags():
    """Reset used_for_training flag for gold/eval annotations."""
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    try:
        # Check current state
        check_query = text("""
            SELECT usage, COUNT(*) as count, SUM(CASE WHEN used_for_training THEN 1 ELSE 0 END) as used_count
            FROM article_annotations 
            WHERE annotation_type = 'CMD' AND usage IN ('gold', 'eval')
            GROUP BY usage
        """)
        result = session.execute(check_query)
        before_state = result.fetchall()
        
        print("Before reset:")
        for row in before_state:
            print(f"  {row[0]}: {row[1]} total, {row[2]} marked as used")
        
        # Reset the flag for gold/eval annotations
        reset_query = text("""
            UPDATE article_annotations 
            SET used_for_training = FALSE
            WHERE annotation_type = 'CMD' 
            AND usage IN ('gold', 'eval')
            AND used_for_training = TRUE
        """)
        
        result = session.execute(reset_query)
        session.commit()
        
        updated_count = result.rowcount
        print(f"\n✅ Reset used_for_training flag for {updated_count} annotation(s)")
        
        # Verify after reset
        verify_query = text("""
            SELECT usage, COUNT(*) as count, SUM(CASE WHEN used_for_training THEN 1 ELSE 0 END) as used_count
            FROM article_annotations 
            WHERE annotation_type = 'CMD' AND usage IN ('gold', 'eval')
            GROUP BY usage
        """)
        verify_result = session.execute(verify_query)
        after_state = verify_result.fetchall()
        
        print("\nAfter reset:")
        for row in after_state:
            print(f"  {row[0]}: {row[1]} total, {row[2]} marked as used")
        
        if all(row[2] == 0 for row in after_state):
            print("\n✅ All gold/eval annotations now correctly marked as unused for training")
        else:
            print("\n⚠️  Some annotations still marked as used")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error resetting training flags: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    reset_training_flags()





