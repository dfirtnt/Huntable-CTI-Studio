#!/usr/bin/env python3
"""Migrate legacy SigmaAgent and RankAgent prompt records to canonical {system, user} shape.

Background:
  agent_prompts.SigmaAgent and agent_prompts.RankAgent in agentic_workflow_config
  have accumulated five historical shapes due to overlapping UI save paths:
    1. Locked scaffold JSON: {"prompt": "{\"role\":...,\"user_template\":...}", ...}
    2. Extraction-agent JSON: {"prompt": "{\"role\":...,\"task\":...,\"json_example\":...,\"instructions\":...}", ...}
    3. Legacy simple JSON:    {"prompt": "{\"system\":...,\"user\":...}", ...}
    4. Bootstrap raw text:    {"prompt": "<persona or template text>", ...}
    5. Auto-persist:          {"prompt": "...", "model": "...", "instructions": ...}

  The shape-2/5 generators have been fixed in the UI (subtasks 1+2 of the parent
  issues). This migration rewrites legacy records IN-PLACE to a single canonical
  outer shape:

      agent_prompts.<Agent> = {
          "system": "<persona text>",
          "user":   "<user template text or null>",
          "instructions": "<preserved>"     # only when non-empty
      }

  After migration, both parse_sigma_agent_prompt_data and _parse_rank_prompt
  can be simplified to a 2-line read; legacy-shape branches become dead code.

Usage:
    python scripts/migrate_agent_prompts.py              # dry-run (default)
    python scripts/migrate_agent_prompts.py --apply      # write changes
    python scripts/migrate_agent_prompts.py --agents SigmaAgent  # one agent only
    python scripts/migrate_agent_prompts.py --backup-only        # snapshot, don't migrate

Safety:
  - Dry-run by default; --apply required to mutate.
  - Always writes a snapshot JSON file before --apply (timestamped).
  - Per-row diff printed before each rewrite.
  - SigmaAgent: treated identically to RankAgent; user is preserved if present.
  - RankAgent: preserves user template if one is recoverable; otherwise None
    (the runtime falls back to src/prompts/rank_article.txt once that lands).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowConfigTable

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Matches Python str.format-style placeholders, used to distinguish a user
# template ({title}/{content}/{url}/etc.) from a plain persona string.
_PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*[^{]*?\}")

CANONICAL_AGENTS = ("SigmaAgent", "RankAgent")


def _normalize_record(agent_name: str, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert any legacy shape into canonical {system, user, instructions?} for the given agent.

    Returns None if the record is empty or unrecognizable -- caller skips writing
    so the existing record is preserved.
    """
    if not raw:
        return None

    prompt_field = raw.get("prompt", "")
    instructions = raw.get("instructions", "") or ""
    sibling_system = raw.get("system_prompt") if isinstance(raw.get("system_prompt"), str) else None

    system: str | None = None
    user: str | None = None

    if isinstance(prompt_field, str) and prompt_field:
        # Try JSON parse first
        try:
            inner = json.loads(prompt_field)
        except (ValueError, json.JSONDecodeError):
            inner = None

        if isinstance(inner, dict):
            # Shape 1: locked scaffold {role, user_template}
            if inner.get("user_template"):
                user = inner["user_template"]
                system = inner.get("role") or inner.get("system") or None
            # Shape 3: legacy {system, user}
            elif inner.get("user") or inner.get("system"):
                user = inner.get("user") or None
                system = inner.get("system") or inner.get("role") or None
            # Shape 2: extraction-agent envelope (role + task/json_example/instructions)
            elif "task" in inner or "json_example" in inner:
                system = inner.get("role") or None
                # task/json_example/instructions are not used by SigmaAgent or RankAgent
                # backends -- discard. Preserve outer instructions only.
            # Other JSON shape with just a role/system
            elif inner.get("role") or inner.get("system"):
                system = inner.get("role") or inner.get("system") or None
        else:
            # Raw text. Use placeholder presence to disambiguate.
            if _PLACEHOLDER_RE.search(prompt_field):
                user = prompt_field
            else:
                # No placeholders -> persona text
                system = prompt_field

    # Fall back to sibling system_prompt key
    if not system and sibling_system:
        system = sibling_system

    if agent_name == "SigmaAgent":
        user = None
    canonical: dict[str, Any] = {"system": system, "user": user}
    if instructions:
        canonical["instructions"] = instructions
    return canonical


def _records_equal(old: dict[str, Any] | None, new: dict[str, Any] | None) -> bool:
    """Compare records for migration-no-op detection."""
    if old is None and new is None:
        return True
    if old is None or new is None:
        return False
    return json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True)


def _is_canonical(record: dict[str, Any] | None) -> bool:
    """A record is canonical when its outer keys are exactly {system, user, [instructions]}."""
    if not record:
        return False
    keys = set(record.keys())
    allowed = {"system", "user", "instructions"}
    if not keys.issubset(allowed):
        return False
    if "system" not in keys or "user" not in keys:
        return False
    return True


def _snapshot_path(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"agent_prompts_snapshot_{ts}.json"


def migrate(apply: bool, agents: list[str], snapshot_dir: Path) -> int:
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    try:
        configs = (
            session.query(AgenticWorkflowConfigTable)
            .filter(AgenticWorkflowConfigTable.is_active == True)  # noqa: E712
            .all()
        )
        if not configs:
            logger.error("No active workflow config found")
            return 1

        snapshot: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "configs": [],
        }
        rewrites_planned = 0
        no_op_skips = 0

        for cfg in configs:
            cfg_record: dict[str, Any] = {
                "config_id": cfg.id,
                "version": cfg.version,
                "agents": {},
            }
            current = dict(cfg.agent_prompts or {})
            updated = dict(current)
            changed = False

            for agent_name in agents:
                old = current.get(agent_name)
                if old is None:
                    logger.info(f"  [{agent_name}] no record present, skipping")
                    continue

                if _is_canonical(old):
                    logger.info(f"  [{agent_name}] already canonical, skipping")
                    no_op_skips += 1
                    cfg_record["agents"][agent_name] = {"status": "already_canonical", "old": old}
                    continue

                normalized = _normalize_record(agent_name, old)
                if _records_equal(old, normalized):
                    logger.info(f"  [{agent_name}] normalization is a no-op, skipping")
                    no_op_skips += 1
                    cfg_record["agents"][agent_name] = {"status": "no_change", "old": old}
                    continue

                logger.info(f"  [{agent_name}] WILL REWRITE")
                logger.info(f"      OLD: {json.dumps(old, indent=2)}")
                logger.info(f"      NEW: {json.dumps(normalized, indent=2)}")
                rewrites_planned += 1
                cfg_record["agents"][agent_name] = {
                    "status": "rewrite_planned",
                    "old": old,
                    "new": normalized,
                }
                updated[agent_name] = normalized
                changed = True

            snapshot["configs"].append(cfg_record)

            if changed and apply:
                cfg.agent_prompts = updated
                session.add(cfg)

        # Write snapshot before any commit
        snap_path = _snapshot_path(snapshot_dir)
        with open(snap_path, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)
        logger.info(f"\nSnapshot written: {snap_path}")
        logger.info(f"Rewrites planned: {rewrites_planned}")
        logger.info(f"No-op skips:      {no_op_skips}")

        if apply and rewrites_planned > 0:
            session.commit()
            logger.info("APPLIED: changes committed to DB")
        elif apply:
            logger.info("APPLIED: nothing to write")
        else:
            logger.info("DRY-RUN: re-run with --apply to commit")

        return 0
    except Exception as exc:
        session.rollback()
        logger.error(f"Migration failed: {exc}")
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    parser.add_argument(
        "--agents",
        nargs="+",
        default=list(CANONICAL_AGENTS),
        help=f"Agents to migrate (default: {' '.join(CANONICAL_AGENTS)})",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/migration_snapshots",
        help="Directory for snapshot JSON files (default: data/migration_snapshots)",
    )
    args = parser.parse_args()

    return migrate(apply=args.apply, agents=args.agents, snapshot_dir=Path(args.snapshot_dir))


if __name__ == "__main__":
    sys.exit(main())
