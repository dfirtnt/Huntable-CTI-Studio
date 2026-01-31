#!/usr/bin/env python3
"""
Migration script to re-index all existing SIGMA rules with section-based embeddings.

This script:
1. Loads all existing rules from the database
2. Generates section embeddings for each rule
3. Updates database records with new embeddings
4. Tracks progress for resume capability
5. Optionally compares old vs new similarity results

Usage:
    python scripts/migrate_sigma_embeddings.py [--force] [--limit N] [--resume-from N]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleTable
from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_sync_service import SigmaSyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def load_progress_checkpoint(checkpoint_file: str) -> int:
    """Load progress checkpoint from file."""
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file) as f:
                data = json.load(f)
                return data.get("last_processed_id", 0)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    return 0


def save_progress_checkpoint(checkpoint_file: str, last_id: int, processed: int, total: int):
    """Save progress checkpoint to file."""
    try:
        with open(checkpoint_file, "w") as f:
            json.dump(
                {
                    "last_processed_id": last_id,
                    "processed": processed,
                    "total": total,
                    "timestamp": datetime.now().isoformat(),
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.warning(f"Failed to save checkpoint: {e}")


def migrate_rules(force: bool = False, limit: int = None, resume_from: int = 0):
    """
    Migrate all existing SIGMA rules to use section-based embeddings.

    Args:
        force: If True, regenerate embeddings even if they exist
        limit: Maximum number of rules to process (None = all)
        resume_from: ID to resume from (for checkpoint recovery)
    """
    logger.info("Starting SIGMA rule embedding migration...")

    # Initialize services
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        sync_service = SigmaSyncService()
        embedding_service = LMStudioEmbeddingClient()

        # Get all rules
        query = session.query(SigmaRuleTable).filter(SigmaRuleTable.id > resume_from)

        if not force:
            # Only process rules without section embeddings
            query = query.filter(
                (SigmaRuleTable.title_embedding.is_(None))
                | (SigmaRuleTable.description_embedding.is_(None))
                | (SigmaRuleTable.tags_embedding.is_(None))
                | (SigmaRuleTable.logsource_embedding.is_(None))
                | (SigmaRuleTable.detection_structure_embedding.is_(None))
                | (SigmaRuleTable.detection_fields_embedding.is_(None))
            )

        # Order before limiting
        query = query.order_by(SigmaRuleTable.id)

        if limit:
            query = query.limit(limit)

        rules = query.all()
        total_rules = len(rules)

        logger.info(f"Found {total_rules} rules to migrate")

        if total_rules == 0:
            logger.info("No rules need migration")
            return

        checkpoint_file = "sigma_migration_checkpoint.json"
        processed = 0
        errors = 0

        for rule in rules:
            try:
                # Convert rule to rule_data format
                rule_data = {
                    "rule_id": rule.rule_id,
                    "title": rule.title,
                    "description": rule.description,
                    "tags": rule.tags if rule.tags else [],
                    "logsource": rule.logsource,
                    "detection": rule.detection,
                    "level": rule.level,
                    "status": rule.status,
                    "author": rule.author,
                    "date": rule.date,
                    "rule_references": rule.rule_references if rule.rule_references else [],
                    "false_positives": rule.false_positives if rule.false_positives else [],
                    "fields": rule.fields if rule.fields else [],
                }

                # Generate section embedding texts
                section_texts = sync_service.create_section_embeddings_text(rule_data)

                # Generate embeddings for each section (batch for efficiency)
                section_texts_list = [
                    section_texts["title"],
                    section_texts["description"],
                    section_texts["tags"],
                    section_texts["logsource"],
                    section_texts["detection_structure"],
                    section_texts["detection_fields"],
                ]

                section_embeddings = embedding_service.generate_embeddings_batch(section_texts_list)

                # Handle cases where batch might return fewer embeddings than expected
                while len(section_embeddings) < 6:
                    section_embeddings.append([0.0] * 768)  # Zero vector for missing sections

                # Validate embeddings are correct dimension before storing
                def safe_embedding(emb, index):
                    if emb and len(emb) == 768:
                        return emb
                    logger.warning(f"Invalid embedding for section {index}, using zero vector")
                    return [0.0] * 768

                # Update rule with new embeddings
                rule.title_embedding = safe_embedding(section_embeddings[0], 0)
                rule.description_embedding = safe_embedding(section_embeddings[1], 1)
                rule.tags_embedding = safe_embedding(section_embeddings[2], 2)
                rule.logsource_embedding = safe_embedding(section_embeddings[3], 3)
                rule.detection_structure_embedding = safe_embedding(section_embeddings[4], 4)
                rule.detection_fields_embedding = safe_embedding(section_embeddings[5], 5)

                processed += 1

                # Commit every 10 rules
                if processed % 10 == 0:
                    session.commit()
                    save_progress_checkpoint(checkpoint_file, rule.id, processed, total_rules)
                    logger.info(f"Processed {processed}/{total_rules} rules (last ID: {rule.id})")

            except Exception as e:
                errors += 1
                logger.error(f"Error processing rule {rule.rule_id} (ID: {rule.id}): {e}")
                session.rollback()
                continue

        # Final commit
        session.commit()
        save_progress_checkpoint(checkpoint_file, 0, processed, total_rules)  # Mark complete

        logger.info(f"Migration complete: {processed} rules processed, {errors} errors")

        # Clean up checkpoint file on success
        if errors == 0 and os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)
            logger.info("Checkpoint file removed (migration successful)")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def compare_similarity_methods(sample_rules: int = 5, rank_diff_threshold: int = 5):
    """
    Compare old vs new similarity methods on sample rules with mismatch logging.

    Tracks ranking positions and logs cases where ranking differs by more than N positions.

    Args:
        sample_rules: Number of sample rules to test
        rank_diff_threshold: Threshold for logging ranking differences (default 5)
    """
    logger.info(
        f"Comparing similarity methods on {sample_rules} sample rules (rank diff threshold: {rank_diff_threshold})..."
    )

    db_manager = DatabaseManager()
    session = db_manager.get_session()

    try:
        matching_service = SigmaMatchingService(session)

        # Get sample rules with both old and new embeddings
        rules = (
            session.query(SigmaRuleTable)
            .filter(SigmaRuleTable.embedding.isnot(None), SigmaRuleTable.title_embedding.isnot(None))
            .limit(sample_rules)
            .all()
        )

        all_mismatches = []
        significant_mismatches = []

        for rule in rules:
            rule_data = {
                "title": rule.title,
                "description": rule.description,
                "tags": rule.tags if rule.tags else [],
                "logsource": rule.logsource,
                "detection": rule.detection,
            }

            # Test OLD method (using main embedding)
            from src.services.sigma_sync_service import SigmaSyncService

            sync_service = SigmaSyncService()

            # Old method: single embedding
            old_embedding_text = sync_service.create_rule_embedding_text(rule_data)
            from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient

            embedding_client = LMStudioEmbeddingClient()
            old_embedding = embedding_client.generate_embedding(old_embedding_text)
            old_embedding_str = "[" + ",".join(map(str, old_embedding)) + "]"

            connection = session.connection()
            cursor = connection.connection.cursor()
            cursor.execute(
                """
                SELECT sr.rule_id, sr.title, 1 - (sr.embedding <=> %(embedding)s::vector) AS similarity
                FROM sigma_rules sr
                WHERE sr.embedding IS NOT NULL
                ORDER BY similarity DESC
                LIMIT 20
            """,
                {"embedding": old_embedding_str},
            )
            old_rows = cursor.fetchall()
            cursor.close()

            # Build old ranking
            old_ranking = {row[0]: (i + 1, float(row[2])) for i, row in enumerate(old_rows)}

            # Test NEW method (multi-vector)
            new_matches = matching_service.compare_proposed_rule_to_embeddings(rule_data, threshold=0.0)

            # Build new ranking
            new_ranking = {match["rule_id"]: (i + 1, match["similarity"]) for i, match in enumerate(new_matches)}

            # Compare rankings and find mismatches
            all_matched_rules = set(old_ranking.keys()) | set(new_ranking.keys())

            for matched_rule_id in all_matched_rules:
                old_pos = old_ranking.get(matched_rule_id, (None, None))[0]
                new_pos = new_ranking.get(matched_rule_id, (None, None))[0]
                old_sim = old_ranking.get(matched_rule_id, (None, None))[1]
                new_sim = new_ranking.get(matched_rule_id, (None, None))[1]

                if old_pos is not None and new_pos is not None:
                    rank_diff = abs(old_pos - new_pos)

                    mismatch = {
                        "query_rule_id": rule.rule_id,
                        "query_rule_title": rule.title,
                        "matched_rule_id": matched_rule_id,
                        "matched_rule_title": old_rows[old_pos - 1][1] if old_pos <= len(old_rows) else "Unknown",
                        "old_rank": old_pos,
                        "new_rank": new_pos,
                        "rank_diff": rank_diff,
                        "old_similarity": old_sim,
                        "new_similarity": new_sim,
                        "sim_diff": new_sim - old_sim if old_sim and new_sim else None,
                    }

                    all_mismatches.append(mismatch)

                    # Log significant mismatches (rank diff > threshold)
                    if rank_diff > rank_diff_threshold:
                        significant_mismatches.append(mismatch)
                        logger.warning(
                            f"Significant ranking change for rule {matched_rule_id}: "
                            f"Old rank {old_pos} -> New rank {new_pos} (diff: {rank_diff})"
                        )

        # Save comparison results
        output_file = f"similarity_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "sample_size": sample_rules,
                    "rank_diff_threshold": rank_diff_threshold,
                    "total_matches_compared": len(all_mismatches),
                    "significant_mismatches_count": len(significant_mismatches),
                    "all_mismatches": all_mismatches,
                    "significant_mismatches": significant_mismatches,
                    "summary": {
                        "total_rules_tested": len(rules),
                        "avg_rank_change": sum(m["rank_diff"] for m in all_mismatches if m["rank_diff"])
                        / len(all_mismatches)
                        if all_mismatches
                        else 0,
                        "max_rank_change": max((m["rank_diff"] for m in all_mismatches if m["rank_diff"]), default=0),
                        "improved_rankings": len([m for m in all_mismatches if m["new_rank"] < m["old_rank"]]),
                        "degraded_rankings": len([m for m in all_mismatches if m["new_rank"] > m["old_rank"]]),
                    },
                },
                f,
                indent=2,
            )

        logger.info("Comparison complete:")
        logger.info(f"  Total matches compared: {len(all_mismatches)}")
        logger.info(f"  Significant mismatches (diff > {rank_diff_threshold}): {len(significant_mismatches)}")
        logger.info(f"  Results saved to {output_file}")

    except Exception as e:
        logger.error(f"Comparison failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate SIGMA rules to section-based embeddings")
    parser.add_argument("--force", action="store_true", help="Force re-generation of embeddings")
    parser.add_argument("--limit", type=int, help="Limit number of rules to process")
    parser.add_argument("--resume-from", type=int, default=0, help="Resume from rule ID")
    parser.add_argument("--compare", action="store_true", help="Compare similarity methods after migration")
    parser.add_argument("--compare-only", action="store_true", help="Only run comparison, skip migration")
    parser.add_argument(
        "--rank-diff-threshold", type=int, default=5, help="Threshold for logging ranking differences (default: 5)"
    )

    args = parser.parse_args()

    if args.compare_only:
        compare_similarity_methods(rank_diff_threshold=args.rank_diff_threshold)
    else:
        migrate_rules(force=args.force, limit=args.limit, resume_from=args.resume_from)

        if args.compare:
            compare_similarity_methods(rank_diff_threshold=args.rank_diff_threshold)


if __name__ == "__main__":
    main()
