#!/usr/bin/env python3
"""
Migration script to backfill canonical fields for existing SIGMA rules.

Computes canonical_json, exact_hash, canonical_text, and logsource_key
for all existing rules in the sigma_rules table.
"""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleTable
from src.services.sigma_novelty_service import SigmaNoveltyService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_rules(force: bool = False, limit: int = None, resume_from: int = 0):
    """
    Migrate existing rules to canonical form.

    Args:
        force: If True, recompute even if fields already exist
        limit: Maximum number of rules to process (None = all)
        resume_from: Resume from this rule ID (for checkpointing)
    """
    try:
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        # Initialize novelty service
        novelty_service = SigmaNoveltyService(db_session=session)

        # Query rules that need migration
        query = session.query(SigmaRuleTable)

        if not force:
            # Only process rules missing canonical fields
            query = query.filter(
                (SigmaRuleTable.canonical_json.is_(None))
                | (SigmaRuleTable.exact_hash.is_(None))
                | (SigmaRuleTable.logsource_key.is_(None))
            )

        if resume_from > 0:
            query = query.filter(SigmaRuleTable.id >= resume_from)

        if limit:
            query = query.limit(limit)

        rules = query.all()
        total = len(rules)

        logger.info(f"Processing {total} rules...")

        processed = 0
        errors = 0

        for rule in rules:
            try:
                # Build rule data dictionary
                rule_data = {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "description": rule.description,
                    "logsource": rule.logsource,
                    "detection": rule.detection,
                    "tags": rule.tags,
                    "level": rule.level,
                    "status": rule.status,
                }

                # Compute canonical fields
                canonical_rule = novelty_service.build_canonical_rule(rule_data)

                from dataclasses import asdict

                canonical_json = asdict(canonical_rule)
                exact_hash = novelty_service.generate_exact_hash(canonical_rule)
                canonical_text = novelty_service.generate_canonical_text(canonical_rule)
                logsource_key, _ = novelty_service.normalize_logsource(rule_data.get("logsource", {}))

                # Update rule
                rule.canonical_json = canonical_json
                rule.exact_hash = exact_hash
                rule.canonical_text = canonical_text
                rule.logsource_key = logsource_key

                processed += 1

                # Commit every 100 rules
                if processed % 100 == 0:
                    session.commit()
                    logger.info(f"Processed {processed}/{total} rules...")

            except Exception as e:
                logger.error(f"Error processing rule {rule.rule_id}: {e}")
                errors += 1
                continue

        # Final commit
        session.commit()

        logger.info(f"Migration complete: {processed} processed, {errors} errors")

        session.close()
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate SIGMA rules to canonical form")
    parser.add_argument("--force", action="store_true", help="Recompute even if fields exist")
    parser.add_argument("--limit", type=int, help="Maximum number of rules to process")
    parser.add_argument("--resume-from", type=int, default=0, help="Resume from this rule ID")

    args = parser.parse_args()

    success = migrate_rules(force=args.force, limit=args.limit, resume_from=args.resume_from)

    sys.exit(0 if success else 1)
