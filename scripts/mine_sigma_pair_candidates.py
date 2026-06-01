#!/usr/bin/env python3
"""mine_sigma_pair_candidates.py

READ-ONLY miner that surfaces candidate "highly similar" Sigma rule pairs from
the existing corpus, bucketed into difficulty tiers, for human labeling into a
held-out eval set for the rule-novelty/similarity engine.

The single most valuable output is the T3 "blind-spot" tier: pairs that are the
SAME detection written differently, which the current engine fails to match.

================================================================================
DO NOTS (load-bearing — read before changing anything)
================================================================================

1. DB access is READ-ONLY (psycopg2 conn opened with readonly=True). SELECT only.
2. DO NOT use sigma_rules.exact_hash to identify duplicates. It has degenerate
   collisions (one hash observed shared by 84 unrelated rules with different
   positive_atoms). It is poisoned as a dup signal.
3. DO NOT pick pairs by running the novelty engine (sigma_novelty_service or
   sigma_matching_service). That is circular: the engine scores the T3
   blind-spot pairs as NOVEL, so mining with it would systematically EXCLUDE
   exactly the pairs you most need. We use an engine-INDEPENDENT canonical
   Jaccard over canon_atom() keys.

================================================================================
HOW TO RUN
================================================================================

    .venv/bin/python3 scripts/mine_sigma_pair_candidates.py \\
        --output eval_candidate_pairs.csv \\
        --max-per-tier 30

Default output: ./eval_candidate_pairs.csv (in repo root or cwd).

================================================================================
COVERAGE CAVEAT (printed at runtime too)
================================================================================

positive_atoms is only populated for ~1,901 of ~3,728 rules, and canonical_class
is only meaningful for windows.process_creation (~1,406) and
linux.process_creation (~141). Atom-based mining therefore covers
process_creation ONLY. Other categories (registry, network, file, etc.) are not
covered here — that needs a separate mining pass once positive_atoms backfills.

================================================================================
HELD-OUT INTENT
================================================================================

Each pair (A,B) is meant for a recall eval: hold A out as the query rule, keep B
in the corpus, and assert the engine surfaces B with the correct label. T3 pairs
are the regression suite for the planned wildcard<->modifier canonicalization
fix — they should fail before that fix and pass after.

The canon_atom() function below is also the reference spec for an upcoming fix
to the engine's atom keying (the engine currently keys on literal
operator+value, so `Image|endswith: '\\x.exe'` and `Image: '*\\x.exe'` do not
match though they are identical predicates). Keep canon_atom clean — it will be
reused.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extensions
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# canon_atom: pure, well-tested, engine-INDEPENDENT atom canonicalization
# ---------------------------------------------------------------------------

# Sigma comparison operators recognized in the modifier chain. Order matches
# ast_builder._parse_field_spec so we pick the same "first comparison op" the
# storage layer chose.
_COMPARISON_OPS = frozenset(
    {"contains", "endswith", "startswith", "re", "eq", "lt", "gt", "lte", "gte", "neq"}
)


def canon_atom(s: str) -> str:
    """Fold a stored positive_atoms identity into engine-independent canonical form.

    Input identity format produced by sigma_similarity/atom_extractor.atom_identity():
        ``field|operator|modifier_chain|value``
    where modifier_chain may itself contain pipes (e.g. ``contains|all``).

    Folding rules:

    * field = first ``|``-segment, value = last ``|``-segment.
    * Middle tokens: drop any ``all`` token (it controls list-AND/OR semantics,
      not behavioral identity); base_op = first token in :data:`_COMPARISON_OPS`,
      default ``eq``.
    * Wildcard folding when base_op == "eq":

      - ``*X*`` -> op=contains, v=X
      - ``*X``  -> op=endswith, v=X
      - ``X*``  -> op=startswith, v=X

    * If base_op already in {contains, endswith, startswith}: strip a single
      leading/trailing ``*`` from value if present (some rule authors include
      redundant wildcards in addition to the modifier).
    * Regex (``re``) and numeric ops (lt/gt/...) preserve value verbatim — we
      must not touch regex patterns.

    Known imprecision: values containing literal ``|`` (rare; some command
    lines) lose internal segments. Acceptable per spec since the resulting
    pairs are human-reviewed; for exactness, re-derive atoms from
    ``sigma_rules.detection`` jsonb instead.

    Returns ``field|op|v``.
    """
    parts = s.split("|")
    if len(parts) < 2:
        return s  # malformed; pass through unchanged

    field = parts[0]
    value = parts[-1]
    middle = parts[1:-1]

    # Drop |all tokens; find first comparison op in the remaining chain.
    middle_clean = [t for t in middle if t.lower() != "all"]
    base_op = "eq"
    for tok in middle_clean:
        if tok.lower() in _COMPARISON_OPS:
            base_op = tok.lower()
            break

    op, v = base_op, value

    if base_op == "eq":
        starts = v.startswith("*")
        ends = v.endswith("*")
        if starts and ends and len(v) >= 2:
            op, v = "contains", v[1:-1]
        elif starts:
            op, v = "endswith", v[1:]
        elif ends:
            op, v = "startswith", v[:-1]
    elif base_op in ("contains", "endswith", "startswith"):
        if v.startswith("*"):
            v = v[1:]
        if v.endswith("*"):
            v = v[:-1]
    # base_op in {re, lt, gt, lte, gte, neq, eq-with-no-wildcards}: leave value alone.

    return f"{field}|{op}|{v}"


# ---------------------------------------------------------------------------
# Read-only DB plumbing
# ---------------------------------------------------------------------------


def _load_postgres_password() -> str:
    """Resolve POSTGRES_PASSWORD from environment, then from repo .env file."""
    if pw := os.environ.get("POSTGRES_PASSWORD"):
        return pw
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("POSTGRES_PASSWORD="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(
        "POSTGRES_PASSWORD not found in env or .env. "
        "Export it or run inside a shell that has it loaded."
    )


def _connect_read_only(host: str, port: int) -> psycopg2.extensions.connection:
    """Open a Postgres connection with session-level read-only enforcement."""
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname="cti_scraper",
        user="cti_user",
        password=_load_postgres_password(),
        application_name="mine_sigma_pair_candidates(read-only)",
    )
    # Belt-and-suspenders read-only:
    #   readonly=True       — psycopg2 sets default_transaction_read_only=ON
    #   autocommit=True     — no implicit BEGIN/COMMIT churn
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _fetch_rules(conn: psycopg2.extensions.connection) -> list[dict[str, Any]]:
    """SELECT process_creation rules with non-empty positive_atoms."""
    sql = """
        SELECT rule_id, title, file_path, canonical_class, positive_atoms
        FROM sigma_rules
        WHERE canonical_class IN ('windows.process_creation', 'linux.process_creation')
          AND positive_atoms IS NOT NULL
          AND jsonb_typeof(positive_atoms) = 'array'
          AND jsonb_array_length(positive_atoms) > 0
        ORDER BY canonical_class, rule_id
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Pair mining
# ---------------------------------------------------------------------------

# Skip canon atoms found in more than this many rules — they are generic
# (think "process.image|endswith|.exe") and don't help discriminate pairs.
# Without this cap, blocking degenerates toward O(n^2) for the most common atom.
_BLOCK_SIZE_CAP = 300

# Tier thresholds (per spec).
_T1_THRESHOLD = 0.8       # near-identical
_T2_LOWER = 0.5           # moderate (T2: 0.5 <= canon < 0.8)
_T3_GAP_MIN = 0.3         # blind-spot: canon >= 0.5 AND gap >= 0.3
_NEG_UPPER = 0.2          # hard-negative: shares >=1 atom AND canon < 0.2


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _tier(canon_j: float, gap: float, shared_count: int) -> str | None:
    """Assign tier. T3 wins over T1/T2 (it's the prize)."""
    if canon_j >= _T2_LOWER and gap >= _T3_GAP_MIN:
        return "T3"
    if canon_j >= _T1_THRESHOLD:
        return "T1"
    if canon_j >= _T2_LOWER:
        return "T2"
    if canon_j < _NEG_UPPER and shared_count >= 1:
        return "NEG"
    return None  # uninteresting middle ground


def _mine_pairs(
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Block by shared canon atom within canonical_class, score, tier.

    Returns (pair_records, diagnostics).
    """
    # Precompute raw/canon atom sets per rule.
    raw_sets: list[set[str]] = []
    canon_sets: list[set[str]] = []
    for r in rules:
        atoms_raw = r["positive_atoms"] or []
        raw_sets.append(set(atoms_raw))
        canon_sets.append({canon_atom(a) for a in atoms_raw})

    # Inverted index PER canonical_class so we never compare windows vs linux.
    per_class_index: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for idx, r in enumerate(rules):
        cls = r["canonical_class"]
        for ca in canon_sets[idx]:
            per_class_index[cls][ca].append(idx)

    candidate_pairs: set[tuple[int, int]] = set()
    skipped_giant_blocks = 0
    for cls, atom_to_rules in per_class_index.items():
        for ca, rule_idxs in atom_to_rules.items():
            if len(rule_idxs) > _BLOCK_SIZE_CAP:
                skipped_giant_blocks += 1
                continue
            for i, j in itertools.combinations(sorted(rule_idxs), 2):
                candidate_pairs.add((i, j))

    pair_records: list[dict[str, Any]] = []
    tier_counts: dict[str, int] = defaultdict(int)
    for i, j in candidate_pairs:
        A, B = rules[i], rules[j]
        if A["canonical_class"] != B["canonical_class"]:
            continue  # blocking already prevents this; defensive.
        raw_a, raw_b = raw_sets[i], raw_sets[j]
        can_a, can_b = canon_sets[i], canon_sets[j]
        raw_j = _jaccard(raw_a, raw_b)
        can_j = _jaccard(can_a, can_b)
        gap = can_j - raw_j
        shared = can_a & can_b
        tier = _tier(can_j, gap, len(shared))
        if tier is None:
            continue
        pair_records.append(
            {
                "tier": tier,
                "canon_jaccard": can_j,
                "raw_jaccard": raw_j,
                "gap": gap,
                "rule_id_a": A["rule_id"],
                "title_a": A["title"] or "",
                "file_path_a": A["file_path"] or "",
                "rule_id_b": B["rule_id"],
                "title_b": B["title"] or "",
                "file_path_b": B["file_path"] or "",
                "shared_canon_atoms": sorted(shared),
                "a_only_atoms": sorted(can_a - can_b),
                "b_only_atoms": sorted(can_b - can_a),
                "canonical_class": A["canonical_class"],
            }
        )
        tier_counts[tier] += 1

    diagnostics = {
        "rules_mined": len(rules),
        "candidate_pairs_after_blocking": len(candidate_pairs),
        "skipped_giant_blocks": skipped_giant_blocks,
        **dict(tier_counts),
    }
    return pair_records, diagnostics


def _select_per_tier(
    pairs: list[dict[str, Any]], max_per_tier: int
) -> list[dict[str, Any]]:
    """Sort each tier by its native ranking signal, then keep top N per tier.

    Final output order: T3 first (by gap desc), then T1 (canon desc),
    then T2 (canon desc), then NEG (canon asc — weirdest near-misses first).
    """
    by_tier: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        by_tier[p["tier"]].append(p)

    by_tier["T3"].sort(key=lambda p: (-p["gap"], -p["canon_jaccard"]))
    by_tier["T1"].sort(key=lambda p: -p["canon_jaccard"])
    by_tier["T2"].sort(key=lambda p: -p["canon_jaccard"])
    by_tier["NEG"].sort(key=lambda p: p["canon_jaccard"])

    selected: list[dict[str, Any]] = []
    for tier in ("T3", "T1", "T2", "NEG"):
        selected.extend(by_tier.get(tier, [])[:max_per_tier])
    return selected


# ---------------------------------------------------------------------------
# CSV emission
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "tier",
    "canonical_class",
    "canon_jaccard",
    "raw_jaccard",
    "gap",
    "rule_id_a",
    "title_a",
    "file_path_a",
    "rule_id_b",
    "title_b",
    "file_path_b",
    "shared_canon_atoms",
    "a_only_atoms",
    "b_only_atoms",
]


def _write_csv(pairs: list[dict[str, Any]], output: Path) -> None:
    with output.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        w.writeheader()
        for p in pairs:
            row = {k: p.get(k, "") for k in _CSV_COLUMNS}
            row["canon_jaccard"] = f"{p['canon_jaccard']:.4f}"
            row["raw_jaccard"] = f"{p['raw_jaccard']:.4f}"
            row["gap"] = f"{p['gap']:.4f}"
            # JSON-encode atom lists so pipes / commas inside values round-trip.
            row["shared_canon_atoms"] = json.dumps(p["shared_canon_atoms"])
            row["a_only_atoms"] = json.dumps(p["a_only_atoms"])
            row["b_only_atoms"] = json.dumps(p["b_only_atoms"])
            w.writerow(row)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _print_summary(
    selected: list[dict[str, Any]],
    full_diag: dict[str, int],
    output: Path,
) -> None:
    counts: dict[str, int] = defaultdict(int)
    for p in selected:
        counts[p["tier"]] += 1
    print()
    print("=" * 72)
    print("SIGMA PAIR CANDIDATE MINING — SUMMARY")
    print("=" * 72)
    print(f"Output CSV         : {output}")
    print(f"Rules mined        : {full_diag['rules_mined']}")
    print(f"Candidate pairs    : {full_diag['candidate_pairs_after_blocking']}")
    print(f"Skipped giant blocks (>{_BLOCK_SIZE_CAP} rules sharing one atom): "
          f"{full_diag['skipped_giant_blocks']}")
    print()
    print("Pairs SELECTED for review (after per-tier cap):")
    for tier in ("T3", "T1", "T2", "NEG"):
        print(f"  {tier:4s} : {counts.get(tier, 0):4d}   "
              f"(found total: {full_diag.get(tier, 0)})")
    print()
    print("COVERAGE CAVEAT")
    print("-" * 72)
    print("Atom-based mining covers process_creation ONLY (positive_atoms is")
    print("populated only for that subset of the corpus; canonical_class outside")
    print("process_creation is unpopulated). Registry / network / file / etc.")
    print("rules need a separate mining pass once positive_atoms backfills.")
    print()
    print("HELD-OUT INTENT")
    print("-" * 72)
    print("Each pair (A,B): hold A out as the query rule, keep B in the corpus,")
    print("assert the engine surfaces B. T3 pairs are the regression suite for")
    print("the planned wildcard<->modifier canonicalization fix in the engine.")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mine candidate Sigma rule pairs for held-out eval labeling.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval_candidate_pairs.csv"),
        help="CSV output path (default: ./eval_candidate_pairs.csv)",
    )
    parser.add_argument(
        "--max-per-tier",
        type=int,
        default=30,
        help="Cap each tier to this many pairs (default: 30)",
    )
    parser.add_argument(
        "--host", default="localhost", help="Postgres host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=5432, help="Postgres port (default: 5432)"
    )
    args = parser.parse_args(argv)

    conn = _connect_read_only(args.host, args.port)
    try:
        rules = _fetch_rules(conn)
    finally:
        conn.close()

    if not rules:
        print("No process_creation rules with positive_atoms found.", file=sys.stderr)
        return 1

    pairs, diag = _mine_pairs(rules)
    selected = _select_per_tier(pairs, args.max_per_tier)
    _write_csv(selected, args.output)
    _print_summary(selected, diag, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
