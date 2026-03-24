"""Migration: Add healing_events table for AI healing audit trail."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect

from src.database.manager import DatabaseManager
from src.database.models import HealingEventTable


def migrate():
    db = DatabaseManager()
    engine = db.engine
    inspector = inspect(engine)

    if "healing_events" not in inspector.get_table_names():
        HealingEventTable.__table__.create(engine)
        print("Created healing_events table")
    else:
        print("healing_events table already exists")


if __name__ == "__main__":
    migrate()
