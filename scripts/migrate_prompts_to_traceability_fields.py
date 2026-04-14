#!/usr/bin/env python3
"""Migrate agent_prompts JSONB to the unified traceability field schema.

Context
-------
The extract sub-agent contract was unified so that every extracted item carries:
  - value
  - source_evidence          (replaces raw_text_snippet)
  - extraction_justification (new, required)
  - confidence_score         (replaces confidence_level)

The runtime _traceability_block in src/services/llm_service.py was already
enforcing the new names. The prompt files in src/prompts/ were updated to match.
However, existing installs that already seeded the DB from the OLD prompt files
have stale copies inside agentic_workflow_config.agent_prompts (JSONB). Those
stored prompts still reference raw_text_snippet / confidence_level and will
contradict the runtime traceability block until refreshed.

This script refreshes the five affected agents' prompt strings in every row of
agentic_workflow_config from the current on-disk source:

  RegistryExtract, ServicesExtract, ProcTreeExtract, RegistryQA, ServicesQA

Safety properties
-----------------
- Idempotent: re-running after a successful migration is a no-op (detected by
  absence of deprecated field names in the stored prompt).
- Scoped: only the five agents listed above are touched. Every other agent's
  customized prompt is preserved exactly.
- Active-row-only by default: `agentic_workflow_config` retains every past
  version as an inactive history row. Rewriting those rows would corrupt the
  audit trail / rollback UI because they should reflect what actually ran at
  the time. Pass --include-inactive only if you explicitly want to refresh
  history too (rarely correct).
- Preserves existing `instructions` sibling field per agent entry.
- Dry-run supported via --dry-run; default is to apply.
- Emits a per-row, per-agent summary for audit.
- Does NOT touch historical workflow_execution_results; those render via
  templates that already handle the old field names gracefully.

Usage
-----
  DATABASE_URL=postgresql://... python3 scripts/migrate_prompts_to_traceability_fields.py
  DATABASE_URL=postgresql://... python3 scripts/migrate_prompts_to_traceability_fields.py --dry-run
  DATABASE_URL=postgresql://... python3 scripts/migrate_prompts_to_traceability_fields.py --include-inactive

Exit codes
----------
  0  success (including no-op re-run)
  1  failure (DB unreachable, prompt file missing, unexpected schema, etc.)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = REPO_ROOT / "src" / "prompts"

# Only the agents whose prompts were rewritten for the traceability contract.
# Touching anything else risks overwriting user customizations.
MIGRATED_AGENTS: tuple[str, ...] = (
    "RegistryExtract",
    "ServicesExtract",
    "ProcTreeExtract",
    "RegistryQA",
    "ServicesQA",
)

DEPRECATED_FIELDS: tuple[str, ...] = ("raw_text_snippet", "confidence_level")


def _load_prompt_text(agent_name: str) -> str:
    """Return the on-disk prompt file as a UTF-8 string.

    Validates that the file parses as JSON so we never store a malformed prompt.
    """
    path = PROMPT_DIR / agent_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Prompt file {path} is not valid JSON: {exc}") from exc
    return raw


def _needs_migration(stored_prompt: str | None) -> bool:
    """True if the stored prompt still references deprecated field names."""
    if not stored_prompt:
        # Missing stored prompt: a fresh seed on next boot will populate from
        # the on-disk file, so nothing to do here.
        return False
    return any(field in stored_prompt for field in DEPRECATED_FIELDS)


def _resolve_database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if not url:
        return None
    # SQLAlchemy here uses the sync driver (psycopg2); strip asyncpg suffix if
    # the env var was prepared for the async app runtime.
    if "asyncpg" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def run_migration(dry_run: bool = False, include_inactive: bool = False) -> bool:
    database_url = _resolve_database_url()
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Preload all new prompt strings up front so a missing file fails fast,
    # before any DB writes.
    new_prompts: dict[str, str] = {}
    for agent in MIGRATED_AGENTS:
        try:
            new_prompts[agent] = _load_prompt_text(agent)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Cannot load prompt for %s: %s", agent, exc)
            return False

    try:
        engine = create_engine(database_url)
    except Exception as exc:
        logger.error("Failed to create DB engine: %s", exc)
        return False

    total_rows = 0
    total_updates = 0
    total_already_current = 0

    try:
        with engine.begin() as conn:
            # Default: only migrate the active row. Inactive rows are history
            # snapshots; rewriting them would corrupt the rollback audit trail.
            query = (
                "SELECT id, version, is_active, agent_prompts "
                "FROM agentic_workflow_config "
            )
            if not include_inactive:
                query += "WHERE is_active = TRUE "
            query += "ORDER BY id"
            rows = conn.execute(text(query)).fetchall()

            if not rows:
                scope = "rows" if include_inactive else "active rows"
                logger.info("No %s in agentic_workflow_config; nothing to migrate.", scope)
                return True
            logger.info(
                "Scanning %d row(s) (include_inactive=%s).", len(rows), include_inactive
            )

            for row in rows:
                total_rows += 1
                row_id, version, is_active, agent_prompts = row
                agent_prompts = agent_prompts or {}

                logger.info(
                    "Row id=%s version=%s is_active=%s",
                    row_id,
                    version,
                    is_active,
                )

                for agent in MIGRATED_AGENTS:
                    entry = agent_prompts.get(agent)
                    if not isinstance(entry, dict):
                        # Agent not present in this row's prompts: nothing to
                        # migrate. The on-disk file will be used on next seed
                        # for rows that do not have this key.
                        logger.info("  %s: not present in agent_prompts, skipping", agent)
                        continue

                    stored = entry.get("prompt")
                    if not _needs_migration(stored):
                        total_already_current += 1
                        logger.info("  %s: already on new contract, skipping", agent)
                        continue

                    # Preserve the sibling `instructions` value if present.
                    instructions = entry.get("instructions", "")
                    new_entry = {"prompt": new_prompts[agent], "instructions": instructions}

                    logger.info(
                        "  %s: MIGRATE (deprecated fields present: %s)",
                        agent,
                        ", ".join(f for f in DEPRECATED_FIELDS if f in (stored or "")),
                    )

                    if dry_run:
                        total_updates += 1
                        continue

                    # jsonb_set with create_missing=false: we already confirmed
                    # the key exists, so this only overwrites; it never injects
                    # into a row that chose to delete this agent.
                    conn.execute(
                        text(
                            "UPDATE agentic_workflow_config "
                            "SET agent_prompts = jsonb_set("
                            "  agent_prompts, :path, :new_value::jsonb, false"
                            "), "
                            "updated_at = NOW() "
                            "WHERE id = :row_id"
                        ),
                        {
                            "path": "{" + agent + "}",
                            "new_value": json.dumps(new_entry),
                            "row_id": row_id,
                        },
                    )
                    total_updates += 1

            if dry_run:
                # Roll back any accidental writes; engine.begin() would
                # otherwise commit on clean exit. We explicitly raise so the
                # context manager rolls back.
                raise _DryRunRollback()

    except _DryRunRollback:
        logger.info("Dry run: transaction rolled back.")
    except Exception as exc:
        logger.error("Migration failed: %s", exc, exc_info=True)
        return False

    logger.info(
        "Summary: rows_scanned=%d agent_updates=%d already_current=%d (dry_run=%s)",
        total_rows,
        total_updates,
        total_already_current,
        dry_run,
    )
    return True


class _DryRunRollback(Exception):
    """Sentinel used to force a rollback when --dry-run is set."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the DB.",
    )
    parser.add_argument(
        "--include-inactive",
        action="store_true",
        help=(
            "Also migrate inactive (historical) config rows. Default is active-row only; "
            "inactive rows are history snapshots and rewriting them corrupts the rollback audit trail."
        ),
    )
    args = parser.parse_args()

    ok = run_migration(dry_run=args.dry_run, include_inactive=args.include_inactive)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
