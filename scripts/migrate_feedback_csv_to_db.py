#!/usr/bin/env python3
"""
One-time migration script to import existing CSV feedback into database.
"""

import os
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).parent.parent / "src"))

from database.manager import DatabaseManager
from database.models import ChunkClassificationFeedbackTable


def migrate_csv_to_db():
    csv_file = "outputs/training_data/chunk_classification_feedback.csv"

    if not os.path.exists(csv_file):
        print("No CSV file to migrate")
        return

    df = pd.read_csv(csv_file)
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        migrated = 0
        for _, row in df.iterrows():
            feedback = ChunkClassificationFeedbackTable(
                article_id=int(row["article_id"]),
                chunk_id=int(row["chunk_id"]),
                chunk_text=row["chunk_text"],
                model_classification=row["model_classification"],
                model_confidence=float(row["model_confidence"]),
                model_reason=row.get("model_reason", ""),
                is_correct=bool(row["is_correct"]),
                user_classification=row.get("user_classification", ""),
                comment=row.get("comment", ""),
                used_for_training=bool(row.get("used_for_training", False)),
            )
            session.add(feedback)
            migrated += 1

        session.commit()
        print(f"✅ Migrated {migrated} feedback entries to database")

        # Backup and remove CSV
        backup_path = f"{csv_file}.migrated.bak"
        os.rename(csv_file, backup_path)
        print(f"📦 Backed up CSV to {backup_path}")

    except Exception as e:
        session.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    migrate_csv_to_db()
