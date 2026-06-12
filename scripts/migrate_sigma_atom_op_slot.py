#!/usr/bin/env python3
"""Migration: strip the redundant ``op`` slot from stored sigma atom strings.

Why
---
``atom_identity()`` used to emit a 4-slot identity ``field|op|modifier_chain|value``.
The ``op`` slot was always redundant — it equals ``modifier_chain.split("|")[0]``
(an empty chain ⟺ default ``eq``) — and it produced the confusing
``process.image|endswith|endswith|/php.exe`` double-modifier display.

Commit f7ad0813 changed the extractor to emit the 3-slot form
``field|modifier_chain|value``. New rules indexed through
``precompute_atom_fields()`` already store the 3-slot form, but rows
written before that commit still hold the legacy 4-slot strings in their
``positive_atoms`` / ``negative_atoms`` JSONB columns. This leaves a mixed
corpus. This script rewrites the stored strings in place so storage is
uniform.

What it changes
---------------
For every ``sigma_rules`` row, each element of ``positive_atoms`` and
``negative_atoms`` is run through :func:`strip_op_slot`, which drops the
redundant ``op`` segment. Only those two columns are touched — ``canonical_class``,
``surface_score`` and everything else are left untouched. This is a pure
string rewrite, *not* a re-parse, so it cannot change which atoms a rule has.

Legacy shapes recognised (all collapse to ``field|modifier_chain|value``):
- ``field|op|op|value``            single modifier  -> ``field|op|value``
- ``field|op|op|mod2|value``       multi modifier   -> ``field|op|mod2|value``
- ``field|eq||value``              default eq       -> ``field||value``

Already-3-slot strings (``field|mod|value``, ``field||value``,
``field|contains|all|value``) are left unchanged, so the migration is
idempotent and safe to re-run.

Idempotent: re-running is a no-op on rows already in 3-slot form.

Usage
-----
    # report what would change, write nothing (default):
    python scripts/migrate_sigma_atom_op_slot.py
    python scripts/migrate_sigma_atom_op_slot.py --dry-run

    # actually rewrite the rows:
    python scripts/migrate_sigma_atom_op_slot.py --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Operators that are case-insensitive by default. "eq" is the default operator
# emitted (with an empty modifier chain) by the legacy 4-slot format.
_DEFAULT_OP = "eq"


def strip_op_slot(atom: str) -> str:
    """Drop the redundant leading ``op`` segment from a legacy 4-slot atom string.

    Legacy identity: ``field|op|modifier_chain|value`` where
    ``op == modifier_chain.split("|")[0]`` (or ``op == "eq"`` with an empty
    modifier chain for the default operator). The target 3-slot identity is
    ``field|modifier_chain|value``.

    The transform is purely structural and operates on the *front* of the
    string (field/op/first-modifier), so values that themselves contain ``|``
    are unaffected. It is idempotent: strings already in 3-slot form are
    returned unchanged.
    """
    segs = atom.split("|")
    # 3-slot (field|mod|value) or shorter -> nothing to strip.
    if len(segs) < 4:
        return atom
    op, first_mod = segs[1], segs[2]
    # A legacy row duplicates the operator into segs[1]:
    #   - non-default op: segs[1] == segs[2] (first modifier token), or
    #   - default eq: segs[1] == "eq" and the modifier chain (segs[2]) is empty.
    is_legacy = (op == first_mod) or (op == _DEFAULT_OP and first_mod == "")
    if not is_legacy:
        return atom
    del segs[1]
    return "|".join(segs)


def migrate_atom_list(atoms: object) -> tuple[list | object, int]:
    """Apply :func:`strip_op_slot` to every element of a stored atom list.

    Returns ``(new_value, changed_count)``. Non-list / empty values are passed
    through unchanged with a zero count, mirroring how the precompute path can
    leave the column null or scalar for rules with no extractable atoms.
    """
    if not isinstance(atoms, list):
        return atoms, 0
    new_atoms: list = []
    changed = 0
    for a in atoms:
        if isinstance(a, str):
            stripped = strip_op_slot(a)
            if stripped != a:
                changed += 1
            new_atoms.append(stripped)
        else:
            new_atoms.append(a)
    return new_atoms, changed


def run_migration(apply: bool = False) -> bool:
    """Rewrite legacy 4-slot atom strings to 3-slot across the sigma_rules table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    from sqlalchemy import create_engine, text

    mode = "APPLY" if apply else "DRY-RUN"
    logger.info("=== sigma atom op-slot migration (%s) ===", mode)

    rows_scanned = 0
    rows_changed = 0
    atoms_changed = 0

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT id, positive_atoms, negative_atoms FROM sigma_rules "
                    "WHERE positive_atoms IS NOT NULL OR negative_atoms IS NOT NULL"
                )
            )
            updates: list[tuple[int, list | object, list | object]] = []
            for row in result:
                rows_scanned += 1
                new_pos, c_pos = migrate_atom_list(row.positive_atoms)
                new_neg, c_neg = migrate_atom_list(row.negative_atoms)
                if c_pos or c_neg:
                    rows_changed += 1
                    atoms_changed += c_pos + c_neg
                    updates.append((row.id, new_pos, new_neg))

            logger.info(
                "Scanned %d rows; %d rows need rewriting; %d atom strings affected.",
                rows_scanned,
                rows_changed,
                atoms_changed,
            )

            if not apply:
                if updates:
                    sample = updates[:5]
                    logger.info("Sample of rows that would change (first %d):", len(sample))
                    for rule_id, _, _ in sample:
                        logger.info("  rule id=%s", rule_id)
                logger.info("Dry-run only — no rows written. Re-run with --apply to commit.")
                return True

            import json

            for rule_id, new_pos, new_neg in updates:
                conn.execute(
                    text(
                        "UPDATE sigma_rules SET positive_atoms = CAST(:pos AS jsonb), "
                        "negative_atoms = CAST(:neg AS jsonb), updated_at = NOW() WHERE id = :id"
                    ),
                    {
                        "pos": json.dumps(new_pos) if isinstance(new_pos, list) else None,
                        "neg": json.dumps(new_neg) if isinstance(new_neg, list) else None,
                        "id": rule_id,
                    },
                )
            conn.commit()
            logger.info("✅ Rewrote %d rows (%d atom strings).", rows_changed, atoms_changed)
        return True
    except Exception as e:  # noqa: BLE001 - surface any failure to the operator
        logger.error("❌ Migration failed: %s", e)
        import traceback

        logger.error(traceback.format_exc())
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        action="store_true",
        help="Write the rewritten atom strings to the DB. Default is dry-run.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Report affected rows without writing (the default behaviour).",
    )
    args = parser.parse_args()
    ok = run_migration(apply=args.apply)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
