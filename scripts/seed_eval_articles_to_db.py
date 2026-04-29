#!/usr/bin/env python3
"""
Seed eval articles from config/eval_articles_data into the database.

Reads all articles.json files under config/eval_articles_data/, deduplicates by URL,
and inserts any article not already present (by canonical_url). Uses a dedicated
source "eval_articles" so eval articles appear in the Articles list and the regular
workflow can process them.

Run after DB is up (e.g. from start.sh or manually):
  python3 scripts/seed_eval_articles_to_db.py
  .venv/bin/python scripts/seed_eval_articles_to_db.py

The web app also runs this seed at startup so eval articles are present after a
fresh DB / rehydration (e.g. rebuilt Docker volumes).
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.services.seed_eval_articles import cleanup_stale_eval_results, run


def main() -> int:
    created, errors, reason = run(project_root=project_root)
    if created:
        print(f"Seeded {created} eval article(s) into DB.")
    elif errors:
        print(f"Errors during seed: {errors}")
    elif reason == "already_present":
        print("No new eval articles to seed (all already present in DB).")
    elif reason == "no_config_data":
        print("No eval articles to seed (no config data: config/eval_articles_data/*/articles.json missing or empty).")
    else:
        print("No new eval articles to seed.")

    deleted = cleanup_stale_eval_results(project_root=project_root)
    if deleted:
        print(f"Removed {deleted} stale eval result(s) from DB.")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
