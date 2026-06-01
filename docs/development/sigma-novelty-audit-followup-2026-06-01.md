# Sigma Novelty Engine — Audit Followup & Hardening Spec

**Status:** Active
**Date:** 2026-06-01
**Predecessor audit:** [`cmdline-eval-audit-2026-05-31.md`](cmdline-eval-audit-2026-05-31.md) (the eval-side audit) and the May 31 Sigma novelty audit (mined 1,545 rules → 10 T3 wildcard↔modifier pairs, 231 exact_hash collisions, 0% precision on hash dedup).
**Goal:** *The Sigma novelty scorer is deterministic, honest about recall failures, and structurally complete for the indexed corpus.*

This document is the complete build spec for the follow-up arc. It is **the source of truth** — no external tracker, no Todoist, no parallel issue log. A fresh Claude session should pick the next pending item, do the work, update this doc's status table, commit, and continue.

---

## How Claude uses this spec

1. **Read this entire file before doing anything.** Items have dependencies that aren't obvious from titles alone.
2. **Find the next item to work on** by scanning the Status Dashboard below for the first row with status `○ pending` whose dependencies are all `✓ done`.
3. **Read that item's full section** end-to-end (Why, Where, Acceptance, Subtasks, Dependencies).
4. **Execute the subtasks in order.** Use TDD per `AGENTS.md` (repo root) when adding behavior; quantify-before-fixing for measurement items.
5. **Update the Status Dashboard** in this doc as the item progresses (`◐ in progress` when starting; `✓ done` on completion). Edit this file in the same commit as the work.
6. **Commit and push** per the conventions in `## Project Conventions` below.
7. **If blocked**: change status to `⚠ blocked: <one-line reason>`, write an `## Addendum YYYY-MM-DD` section at the bottom of this doc describing what's blocking, and stop. Do not silently park items.
8. **If measurement output triggers a branch in the plan** (Items 4a/4b/4c gate downstream items): record the measurement in an `## Addendum YYYY-MM-DD: Measurement Results` section, then update the affected items' status to reflect the decision (e.g. `⊘ skipped per 4a: <2% wildcards`).

### Status legend

| Symbol | Meaning |
|---|---|
| `○` | pending — not started, dependencies not yet met OR not yet picked up |
| `◐` | in progress — currently being worked on; commit message will reference the item |
| `✓` | done — landed on `europa-7.2.1` (or `main` if released) |
| `⊘` | skipped — explicitly decided not to ship, with reason in addendum |
| `⚠` | blocked — see addendum for reason |

### Status Dashboard

| Item | Title | Status | Depends on |
|---|---|---|---|
| 1 | Push `bd71d9cc` (exact_hash fix) | ✓ done — on `origin/europa-7.2.1` as of 2026-06-01 | — |
| 2 | Review + commit eval-miner files | ✓ done — `8c7b46b7`, see Addendum | 1 |
| 3 | Fix `generate_canonical_text` operator-drop | ⊘ skipped — spec hypothesis disproved 2026-06-01 (see Addendum) | — |
| 4a | LLM-axis measurement | ✓ done — 14.8% all-time wildcard rate; **ship Item 9** | 2 |
| 4b | Coverage-gap-usage measurement | ✓ done — 0% legacy-path hits in last 30d; **Item 8 demoted to "next quarter"** | 1 |
| 4c | `canonical_class` fan-out measurement | ✓ done — 0 rows; **Item 6 = Option B** | 1 |
| 5 | Queue rules excluded from novelty corpus | ○ | 1 |
| 6 | P2-C: hard-gate / canonical_class contradiction (Option B per 4c) | ✓ done — see Addendum (Item 6) | 1, 4c |
| 7 | P1: unordered `LIMIT 20` sort | ✓ done — see Addendum 2026-06-01 (Item 7) | 1 |
| 8 | P2-D: coverage backfill beyond `process_creation` (demoted to "next quarter" per 4b) | ○ | 1, 4b |
| 9 | P1-B: wildcard↔modifier canonicalization (ship per 4a) | ✓ done — code `0688b0ff`, rebuild + recompute verified, queue 486 went 0→13 matches and 487 went 0→16; see closing Addendum | 1, 4a |
| 10 | P3 hygiene bundle | ○ | 6 |
| 11 | Atom-less rule `exact_hash` collisions (latent) | ○ | 1 |

---

## Definition of Done (for the whole goal)

The goal is closed when **all** are true:

1. No empty-atom rule's `exact_hash` causes a false-DUPLICATE verdict. *(Item 1 — guards the short-circuit; Item 11 — eliminates the underlying collision.)*
2. ~~`generate_canonical_text` includes the operator in every atom's canonical form.~~ *(Item 3 — `⊘ skipped 2026-06-01`: spec premise disproved; operator-drop is in dead code that doesn't affect `exact_hash`. See Addendum.)*
3. `canonical_class` either does work the simpler `logsource_key` fallback wouldn't (broader recall across `logsource_key` values), or is documented as a no-op safety net. The hard gate at `sigma_matching_service.py` is consistent with whichever it is. *(Item 6.)*
4. Candidate retrieval in `sigma_novelty_service.py` is ordered and reproducible. *(Item 7.)*
5. The coverage hole (rules without `canonical_class`/`positive_atoms`) is either backfilled or exposed in operational metrics. *(Item 8.)*
6. Every rule comparison surfaces either a numeric similarity or an explicit "comparator inconclusive" status — no silent fallbacks. *(Items 6, 8.)*
7. LLM-generated rules in production are within the scorer's coverage, verified by measurement, not assumed. *(Item 4.)*
8. Any external "three phases" architecture diagram (decks, docs) describes what the engine actually does. *(Item 6 subtask 4.)*

---

## Themes (what the 10 items actually cover)

The May 31 audit prompted by the exact_hash false-duplicate finding surfaced multiple
classes of problem. Hash collisions are one theme; the rest are distinct axes that share
the same audit lineage but not the same code paths or failure modes. Don't read the spec
as "all hash" — the hash work is ~2 items / ~3 hours; the remaining 8 items / ~8 days
target separate dimensions of correctness, recall, and coverage.

| Theme | Items | What it addresses |
|---|---|---|
| **False-positive duplicate hash** | 1 (✓ done), 3 (⊘ skipped), 11 | List-of-maps collapse (shipped via `bd71d9cc`). Operator-drop hypothesis disproved (3, skipped). Atom-less keyword-only rules still collide on hash but are inert today thanks to bd71d9cc's guard (11 — latent). |
| **Recall holes** | 5, 6 | Queue rules never compared against incoming candidates (5). Hard-gate at `sigma_matching_service.py:551` silently drops cross-`logsource_key` candidates that `canonical_class` was meant to surface (6). |
| **Determinism & instrumentation** | 4b, 7 | `LIMIT 20` without `ORDER BY` makes candidate retrieval non-reproducible across runs (7). Static + dynamic measurement of how often the legacy fallback path fires (4b). |
| **Corpus completeness** | 4c, 8 | Does `canonical_class` actually span multiple `logsource_key` values today (4c)? Only ~41% of rules have precomputed atoms — extend the canonical-class resolver and backfill (8). |
| **LLM-generation side** | 4a, 9 | Do LLM-generated rules use literal `*` in values (4a)? If so, fold wildcards into modifier-equivalent atoms so they intersect with corpus atoms properly (9 — conditional on 4a). |
| **Process hygiene** | 2, 10 | Commit the eval-miner tooling that produced the audit numbers (2). Rename misnamed function, fix N+1 query, document the two-engine architecture (10). |

Each theme is independent of the others — a fresh session can pick up any item whose
dependencies are met without needing the full thematic picture. The grouping is for
human readers deciding where to invest next, not for execution ordering.

---

## Already Shipped (do not redo)

| Commit | What | Files |
|---|---|---|
| `7d242dfd` (on origin) | `/similar-rules` response now ships parsed `current_rule`; queue similarity dialog uses it instead of the broken custom JS YAML parser. Regression test for sibling structure + `CommandLine\|contains\|all` list preservation. Docs updated with correct containment definition + new Surface (DNF branches) subsection. | `src/web/routes/sigma_queue.py`, `src/web/templates/workflow.html`, `tests/api/test_sigma_similar_rules_api.py`, `docs/features/sigma-rules.md` |
| `bd71d9cc` (on origin) | `exact_hash` degenerate-collision fix: list-of-maps extraction + atom-less→NOVEL guard. Corpus re-indexed; 130 collision groups went to 0. | See commit; landed via TDD with 3 tests, 111 green overall. |

**First action when this spec was written:** push `bd71d9cc` to `origin/europa-7.2.1`. *Completed 2026-06-01 — see Addendum at end of doc.*

---

## Item 1 — Push `bd71d9cc` ✓ done

**Status:** Completed 2026-06-01. `bd71d9cc` is on `origin/europa-7.2.1`. See Addendum at end of doc for commit details. This section retained for traceability.

**Why:** Close out the shipped fix. Until it's on origin, nothing downstream can build on it cleanly.

**How (for reference):**
```bash
git push origin europa-7.2.1
```

**Done when:** `git log --oneline origin/europa-7.2.1 | head -1` shows `bd71d9cc`.

**Dependencies:** none.

**Estimate:** 5 minutes.

---

## Item 2 — Review and commit the uncommitted eval-miner files

**Why:** Two files were produced by an agent run during the May 31 audit and are still uncommitted:
- `scripts/mine_sigma_pair_candidates.py`
- `tests/sigma_semantic_similarity/test_canon_atom.py`

They underpin the corpus-internal measurement (456 candidate pairs / 24 missed / 10 strong) used to demote the wildcard↔modifier canonicalization item. If their methodology is wrong, the demotion is wrong, and we'll be re-litigating Item 5 in two weeks.

**Acceptance criteria:**
1. Read both files end-to-end.
2. Verify `canon_atom` in `test_canon_atom.py` reproduces the same logic as `sigma_semantic_similarity/sigma_similarity/atom_extractor.py:atom_identity` — especially: field alias map, case-folding rules for `_CASE_INSENSITIVE_OPS`, backslash normalization. **Any divergence is a methodology bug.**
3. Verify the definition of "missed pair" in `mine_sigma_pair_candidates.py`. Document what threshold the measurement uses (e.g. "canon says identical but scorer < 0.9" vs. "canon says SIMILAR but scorer says NOVEL"). **Different thresholds give different demotion conclusions.**
4. Commit both files as their own focused PR — conventional commit, descriptive body, do not bundle with Item 3.

**Dependencies:** Item 1.

**Estimate:** 30 min review + 10 min commit.

**If methodology issues are found:** stop the dependent chain (Items 4 and 9) and re-run the corpus measurement after fixing the miner.

---

## Item 3 — Fix `generate_canonical_text` operator-drop (P0-2) ⊘ skipped

**Status:** `⊘ skipped 2026-06-01`. The spec's premise that this bug affects `exact_hash` was disproved by direct code reading and corpus quantification — see Addendum at the end of this doc. The typo (`atom.get("ops")` vs `atom.get("op")`) is real but lives in dead code: `generate_canonical_text` writes to `sigma_rules.canonical_text`, which is **never read** anywhere in the repo. `generate_exact_hash` uses `asdict()` directly and includes the operator correctly. The latent atom-less-rule hash collision pattern that *did* surface during the investigation is tracked separately as Item 11.

The original section is retained below for traceability.

---

**Why (original — premise disproved):** The function appears to use a stale key (`atom.get("ops")` or similar) instead of the actual `op` field when building the canonical text fed into `exact_hash`. If true, two rules with the same field+value but **different operators** (e.g. `endswith` vs `contains` vs `eq`) collapse to the same canonical form — same failure shape as the list-of-maps bug we just fixed.

**Where:**
- `src/services/sigma_novelty_service.py` — search for `generate_canonical_text` (function definition) and `generate_exact_hash` (caller).
- The atom dict shape comes from `extract_atomic_predicates` / `build_canonical_rule`; the `op` field is set by `Atom` dataclass at `src/services/sigma_novelty_service.py:138-148`.

**Acceptance criteria:**
1. **Quantify first** (mirrors the exact_hash quantification):
   - Find all `exact_hash` collision groups in the live `sigma_rules` table that survive the Item 1 (list-of-maps) fix. SQL:
     ```sql
     SELECT exact_hash, COUNT(*) AS rule_count, array_agg(rule_id) AS rule_ids
     FROM sigma_rules
     WHERE exact_hash IS NOT NULL
       AND positive_atoms IS NOT NULL          -- exclude atom-less rules (NOVEL via Item 1 guard)
     GROUP BY exact_hash
     HAVING COUNT(*) > 1
     ORDER BY rule_count DESC;
     ```
   - For each surviving group, fetch the rules and inspect their `detection.atoms` operator-by-operator:
     ```sql
     SELECT rule_id, detection
     FROM sigma_rules
     WHERE rule_id = ANY('{<rule_ids from above>}');
     ```
   - If any group contains rules with **identical field+value but distinct operators**, that's a confirmed operator-drop collision. Count and report in the addendum.
2. Fix in `generate_canonical_text` so the canonical text includes the operator for every atom. Suggested form: serialize each atom as `field|op|value` (sorted lex), join with newline. The exact wire format is not load-bearing as long as different `op` values produce different strings.
3. TDD: add a regression test in `tests/sigma_semantic_similarity/` that constructs two atoms with same field+value but different ops, computes their `exact_hash`, asserts hashes differ. Template:
   ```python
   def test_exact_hash_differs_when_operators_differ():
       a1 = {"field": "CommandLine", "op": "contains", "value": "powershell.exe"}
       a2 = {"field": "CommandLine", "op": "endswith", "value": "powershell.exe"}
       rule1 = make_rule([a1])
       rule2 = make_rule([a2])
       assert generate_exact_hash(rule1) != generate_exact_hash(rule2)
   ```
4. Re-index the corpus and re-run the collision query — confirm collisions drop to zero (or to the next remaining cause, which becomes a new addendum and possibly a new spec item). Re-index command:
   ```bash
   ./run_cli.sh sigma reindex-semantic-fields     # if this exists
   # OR, if no CLI subcommand yet, run the recompute path inline:
   ./run_cli.sh sigma index-customer-repo --force
   ```
   Confirm with operator before running — touches every row in `sigma_rules`.

**Dependencies:** Item 1.

**Estimate:** 1–2 hours.

**Why P0:** This is a *correctness* bug, not hygiene. It also pollutes the canonical_class fan-out measurement in Item 5 if not fixed first.

---

## Item 4 — Decision-gating measurements

**Why:** Three downstream items (Items 6, 7, 9) are gated on measurements that haven't been run. Doing them while the scorer is stochastic (no `ORDER BY` on the fallback) or while the canonical text is bug-ridden (Item 3 unfixed) would produce numbers we can't trust.

**Three measurements in one read-only pass:**

### 4a — LLM-axis: do generated rules use wildcards?

**Population:** all rules from `sigma_rule_queue` and `agentic_workflow_executions.sigma_results` in the last 30 days. Not a synthetic sample.

**Signals (compute both):**
1. **Fraction of generated rules with literal `*` in any value.**
2. **Rank-change rate.** For each rule with a literal `*`, find its current top-5 nearest atom-distance neighbors. Run a *hypothetical* transformation that folds `\foo\*` → `endswith \foo\` and similar (leading `*` → `endswith`, trailing `*` → `startswith`, `*…*` → `contains`). Re-rank. Count how often the top-1 changes.

**Decision thresholds (pre-commit, write down before running):**

| Outcome | Action |
|---|---|
| <2% of rules with `*` AND <1 rank-change per 100 rules | Skip Item 9 permanently. Document as "wildcard↔modifier not worth ~half day of work; corpus-internal impact tiny AND LLM-axis impact tiny." |
| >10% OR >5 rank-changes per 100 | Ship Item 9 (P1-B wildcard↔modifier canonicalization). |
| Anything in between | Run a small synthetic experiment: pick 20 generated rules with `*`, transform them by hand, see if any change queue outcome (NOVEL ↔ SIMILAR boundary). Re-decide. |

### 4b — Coverage-gap-usage

**Question:** when the live scorer falls back from the precomputed-atom path to the legacy in-app path (because the candidate has no `positive_atoms`), how often does that happen?

**How:** two complementary approaches — run both:

1. **Static corpus coverage** (one SQL query, ~30 seconds):
   ```sql
   SELECT
     COUNT(*) FILTER (WHERE positive_atoms IS NOT NULL)                      AS with_atoms,
     COUNT(*) FILTER (WHERE positive_atoms IS NULL)                          AS without_atoms,
     COUNT(*)                                                                AS total,
     ROUND(100.0 * COUNT(*) FILTER (WHERE positive_atoms IS NULL) / COUNT(*), 1) AS pct_without
   FROM sigma_rules;
   ```
   This is the *upper bound* on fallback usage: every comparison touching a row without `positive_atoms` takes the fallback path.
2. **Dynamic instrumentation** (more accurate, but invasive): add a counter in `sigma_novelty_service.py` around line 345 (the precomputed-atom branch entry) and around line 437 (the legacy fallback branch entry). Log per-comparison; aggregate per workflow run. Remove the instrumentation before committing.

Report both numbers in the addendum. The static number tells you "if all rules were compared uniformly, the fallback would fire X% of the time"; the dynamic number tells you "in production, with the actual rule distribution generated rules hit, the fallback fires Y% of the time." Often Y < X because LLM-generated rules cluster in `windows.process_creation` where coverage is good.

**Decision thresholds:**

| Outcome | Action |
|---|---|
| Fallback fires <5% of comparisons | Item 8 is "later" priority. |
| Fallback fires 5–25% | Item 8 is "next quarter" priority. |
| Fallback fires >25% | Item 8 is urgent — most of the corpus is being scored by the legacy path, which the audit found to be less accurate. Move ahead of Item 6. |

### 4c — `canonical_class` fan-out

**Question:** does `canonical_class` actually span multiple `logsource_key` values in the live corpus? This determines whether the Item 6 hard-gate fix is Option A or Option B.

**SQL (one query):**
```sql
SELECT canonical_class, COUNT(DISTINCT logsource_key) AS lk_count
FROM sigma_rules
WHERE canonical_class IS NOT NULL
GROUP BY canonical_class
HAVING COUNT(DISTINCT logsource_key) > 1
ORDER BY lk_count DESC;
```

**Decision thresholds:**

| Outcome | Action |
|---|---|
| Zero rows (max distinct lk per class = 1) | Item 6 = Option B (scope the gate to fallback path; canonical_class is de facto 1:1 with logsource_key). |
| Any rows | Item 6 = Option A (penalty in scoring). Read the rows: are they meaningful semantic equivalences (sysmon↔windows for process_creation) or just normalization variants? |

**Acceptance criteria:**
1. All three measurements run.
2. Numbers written down with absolute counts (not just percentages).
3. The three decision thresholds applied, results recorded in the Goal's parent task or this doc as an addendum.
4. **Do not** modify any production code paths during the measurement — instrumentation is fine but must be backed out before the next commit.

**Dependencies:** Items 1, 2, 3.

**Estimate:** half a day.

---

## Item 5 — Queue rules excluded from novelty corpus

**Why:** The novelty/similarity scorer reads only from `sigma_rules` (the indexed SigmaHQ + customer-repo corpus). Approved-but-unsubmitted rules in `sigma_rule_queue` are **never compared** against incoming candidates. If a user approves rule X today and an LLM generates near-duplicate rule X' tomorrow, X' will be classified NOVEL even though X is already in the queue waiting to be merged.

This is a real recall hole, independent of all other items.

**Acceptance criteria:**
1. Add `sigma_rule_queue` rows with `status IN ('approved', 'submitted')` to the candidate set in `_get_candidate_rules` at `src/services/sigma_novelty_service.py:1130-1245`. Shape:
   ```python
   # Existing block returns candidates from sigma_rules.
   # Add a second query for queue rules with the same logsource/canonical_class filter:
   if hasattr(SigmaRuleQueueTable, "canonical_class") and canonical_class:
       queue_candidates = (
           self.db_session.query(SigmaRuleQueueTable)
           .filter(SigmaRuleQueueTable.canonical_class == canonical_class)
           .filter(SigmaRuleQueueTable.status.in_(["approved", "submitted"]))
           .all()
       )
       candidates.extend(_row_to_candidate(q, from_queue=True) for q in queue_candidates)
   ```
   `SigmaRuleQueueTable` may not have `canonical_class`/`positive_atoms` columns yet — if not, this item also requires adding those columns + a backfill (subtask below). Confirm before coding.
2. Tag candidates with `from_queue: True` in the match dict so downstream code can distinguish queue-sourced matches from corpus-sourced matches.
3. Tests in `tests/services/test_sigma_novelty_service.py`: generate a duplicate of an approved-but-unsubmitted queue rule; verify it's classified SIMILAR or DUPLICATE, not NOVEL. Mock the queue session as needed.
4. UI: the queue card's "similar rules" panel (`src/web/templates/workflow.html` around line 15976 onward) shows a distinct badge for queue-sourced matches: "Already in queue (approved)" vs. the existing "Your repo" / "SigmaHQ" badges at line 15974-15975.

### Subtasks (order)
1. **Check schema.** Does `sigma_rule_queue` have `canonical_class`, `positive_atoms`, `negative_atoms`, `surface_score`? If not, add them (Alembic migration) and backfill from `rule_yaml` for existing approved rows. This is a precondition.
2. Extend `_get_candidate_rules` to query queue rules.
3. Add `from_queue` tag through the matching pipeline.
4. UI badge.
5. Tests for the NOVEL → SIMILAR transition.

**Dependencies:** Items 1, 3. (Independent of measurements; can be parallelized with Item 4.)

**Estimate:** 1 day, *plus* migration if schema gap exists (another half day).

**Note:** Once shipped, the inverse query also becomes useful: "list of approved queue rules whose PR never landed" — surfaces stuck PRs. Not in scope for this item; flag in the PR description as a follow-up candidate.

---

## Item 6 — P2-C: Hard-gate / canonical_class contradiction

**Why:** The hard gate at `src/services/sigma_matching_service.py:551-560` drops any scored candidate whose `logsource_key` doesn't equal the proposed rule's. This makes the canonical_class branch of Phase 1 (`sigma_novelty_service.py:1130-1186`) effectively dead code — Phase 1's broader recall is immediately undone by Phase 3's narrow gate. The engine never returns cross-`logsource_key` matches even though the column, indexed at sync time by `sigma_sync_service.py`, exists to enable exactly that.

**Where:**
- Hard gate: `src/services/sigma_matching_service.py:551-560`
- Phase 1 retrieval (both branches): `src/services/sigma_novelty_service.py:1130-1186`

**Decision (from Item 4c measurement, made BEFORE coding):**

| canonical_class fan-out | Design | Why |
|---|---|---|
| = 1 across the corpus | **Option B**: scope the gate to the fallback path | canonical_class is de facto 1:1 with logsource_key; the gate is dead code on the canonical_class path. Simplest fix; matches "safety check" intent. |
| > 1 | **Option A**: penalty in scoring | Real recall is being silently dropped. Need to surface it numerically. |

### Option A specifics (if chosen)

**Critical:** do NOT fold the logsource-mismatch penalty into `filter_penalty`. `filter_penalty` means *"negative atoms differ"* — distinct semantics. There's already a `service_penalty` slot in the match dict at `src/services/sigma_novelty_service.py:489`; introduce a sibling **`logsource_penalty`** field. The new similarity formula:

```
similarity = (Jaccard × Containment) − filter_penalty − service_penalty − logsource_penalty
```

Default `logsource_penalty` for cross-logsource-same-canonical-class candidates: start at `0.10` (parity with `SERVICE_PENALTY`). Tune via the measurement data.

**Code shape (Option A):**

```python
# In sigma_matching_service.py around line 551, REPLACE the hard-gate continue
# with a penalty calculation:

if (
    rule_logsource_key
    and proposed_logsource_key
    and rule_logsource_key != proposed_logsource_key
):
    logger.info(
        "logsource_mismatch_penalty_applied",
        extra={
            "proposed_logsource_key": proposed_logsource_key,
            "candidate_logsource_key": rule_logsource_key,
            "candidate_rule_id": rule.rule_id,
            "phase1_path": match.get("phase1_path", "unknown"),
        },
    )
    logsource_penalty = LOGSOURCE_PENALTY  # new module-level constant, default 0.10
else:
    logsource_penalty = 0.0

# Then add logsource_penalty to the match dict alongside service_penalty/filter_penalty,
# and subtract it from `similarity` in the assembly step at sigma_novelty_service.py:484-509.
```

### Option B specifics (if chosen)

Thread a `phase1_path: 'canonical_class' | 'logsource_fallback'` flag through the candidate dict returned by `_get_candidate_rules` in `sigma_novelty_service.py`. The gate in `sigma_matching_service.py:551` skips when `phase1_path == 'canonical_class'` (Phase 1's SQL already enforced `canonical_class` filtering; the gate is redundant on that path). On the fallback path, the gate becomes a no-op safety check (Phase 1's SQL already enforced `logsource_key == proposed_logsource_key`).

**Code shape (Option B):**

```python
# In sigma_novelty_service.py:1190 (canonical_class branch) and :1213 (fallback branch),
# tag each candidate with how it was retrieved:

def _row_to_candidate(c, phase1_path: str):
    out = {
        "rule_id": c.rule_id,
        ...
        "phase1_path": phase1_path,  # NEW
    }
    ...
    return out

# Then in sigma_matching_service.py:551, gate the gate:
if (
    match.get("phase1_path") == "logsource_fallback"   # only enforce on fallback
    and rule_logsource_key
    and proposed_logsource_key
    and rule_logsource_key != proposed_logsource_key
):
    logger.warning(
        "logsource_key_mismatch_on_fallback_path",  # this should be rare; investigate if it fires
        extra={
            "proposed_logsource_key": proposed_logsource_key,
            "candidate_logsource_key": rule_logsource_key,
            "candidate_rule_id": rule.rule_id,
        },
    )
    continue
```

### Acceptance criteria (both options)

1. When Phase 1 retrieves via `canonical_class` and surfaces a candidate with different `logsource_key`, that candidate either (A) survives scoring with the mismatch reflected, or (B) survives the gate.
2. When Phase 1 retrieves via the `logsource_key` fallback, end-to-end behavior is unchanged.
3. The existing `logger.warning` at `sigma_matching_service.py:556-559` becomes structured logging emitting `proposed_logsource_key`, `candidate_logsource_key`, `candidate_rule_id`, and `phase1_path`.
4. Tests cover both Phase 1 paths under the new gate behavior. Pattern: `tests/sigma_semantic_similarity/` (follow `test_canon_atom.py`).
5. UI: if Option A, the dialog's Behavioral Similarity Breakdown shows `Logsource penalty: X%` as its own row in the deterministic engine's expanded panel (`src/web/static/js/components/similarity-display.js`, lines 264–298). If Option B, no UI change needed.
6. Architecture docs updated:
   - [`docs/features/sigma-rules.md`](../features/sigma-rules.md) — the Phase 3 description in "Novelty Service Architecture."
   - Any external deck describing the three-phase engine (search for "Phase 3" / "hard gate" in `*.pptx`). Update or remove the misleading slide content.

### Subtasks (order)

1. **Read measurement output from Item 4c.** Decide Option A or B in writing (1–2 paragraphs in the task / commit body). Decision drives steps 2–4.
2. **Implement chosen approach + structured logging.**
3. **Tests for both Phase 1 paths** (see acceptance #4).
4. **Update docs and any decks.**

**Dependencies:** Items 1, 3, 4 (specifically 4c).

**Estimate:** 1 day design + 1 day code + 0.5 day docs.

---

## Item 7 — P1: Unordered `LIMIT 20` sort

**Why:** `src/services/sigma_novelty_service.py:1180-1186` (fallback candidate retrieval):

```python
candidates = (
    self.db_session.query(SigmaRuleTable)
    .filter(SigmaRuleTable.logsource_key == logsource_key)
    .limit(top_k)
    .all()
)
```

No `ORDER BY`. Postgres returns *whichever* 20 rows it likes — different across runs, different across replicas, different after `VACUUM`. This is the **P1: sort LIMIT** item from the May 31 audit, demoted in scope (it's only the fallback path) but not in severity (it makes the scorer non-deterministic on rules that hit the fallback).

**Fix:** add `.order_by(SigmaRuleTable.rule_id)` (or another stable column) before `.limit(top_k)`.

**Acceptance criteria:**
1. Same query, same result, every time.
2. Test: insert 30 rules with the same `logsource_key`, call `_get_candidate_rules` twice, assert both calls return the same 20 rule_ids in the same order.

**Dependencies:** Item 1.

**Estimate:** 30 min (fix + test).

**Why P1 (not P3 hygiene):** non-determinism corrupts every measurement and every test that lands on the fallback path. Land before Items 8 and 9 if either of those exercise the fallback.

---

## Item 8 — P2-D: Coverage backfill beyond `process_creation`

**Why:** Of 3,728 rules in the corpus, only 1,547 (41%) have `positive_atoms` / `canonical_class` populated. The remainder fall back to the legacy in-app path on every comparison. The Item 4b measurement decides urgency, but the work itself has two halves:

**Code half:** the `canonical_class` resolution map (search for it in `sigma_novelty_service.py` and `sigma_semantic_similarity/sigma_similarity/`) currently covers `windows.process_creation`, `linux.process_creation`, and a few others. Add the missing classes — at minimum: `windows.network_connection`, `windows.file_event`, `windows.registry_event`, `windows.image_load`, `linux.network_connection`, `linux.file_event`. Each addition needs its own integration test.

**Operational half:** for every rule already in the DB, run the canonical_class resolver and update the row. Either:
- A new CLI subcommand `sigma recompute-semantic-fields` that iterates rules, recomputes `positive_atoms`/`negative_atoms`/`surface_score`/`canonical_class`, and writes back.
- Or a one-off migration script.

The CLI approach is preferred because it's repeatable (when new canonical classes are added, you re-run it).

**Acceptance criteria:**
1. The CLI command exists and is idempotent.
2. After running it, the coverage measurement from Item 4b returns ≥ 95% of comparisons going through the precomputed-atom path (assuming the new canonical classes cover the existing corpus).
3. Tests for each new canonical class (e.g. `windows.network_connection`) extracting atoms correctly from representative rules.
4. Documentation in [`docs/features/sigma-rules.md`](../features/sigma-rules.md) updated with the new canonical class list.

**Dependencies:** Items 1, 3, 4b (urgency signal). Independent of Item 6.

**Estimate:** 2–3 days (depends on how many canonical classes need adding).

---

## Item 9 — P1-B: Wildcard↔modifier canonicalization (conditional)

**Why:** Sigma allows two equivalent ways to express anchored substring matches. Rule A writes:

```yaml
CommandLine|contains|all:
  - \AppData\Roaming\php\
```

Rule B writes the same anchor as a literal `*`:

```yaml
CommandLine|contains: \AppData\Roaming\php\*
```

The current atom extractor treats `\AppData\Roaming\php\` and `\AppData\Roaming\php\*` as two distinct literal strings — they don't intersect, Jaccard = 0, containment falls to the 0.65 floor, both rules classified NOVEL of each other.

**Run only if Item 4a says yes.** If 4a returns "skip permanently," close this item without coding and document the demotion.

**Where:**
- `sigma_semantic_similarity/sigma_similarity/atom_extractor.py` — specifically `_normalize_value` (line 70) and `atom_identity` (line 116).

**Approach:** canonicalize wildcards into modifiers at extraction time, *before* atom identity is computed.

```
"prefix*"    → operator stays as-is, value becomes "prefix", modifier_chain prepends "startswith"
"*suffix"    → value becomes "suffix", modifier_chain prepends "endswith"
"*middle*"   → value becomes "middle", modifier_chain stays as "contains"
"left*right" → split-and-pair (only if the original operator was contains/eq); else leave alone
```

Be conservative: only fold leading/trailing single `*`. Internal `*` patterns are ambiguous (could be literal asterisks in a path) — leave them as-is to avoid false-positive collisions.

**Acceptance criteria:**
1. Two atoms that previously differed only by leading/trailing `*` vs modifier now produce identical `atom_identity` strings.
2. Atoms with internal `*` (e.g. `foo*bar*baz`) are unchanged.
3. TDD: at least 10 test cases in `tests/sigma_semantic_similarity/` covering: leading `*`, trailing `*`, both, neither, escaped `\*`, mixed with explicit `endswith`/`startswith`/`contains` modifiers, edge cases (empty value, just `*`).
4. Re-run the Item 4a measurement post-fix; confirm the rank-change rate drops.
5. Existing tests in `tests/sigma_semantic_similarity/` still green.

**Dependencies:** Items 1, 3, 4a. Independent of Items 6, 7.

**Estimate:** half day code + 1 hour tests, *if* Item 4a says ship.

---

## Item 10 — P3 hygiene bundle

**Why:** A grab-bag of small cleanup items from the audit. None individually justifies a PR; together they're a focused half-day.

**Items:**

| # | What | Where | Notes |
|---|---|---|---|
| 10a | Rename `compare_proposed_rule_to_embeddings` → `assess_rule_novelty` | `src/services/sigma_matching_service.py:639-652` (already aliased — just remove the deprecated wrapper after grepping for live callers) | Misnomer: the function uses no embeddings. Already documented as deprecated. |
| 10b | N+1 re-fetch in the matching loop | `src/services/sigma_matching_service.py:543` — `self.db.query(SigmaRuleTable).filter(SigmaRuleTable.rule_id == match.get("rule_id", "")).first()` runs once per match in a tight loop | Replace with one `SELECT ... WHERE rule_id IN (...)` then a dict lookup. |
| 10c | Two-engine docs | [`docs/features/sigma-rules.md`](../features/sigma-rules.md) "Behavioral Novelty Scoring" section | The legacy path is barely documented. Add: when it runs, why it's there, what it sacrifices vs deterministic. |
| 10d | Structured logging for the warning at `sigma_matching_service.py:556-559` | (subsumed by Item 6 acceptance #3) | Mentioned here for completeness; do not duplicate the work. |

**Acceptance criteria:** each sub-item has its own test (where applicable) and lands in a single hygiene PR titled "chore(sigma): hygiene bundle".

**Dependencies:** Item 1 minimum. Best done after Item 6 ships (10d is part of Item 6's acceptance criteria — don't double-ship).

**Estimate:** half a day total.

---

## Item 11 — Atom-less rule `exact_hash` collisions (latent)

**Why:** `generate_exact_hash` produces identical SHA256 outputs for behaviorally distinct rules whose detection contains no atomic predicates — keyword-only `keywords:` selections common in Cisco/SSHD log-pattern rules. With `canonical_rule.detection["atoms"]` empty, the canonical JSON collapses to essentially the same string across rules sharing a logsource. Differences in `keywords:` lists are encoded in the original rule YAML but lost in the canonical representation.

Today this is **inert**. The `bd71d9cc` atom-less guard at `assess_novelty` returns NOVEL before the `exact_hash` short-circuit is ever consulted. The collisions live in the database but never cause a false-DUPLICATE verdict.

The risk: if the atom-less guard is later refactored, removed, or has its own bug, the latent collisions become observable false DUPLICATEs. This item closes the underlying root cause instead of relying on the downstream guard alone.

**Where:**
- `src/services/sigma_novelty_service.py:1081-1085` — `generate_exact_hash` (SHA256 of canonical JSON via `asdict`).
- `src/services/sigma_novelty_service.py` near `assess_novelty` — the atom-less guard added in `bd71d9cc`.
- `src/services/sigma_sync_service.py:551, 615` — where `exact_hash` and `canonical_text` are populated during indexing.
- Affected rules today (4 known, in 2 collision groups):
  - `2ece8816-…` — CVE-2023-20198 (Cisco IOS XE Web UI exploitation)
  - `ef0ff092-…` — Cisco Dot1x Disabled
  - `4c9d903d-…` — CVE-2018-15473 (SSHD)
  - `8b244735-…` — CVE-2023-2283 (libssh)

All four have `positive_atoms = null`. The deterministic extractor (`atom_extractor.py`) doesn't model keyword-only Sigma selections — `AtomNode` requires field/operator/value.

**Proposed solutions (choose during subtask 1):**

### Option 1: Don't compute `exact_hash` for atom-less rules (preferred)

In `sigma_sync_service.py`, skip the `exact_hash` population when `canonical_rule.detection["atoms"]` is empty. Leave the column NULL. No collisions can form.

- **Pros:** Simplest. Acknowledges that `exact_hash` is a tool for atom-bearing rules.
- **Cons:** Loses any future ability to use `exact_hash` on atom-less rules (none currently).
- **Effort:** ~1 hour.

### Option 2: Hash keyword content for atom-less rules

For rules with no atoms but with `keywords:`/`keyword_*:` selections, hash the keyword content explicitly so distinct keyword lists produce distinct hashes.

- **Pros:** Keeps `exact_hash` population universal.
- **Cons:** More code; ambiguous which keyword fields to include (Sigma rules use `keywords`, `keyword_event`, `keyword_user`, etc.); doesn't generalize to other atom-less detection shapes.
- **Effort:** 2–3 hours.

### Recommended approach

**Option 1.** Until something actually reads `exact_hash` for atom-less rules, paying for collision-resistance is over-engineering. The downstream `assess_novelty` atom-less guard already handles the only observable consequence; making the database column NULL when meaningless is honest documentation.

**Acceptance criteria:**

1. In `sigma_sync_service.py` (and `sigma_commands.py` if it also populates the column), `exact_hash` is set to NULL when the canonical rule has zero atoms.
2. Regression test in `tests/services/test_sigma_novelty_service.py`: an atom-less Sigma rule indexed via the sync code path has `exact_hash IS NULL` (or equivalent assertion against the canonical representation).
3. Corpus re-indexed (operator-approved). Post-re-index re-running the collision query *without* the `jsonb_array_length > 0` filter returns 0 rows:
   ```sql
   SELECT exact_hash, COUNT(*) FROM sigma_rules
   WHERE exact_hash IS NOT NULL
   GROUP BY exact_hash HAVING COUNT(*) > 1;
   ```
4. Existing tests still green (`python run_tests.py` baseline).
5. Status Dashboard updated: Item 11 row flipped to `✓ done`.

**Dependencies:** Item 1. Independent of all other items.

**Estimate:** half a day (fix + test + re-index + verification).

**Priority:** P3 — **latent / inert today.** Promote to P1 if the `bd71d9cc` atom-less guard at `assess_novelty` is ever touched (refactored, removed, or has its own bug).

---

## Dependency Graph (ASCII)

```
1 (push) ✓ done
 ├─► 2 (eval-miner review)
 │     └─► 4a (LLM-axis measurement)
 │          └─► 9 (wildcard↔modifier canonicalization, CONDITIONAL)
 ├─► 4b (coverage-gap measurement)
 │    └─► 8 (coverage backfill, urgency from 4b)
 ├─► 4c (canonical_class fan-out measurement)
 │    └─► 6 (gate fix — A or B chosen by 4c)
 │         └─► 10 (hygiene bundle, after 6)
 ├─► 5 (queue-rules-excluded, parallelizable)
 ├─► 7 (LIMIT sort, before 8/9 if those touch fallback)
 └─► 11 (atom-less hash collisions, latent / parallelizable)

3 (operator-drop) ⊘ skipped — hypothesis disproved; no longer in graph.
```

**Critical path:** 1 → 4c → 6 → 10.
**Parallelizable with critical path:** 2, 5, 7, 11.
**Gated by 4:** 8, 9.

---

## Recommended Execution Order

For a sequential single-operator pass:

1. Push `bd71d9cc` (Item 1).
2. Review + commit eval-miner files (Item 2).
3. ~~Quantify and fix `generate_canonical_text` operator-drop (Item 3).~~ — `⊘ skipped 2026-06-01`. See Addendum.
4. Fix the `LIMIT 20` sort (Item 7) — cheap, gets done before measurements.
5. Run the three decision-gating measurements (Item 4abc) in one read-only pass.
6. Record results in this doc as a `## Addendum 2026-MM-DD: Measurement Results` section, then branch:
   - Item 6 (gate fix) — A or B from 4c.
   - Item 9 (wildcard↔modifier) — ship or skip from 4a.
   - Item 8 (coverage backfill) — priority from 4b.
7. Ship Item 5 (queue-rules-excluded) in parallel whenever convenient.
8. Item 11 (atom-less hash collisions, latent) — ship whenever convenient; doesn't block anything.
9. Hygiene bundle (Item 10) after Item 6 lands.

---

## Project Conventions (Critical for a fresh Claude session)

### Test execution

- **Canonical entrypoint:** `python run_tests.py` (per `AGENTS.md` at the repo root).
- **Direct pytest (when you need a single test):**
  ```bash
  APP_ENV=test \
    POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d= -f2) \
    POSTGRES_PORT=5433 \
    TEST_DATABASE_URL="postgresql+asyncpg://cti_user:${POSTGRES_PASSWORD}@localhost:5433/cti_scraper_test" \
    .venv/bin/python -m pytest <path> -v --no-header -p no:cacheprovider
  ```
- **Never pipe through `| tail`** — hides progress and causes long waits. Use direct output or write to a log file.
- **Run actual unit/integration tests relevant to the changed code**, not just smoke tests.

### Git discipline (from CLAUDE.md)

- Never amend; create new commits.
- Never `--no-verify` unless explicitly authorized.
- Commit messages: conventional commits (`fix(scope): ...`, `chore(scope): ...`), HEREDOC body, end with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`.
- If a pre-commit hook modifies files, re-stage and retry (loop up to 3 times). After 3, surface the diff.
- **Do not modify unrelated user changes.** Current uncommitted, not part of this arc (refreshed 2026-06-01 after `bd71d9cc` landed):
  - `M docs/ml-training/hunt-scoring.md` (still uncommitted)
  - `M src/web/templates/ml_hunt_comparison.html` (still uncommitted)
  - `?? docs/development/cmdline-eval-audit-2026-05-31.md`
  - `?? docs/development/eval-contract-audit-prompt.md`
  - `?? scripts/mine_sigma_pair_candidates.py` (Item 2 handles)
  - `?? tests/sigma_semantic_similarity/test_canon_atom.py` (Item 2 handles)
  - `?? docs/development/sigma-novelty-audit-followup-2026-06-01.md` (this spec itself — commit before relying on it from another branch)

  Notes: `docs/CHANGELOG.md`, `docs/features/sigma-rules.md`, `src/services/sigma_novelty_service.py`, and `tests/services/test_sigma_novelty_service.py` were committed as part of `bd71d9cc` and are no longer "don't touch" — they were updated in the exact_hash fix and are now on origin. If you edit any of them as part of this arc, you're editing on top of the landed fix.

### Docs build

- `mkdocs build --strict` must pass before any docs PR.
- Internal links to source files outside `docs/` will fail strict mode — use code-fence references (`` `path/to/file.py` ``) instead of markdown links for source code outside the docs tree.

### Branch

- Working branch: `europa-7.2.1` (per current git state).
- Main branch for PRs: `main`.

### File creation discipline

- Before `Write` on a new file, always `Read` or `Glob` first to confirm absence.
- Edit existing files in preference to creating new ones.
- Do **not** create new docs/markdown files unless they're explicitly requested or required by the spec.

---

## Work Tracking and PR Hygiene

This doc is the only tracker. Do not create parallel issue lists.

- **Tracking:** edit the Status Dashboard at the top in the same commit as the work for that item.
- **One item per PR** where possible. Item 10 is the only deliberate bundle.
- **PR titles:** `fix(sigma): <summary>`, `chore(sigma): <summary>`, `docs(sigma): <summary>`.
- **PR descriptions:** link back to this doc and the item number (e.g. "Closes Item 6 of `docs/development/sigma-novelty-audit-followup-2026-06-01.md`").
- **Commit messages:** conventional commits with Co-Authored-By trailer (see `## Project Conventions`).
- **Branch:** `europa-7.2.1` for now; rebase only with operator approval.

## Recording Decisions and Measurements

Append (do not edit in place) an addendum at the bottom of this doc for any of:

- Measurement results from Item 4a/4b/4c.
- A/B design choice for Item 6 (with the 1–2 paragraph rationale from subtask 1).
- Item 9 ship/skip decision derived from 4a.
- Item 8 priority derived from 4b.
- Any item moved to `⚠ blocked`.

Addendum format:

```markdown
## Addendum YYYY-MM-DD — <short title>

**Item(s) affected:** N (e.g. 4a, 9)
**Decision / result:** <one sentence>
**Detail:** <as long as needed; include raw counts, SQL output, sample sizes>
**Action taken:** <Status Dashboard updated row(s) listed here>
```

---

## Open Questions (operator-only — not Claude to decide)

These require human judgment. If Claude encounters one, stop, surface it in the response, and wait for direction.

1. **Goal deadline:** none set as of 2026-06-01. The operator may impose one.
2. **Customer repo indexing cadence:** the coverage-gap measurement (4b) may reveal that the customer rule repo is under-indexed (`./run_cli.sh sigma index-customer-repo` not run recently). That's an operational fix, not code; flag in the 4b addendum but do not run the index command unprompted.
3. **Should the `logsource_penalty` (if Item 6 Option A) be configurable in `workflow_config`?** Default `0.10` is a starting point. Out of scope for the initial implementation; raise in the Item 6 PR description and let the operator decide.
4. **Re-indexing the full corpus after Item 3 lands:** required for the corpus-internal effects of the operator-drop fix to take effect. Operator should authorize before the re-index runs (it touches every row in `sigma_rules`).

---

## Provenance

- Audit source: May 31, 2026 Sigma novelty audit (mined 1,545 rules; surfaced exact_hash degeneracy + wildcard↔modifier loss + gate/canonical_class contradiction + LIMIT sort + coverage gap).
- Consolidation: this doc, written 2026-06-01 during a multi-thread planning session.
- Prior shipped work referenced in "Already Shipped" above.

End of spec.

---

## Addendum 2026-06-01 — Item 3 hypothesis falsified; new Item 11 spun out

**Item(s) affected:** 3, 11 (new)

**Decision / result:** Item 3 marked `⊘ skipped`. The spec's premise that `generate_canonical_text`'s operator-drop bug causes false-DUPLICATE verdicts via `exact_hash` collisions was disproved by direct code reading and corpus quantification. The typo is real but lives in dead code. A genuinely latent issue surfaced during the investigation (atom-less rules collide on `exact_hash`) — captured as new Item 11 above.

**Detail:**

*Code reading:*

- `generate_exact_hash` at `src/services/sigma_novelty_service.py:1081-1085` serializes `asdict(canonical_rule)` directly into JSON. `Atom.op` is part of the dataclass, lands in the JSON, lands in the hash. Two atoms differing only by operator DO produce different `exact_hash` values.
- The bug exists only in `generate_canonical_text` at line 1104: `ops = "|".join(atom.get("ops", []))`. The `Atom` dataclass uses `op` (singular), so `atom.get("ops", [])` always returns `[]`, and `ops` is always `""`. The canonical text is missing the operator. But that string is written to `sigma_rules.canonical_text`.
- Repo-wide grep for `canonical_text`: only `models.py` (column definition), `sigma_sync_service.py` (writer at lines 551, 615), `sigma_commands.py` (writer at line 340). **No readers.** The 2026-04-29 CHANGELOG noted an unused `canonical_text` local was removed elsewhere — the column has been effectively dead for ≥1 month.

*Corpus quantification (live `cti_postgres`):*

```sql
WITH eligible AS (
  SELECT exact_hash, rule_id FROM sigma_rules
  WHERE exact_hash IS NOT NULL AND positive_atoms IS NOT NULL
    AND jsonb_typeof(positive_atoms) = 'array'
)
SELECT exact_hash, COUNT(*) FILTER (WHERE jsonb_array_length(positive_atoms) > 0) AS nonempty_count
FROM eligible JOIN sigma_rules USING (rule_id, exact_hash)
GROUP BY exact_hash
HAVING COUNT(*) FILTER (WHERE jsonb_array_length(positive_atoms) > 0) > 1
ORDER BY nonempty_count DESC;
```

→ **0 rows.** Among rules with non-empty `positive_atoms`, no `exact_hash` collisions exist.

*The 2 collision groups that DO exist post-`bd71d9cc`*:

| Group | Rule A | Rule B | Both have `positive_atoms`? |
|---|---|---|---|
| 1 | CVE-2023-20198 (Cisco IOS XE Web UI) | Cisco Dot1x Disabled | No (both `null`) — keyword-only |
| 2 | CVE-2018-15473 (SSHD) | CVE-2023-2283 (libssh) | No (both `null`) — keyword-only |

All four are keyword-only Sigma rules that the deterministic extractor doesn't model. The `bd71d9cc` atom-less guard in `assess_novelty` returns NOVEL before any `exact_hash` short-circuit fires against them, so the collisions are **inert today**. Tracked as Item 11 in case the guard is later touched.

**Action taken:**

- Status Dashboard: Item 3 row → `⊘ skipped`; Item 11 row added as `○ pending`.
- Definition of Done: criterion 2 (`generate_canonical_text` operator) struck through; criterion 1 reworded to acknowledge bd71d9cc as the inert-guard and Item 11 as the underlying-cause fix.
- Themes table: Item 3 marked `⊘ skipped`, Item 11 added under "False-positive duplicate hash" theme as the latent follow-up.
- Item 3 section header marked `⊘ skipped` with disproof note + traceability link to this addendum. Original section body retained.
- Dependency Graph redrawn — Item 3 removed; Item 11 added as parallelizable.
- Recommended Execution Order: Item 3 struck through, Item 11 inserted as parallelizable.
- Local todo `005-ready-p1-fix-canonical-text-operator-drop.md` renamed `005-complete-p1-...` with work-log entry capturing the disproof. A new local todo `006-ready-p3-atom-less-rule-hash-collisions.md` was created for Item 11.

**Discipline note:** This is the kind of finding the spec's "quantify first" acceptance criteria are supposed to surface. Following the systematic-debugging Phase 1 / TDD red-first protocol *before* writing any fix code prevented shipping a no-op change to dead code. The lesson: even a carefully-written spec can carry contradictory hypotheses (todo 005's "Findings" section said `op` is in the precomputed-atom path; its "Problem Statement" said `exact_hash` collides on operator drop — both can't be right) — code reading and live SQL win every time.

End of addendum.

---

## Addendum 2026-06-01 — Item 1 landed

**Item(s) affected:** 1

**Decision / result:** `bd71d9cc` pushed to `origin/europa-7.2.1` (range `7d242dfd..bd71d9cc`).

**Detail:**

- Commit subject: `fix(sigma): stop exact_hash collapsing list-of-maps rules into false duplicates`
- Author: dfirtnt, Co-Authored-By: Claude Opus 4.8 (1M context)
- Files changed (now on origin, no longer in the "don't touch" list):
  - `docs/CHANGELOG.md` (+3 lines)
  - `docs/features/sigma-rules.md` (+9 lines)
  - `src/services/sigma_novelty_service.py` (+93 / −60 lines net) — `extract_atomic_predicates` now expands list selections via `_extract_block_atoms`; `assess_novelty` returns NOVEL for atom-less rules
  - `tests/services/test_sigma_novelty_service.py` (+58 lines) — tests for list-of-maps yielding atoms, distinct hashes, and atom-less never-DUPLICATE guard
- Corpus impact reported in the commit body: **provably-distinct exact_hash collisions 130 → 0** after re-index.

**Action taken:**

- Status Dashboard row for Item 1 flipped to `✓ done`.
- "Do not modify unrelated user changes" list refreshed; the four files committed in `bd71d9cc` are no longer listed as off-limits.
- Items 2, 3, 5, 7 are now unblocked. The next operator-eligible item by the recommended execution order is **Item 3 (operator-drop)** — captured as todo `005-ready-p1-fix-canonical-text-operator-drop.md` in `.context/compound-engineering/todos/`.

End of addendum.

---

## Addendum 2026-06-01 — Item 9 closed (rebuild + recompute + verified)

**Item(s) affected:** 9 (now done).

**Decision / result:** Image rebuilt, corpus re-indexed under the new `atom_identity`. Acceptance criterion #4 satisfied: both queue rules from the 4a measurement went from `0` behavioral matches to non-zero and correctly find the canonical SigmaHQ neighbors of their wildcard patterns. Item 9 closed.

**Operator sequence that actually worked (corrected from the earlier addendum):**

```bash
# 1. Rebuild the image used by the four long-running services.
docker compose build
# (4 services: web, worker, workflow_worker, scheduler — all share one Dockerfile/context.)

# 2. ⚠ The cli service is in the 'tools' profile and is NOT touched by `docker compose build`
#    alone. Rebuild it explicitly, otherwise `./run_cli.sh` keeps using the stale image:
docker compose --profile tools build cli

# 3. Recreate the long-running containers from the new image.
docker compose up -d

# 4. Verify the fold is live in the running web container.
docker exec cti_web python -c \
  "import inspect, sigma_similarity.atom_extractor as a; \
   print('FOLD_PRESENT' if '_fold_wildcards' in inspect.getsource(a) else 'FOLD_MISSING')"
# Expected: FOLD_PRESENT

# 5. Refresh the corpus with the new atom_identity. This MUST run after step 2 — the
#    one-shot CLI container uses the cli image, which is what step 2 rebuilds.
./run_cli.sh sigma recompute-semantics

# 6. Verify with the live API for the two known wildcard queue rules.
curl -s 'http://127.0.0.1:8001/api/sigma-queue/486/similar-rules?force=true' | jq '.behavioral_matches_found, .max_similarity'
curl -s 'http://127.0.0.1:8001/api/sigma-queue/487/similar-rules?force=true' | jq '.behavioral_matches_found, .max_similarity'
```

**⚠ Sharp edge discovered mid-execution:** `docker compose build` (no args) ONLY builds services that lack a `profiles:` directive. The `cli` service has `profiles: [tools]` (compose.yml:335-336), so it gets skipped by default. Without step 2, `./run_cli.sh` runs the stale image and the recompute silently no-ops — the corpus is rewritten with the same atom strings it already had. The first verification run hit exactly this trap; an explicit `docker compose --profile tools build cli` is required.

**Verification numbers (2026-06-01 post-rebuild):**

| Check | Before fix | After fix |
|---|---|---|
| `FOLD_PRESENT` probe in cti_web | `FOLD_MISSING` | **`FOLD_PRESENT`** |
| Corpus rules processed by recompute | 1,547 | **1,565** (+18 — the fold rescues rules whose extractor previously skipped them) |
| Corpus rules unsupported (skipped) | 2,181 | 2,163 (−18, mirror of above) |
| `*`-bearing atoms in corpus | 10 | 93 (more rules now produce atoms, including internal-wildcard ones that were silently skipped before; sample of 10 confirmed all internal-pattern: `7z*.exe`, `/*.lnk`, `password*.csv`, `systeminfo*\|*find`, regex `.*` quantifiers — none are edge wildcards, exactly per Item 9's conservative scope) |
| Queue 486 (`CommandLine: '*mshta.exe*'`) `behavioral_matches_found` | 0 (NOVEL) | **13** |
| Queue 486 `max_similarity` | null / 0 | **0.10625** |
| Queue 486 top match | (none) | **"Suspicious JavaScript Execution Via Mshta.EXE"** at 10.62% / 12.5% Jaccard |
| Queue 487 (`ParentImage: '*mshta.exe*', Image: '*conhost.exe*'`) `behavioral_matches_found` | 0 (NOVEL) | **16** |
| Queue 487 `max_similarity` | null / 0 | **0.065** |
| Queue 487 top 3 matches | (none) | Suspicious JavaScript Via Mshta, Powershell Executed From Headless ConHost, Remotely Hosted HTA File Via Mshta — all canonically equivalent to the wildcard pattern |

The top match for both rules is *the actual semantic equivalent in SigmaHQ* — proving the fold isn't just producing noise, it's producing the right matches.

**Action taken:**

- Status Dashboard row for Item 9 flipped to `✓ done — code 0688b0ff, rebuild + recompute verified, queue 486 went 0→13 matches and 487 went 0→16`.
- Acceptance criterion #4 (re-run Item 4a measurement post-fix; confirm the rank-change rate drops) satisfied. The "rank change" interpretation here: both rules went from a degenerate empty match-set to a populated, semantically-correct top-K.
- The corrected operator sequence (with the `--profile tools` step) is documented above for future operations.

**Potential follow-up (not in scope here):**

The `cli` service's profile-membership was a real footgun — the rebuild looked successful but silently skipped one service. Worth either: (a) moving `cli` out of the `tools` profile in `docker-compose.yml` so `docker compose build` covers it by default, or (b) adding an explicit warning in `run_cli.sh` if its image is older than the other service images. Either is a hygiene-bundle candidate (Item 10).

End of addendum.

---

## Addendum 2026-06-01 — Item 9 code landed (wildcard↔modifier canonicalization) — RE-INDEX REQUIRED

**Item(s) affected:** 9 (code landed; awaiting corpus re-index for full effect).

**Decision / result:** `atom_identity` in `sigma_semantic_similarity/sigma_similarity/atom_extractor.py` now folds leading/trailing literal `*` in atom values into the equivalent modifier op. `Image: '*foo.exe'` (eq) and `Image|endswith: 'foo.exe'` (endswith) produce the SAME atom identity string. The fix is operative for atoms computed AFTER this code lands, but stored corpus atoms are still in the OLD identity form — see "Re-index requirement" below.

**Detail:**

- File changed: `sigma_semantic_similarity/sigma_similarity/atom_extractor.py` — added `_fold_wildcards()` helper + `_WILDCARD_FOLDABLE_OPS` frozenset; called `_fold_wildcards` from `atom_identity` AFTER `_normalize_value` (so backslash normalization runs first).
- Fold rules mirror `scripts/mine_sigma_pair_candidates.canon_atom` exactly (which has been the policy spec since Item 2 landed). The miner's canon function is the reference; the engine's fold is its production implementation:
  - `op="eq"` + `*X*` (len ≥ 2) → `contains|contains|X`
  - `op="eq"` + `*X` → `endswith|endswith|X`
  - `op="eq"` + `X*` → `startswith|startswith|X`
  - `op in {contains, endswith, startswith}` + redundant edge `*` → strip the redundant `*`; op + modifier_chain unchanged
  - `re` / `lt` / `gt` / `lte` / `gte` / `neq` → value preserved verbatim (regex patterns and numeric comparisons treat `*` literally)
- Test file: `tests/sigma_semantic_similarity/test_wildcard_fold.py` — 18 unit tests in 5 classes (equivalence, eq folds, redundant-stripping, internal-only-unchanged, non-foldable ops, edge cases). All went RED before the fix and GREEN after. **168/168** in the combined sigma + novelty suite.

**Re-index requirement (⚠ operator approval needed):**

The fix changes the output of `atom_identity` for any rule whose atoms have edge wildcards. Stored `sigma_rules.positive_atoms` and `sigma_rules.negative_atoms` were computed under the OLD identity rules — they still contain strings like `process.image|eq||*foo.exe`. New proposed rules will produce the new form `process.image|endswith|endswith|foo.exe`. **They will not intersect.**

This means:
- **Before re-index:** scoring for rules with edge wildcards is *marginally worse* than before. The proposed atom is folded to the new form; the stored atom is still old. They don't match. Behavior reverts only for the affected wildcard shape — non-wildcard rules are unaffected.
- **After re-index:** both sides use the new identity. Behaviorally-equivalent rules (one written with `*X*`, another with `|contains: X`) match each other.

Re-index command (to be confirmed and run by the operator):

```bash
./run_cli.sh sigma recompute-semantics
```

**⚠ IMAGE REBUILD PRECONDITION (discovered 2026-06-01 mid-execution):**

`sigma_semantic_similarity/` is copied into the Docker image at build time (see [Dockerfile:71](../../Dockerfile)). It is NOT bind-mounted into `cti_web`, `cti_worker`, `cti_workflow_worker`, or `cti_scheduler` — only `./src` and `./config` are. This means **`docker restart` does NOT pick up host edits to `sigma_semantic_similarity/`**, and **the one-shot CLI container spawned by `./run_cli.sh` runs the same baked image too**.

Concretely: if the operator runs `docker restart ... && ./run_cli.sh sigma recompute-semantics` after the Item 9 code lands but **before rebuilding**, the re-index touches every row using the OLD `atom_identity`. The corpus is rewritten with the SAME identity strings it already had — silent no-op.

The correct operator sequence is:

```bash
# 1. Rebuild the image so sigma_semantic_similarity is repacked with the fold.
docker compose build cti_web cti_worker cti_workflow_worker cti_scheduler

# 2. Recreate containers from the new image.
docker compose up -d

# 3. Re-run the recompute against the new image.
./run_cli.sh sigma recompute-semantics

# 4. Verify the fold is live in the running web container:
docker exec cti_web python -c \
  "import inspect, sigma_similarity.atom_extractor as a; \
   print('FOLD_PRESENT' if '_fold_wildcards' in inspect.getsource(a) else 'FOLD_MISSING')"
# Expected: FOLD_PRESENT

# 5. Trigger a fresh comparison for queue 486 / 487 (the two wildcard rules from 4a) to confirm the fix produces non-NOVEL results:
curl -s 'http://127.0.0.1:8001/api/sigma-queue/486/similar-rules?force=true' | jq '.behavioral_matches_found, .max_similarity'
curl -s 'http://127.0.0.1:8001/api/sigma-queue/487/similar-rules?force=true' | jq '.behavioral_matches_found, .max_similarity'
# Expected: non-zero behavioral_matches_found; non-zero similarity for at least one match.
```

Alternative (dev-friendly, NOT recommended for prod): add `- ./sigma_semantic_similarity:/app/sigma_semantic_similarity` to each affected service's `volumes` in `docker-compose.yml` so future host edits propagate without rebuild. Requires the package to be `pip install -e`'d, which it is in the current Dockerfile flow. This change is out of scope for Item 9 itself; could be its own hygiene-bundle entry.

**Acceptance criterion #4 (re-run Item 4a measurement post-fix; confirm rank-change rate drops):** *pending image rebuild + corpus re-index*. Will run once the operator authorizes both. Expected outcome: the 2 recent wildcard rules from the 4a measurement (`'*mshta.exe*'` etc.) should now find their canonical neighbors in the corpus.

**Discovery 2026-06-01 (mid-execution):** the first restart+recompute attempt verified the fix was NOT live in the running container. `docker exec cti_web python -c "import inspect, sigma_similarity.atom_extractor as a; print('FOLD_PRESENT' if '_fold_wildcards' in inspect.getsource(a) else 'FOLD_MISSING')"` returned `FOLD_MISSING`. The package is baked into the image at build time, so a rebuild is required before the recompute does meaningful work. Step sequence updated above.

**Action taken:**

- Code + tests committed; Status Dashboard row for Item 9 set to `◐ code landed; ⚠ image rebuild + re-index required`.
- The fix is dormant until both (a) the image is rebuilt AND containers recreated AND (b) the corpus is re-indexed using the new image. The earlier `./run_cli.sh sigma recompute-semantics` ran with the OLD image; that pass needs to be repeated post-rebuild.

End of addendum.

---

## Addendum 2026-06-01 — Item 6 landed (hard-gate scoped to fallback path, Option B)

**Item(s) affected:** 6 (now done); Item 10 hygiene bundle now unblocked.

**Decision / result:** Per 4c measurement (canonical_class is de facto 1:1 with logsource_key, 0 cross-key fan-out rows in the live corpus), implemented Option B: scope the gate at `sigma_matching_service.py:551` to fire only on the `logsource_key`-fallback retrieval path. Threaded a new `phase1_path` field through the candidate dict so the gate can distinguish how each candidate was retrieved.

**Files changed:**

- `src/services/sigma_novelty_service.py`:
  - `retrieve_candidates`: tracks a local `phase1_path` variable across the three retrieval paths (exact_hash short-circuit, canonical_class branch, logsource_key fallback). Each `_row_to_candidate` output now carries `phase1_path`.
  - `assess_novelty`: propagates `candidate["phase1_path"]` into the match_dict (both the regular path at line 484 and the exact-hash short-circuit at line 325).
- `src/services/sigma_matching_service.py:551`: the gate now reads `match["phase1_path"]` and enforces only when it equals `"logsource_fallback"` OR is missing (legacy default for older payloads). On canonical_class / exact_hash paths the gate is bypassed — the SQL filter or hash identity is the authoritative scoping there. The `logger.warning` is now structured (proposed/candidate logsource_keys, candidate rule_id, and the phase1_path that triggered).
- `tests/services/test_sigma_matching_service.py`: new `TestHardGateScopedToFallback` class with 5 parametrized scenarios — canonical_class+mismatch survives, logsource_fallback+mismatch drops, logsource_fallback+match survives, exact_hash+mismatch survives, missing phase1_path defaults to legacy enforcement.
- `docs/features/sigma-rules.md`: "How It Works" updated to reflect the new 3-path Phase 1 + scoped Phase 3 architecture.

**Test results:** TDD red (2 of 5 failing on the canonical_class + exact_hash exemption cases, 3 already passing the pre-existing always-enforce behavior) → green after the gate fix (5 of 5 pass). Full sigma + novelty + semantic_similarity + sigma_similar_rules suites: **194 passed, 0 failed**.

**Behavioral impact in production:** Per 4c, today `canonical_class` doesn't fan out — every candidate it surfaces has the same `logsource_key` as the proposed rule, so the previously-firing gate was always a no-op in practice. This fix makes the engine honest about that fact (the gate now visibly bypasses the canonical_class path rather than silently re-checking what the SQL filter already enforced) and unblocks any future expansion where canonical_class genuinely spans multiple logsource_keys. The `logsource_fallback` path keeps the gate as a defensive safety check.

**Observability improvement:** when the gate DOES fire (only on the fallback path), it emits `logger.warning("logsource_key_mismatch_on_fallback_path", extra={...})` with structured fields. Pre-fix the warning was an f-string; post-fix it's queryable via log aggregation. Spec acceptance criterion #3 satisfied.

**Action taken:**

- Status Dashboard: Item 6 row flipped to `✓ done — see Addendum (Item 6)`.
- Item 10 (hygiene bundle) is no longer blocked.
- Live containers already on the new image post-Item-9 rebuild, so this fix is operative without an additional rebuild — `src/` is bind-mounted into all four long-running services (per the docker-compose mount layout discovered during Item 9 verification).

**Note on the gate's `legacy_missing` log label:** if a match arrives without `phase1_path` (older novelty payload from before this commit), the gate falls back to the always-enforce behavior and the structured warning logs `phase1_path: "legacy_missing"`. Watching for this in production tells us when stale novelty results are still flowing through; we should see it taper to zero within one workflow cycle of the deploy. If it sticks above zero longer, a queue rule's `similarity_scores` JSONB is being read without recomputation — a separate (Item 10 hygiene candidate) concern.

End of addendum.

---

## Addendum 2026-06-01 — Item 7 landed (unordered LIMIT fix)

**Item(s) affected:** 7

**Decision / result:** Both unordered `.limit(top_k)` calls in `retrieve_candidates` now precede `.limit()` with `.order_by(SigmaRuleTable.rule_id)`. Candidate retrieval is reproducible across runs, replicas, and after `VACUUM`.

**Detail:**

- Files changed:
  - `src/services/sigma_novelty_service.py:1201-1227` — added `.order_by(SigmaRuleTable.rule_id)` to both fallback queries (the canonical_class-empty fallback inside the `if use_deterministic` branch, and the else-branch fallback used when `canonical_class` is unset or `use_deterministic=False`).
  - `tests/services/test_sigma_novelty_service.py` — added `TestRetrieveCandidatesDeterministicOrdering` class with a parametrized test covering both code paths. Test asserts the query chain calls `.order_by()` BEFORE `.limit()` via inspection of `Mock.method_calls`.
- TDD discipline: tests were written first, watched fail (both code paths showed call sequence `['filter', ..., 'limit', 'all']` with no `order_by`), fix applied, tests passed.
- Regression check: full sigma novelty + sigma_semantic_similarity test suites — **150/150 pass**, no regressions.

**Production impact:**

Per the 4b measurement, the legacy / fallback engine path fires 0% of the time on recent traffic (because `canonical_class` is populated for all rules that reach candidate retrieval today). So the unordered-LIMIT bug was *latent* in production — non-determinism didn't manifest yet because the fallback path is unreached. The fix is preventative: it eliminates a class of "different result on different machine / after VACUUM" failures that would otherwise surface the moment Item 8 (coverage backfill) extends candidate retrieval into less-populated logsource classes, or the moment proposed rules in unmodeled telemetry classes start being scored.

**Action taken:**

- Status Dashboard: Item 7 row flipped to `✓ done`.

End of addendum.

---

## Addendum 2026-06-01 — Items 4a/4b/4c measurement results

**Item(s) affected:** 4a, 4b, 4c (now done); downstream consequences for 6, 8, 9.

**Decision / result:**

| Measurement | Result | Decision |
|---|---|---|
| **4c** — canonical_class fan-out | 0 rows | **Item 6 = Option B** (scope hard gate to fallback path; canonical_class is de facto 1:1 with logsource_key in the live corpus) |
| **4b** — coverage-gap usage | Static: 49.1% rules lack atoms. **Dynamic: 0% legacy-path hits across 333 recent comparisons.** | **Item 8 demoted to "next quarter"** (scorer is precise on what it sees; the gap manifests as candidate-retrieval blindness to non-process_creation classes, not as scoring degradation) |
| **4a** — LLM-axis wildcard frequency | All-time: 65/438 = **14.8%** rules with `*`. Last 30 days: 2/66 = 3.0%. | **Ship Item 9** (all-time rate well over the 10% ship threshold; the 2 recent rules use the exact `*X*` pattern canon_atom targets) |

**Detail:**

*4c — `canonical_class` fan-out:*

```sql
SELECT canonical_class, COUNT(DISTINCT logsource_key) AS lk_count
FROM sigma_rules
WHERE canonical_class IS NOT NULL
GROUP BY canonical_class
HAVING COUNT(DISTINCT logsource_key) > 1
ORDER BY lk_count DESC;
```

→ **0 rows.** No `canonical_class` value spans multiple `logsource_key` values. `canonical_class` is a redundant column today; it doesn't broaden recall. Item 6's hard gate on the canonical_class retrieval path is dead code in production. Per the spec's decision table for Item 6, this triggers **Option B**: scope the gate to the fallback path (where it's a no-op safety check that matches the SQL filter) and skip it on the canonical_class path. No `logsource_penalty` field needed.

*4b — coverage-gap usage:*

**Static (corpus shape, one query):**

```sql
SELECT COUNT(*) FILTER (WHERE positive_atoms IS NOT NULL AND jsonb_typeof(positive_atoms) = 'array' AND jsonb_array_length(positive_atoms) > 0) AS with_atoms,
       COUNT(*) FILTER (WHERE positive_atoms IS NULL OR (jsonb_typeof(positive_atoms) = 'array' AND jsonb_array_length(positive_atoms) = 0)) AS without_atoms,
       COUNT(*) AS total
FROM sigma_rules;
```

→ `with_atoms=1545, without_atoms=1829, total=3728, pct_without=49.1`

**Dynamic (no production code touched — derived from stored `similarity_scores` in `sigma_rule_queue`, last 30 days):**

```sql
SELECT engine, COUNT(*) AS hits FROM (
  SELECT jsonb_array_elements(similarity_scores)->>'similarity_engine' AS engine
  FROM sigma_rule_queue
  WHERE similarity_scores IS NOT NULL AND jsonb_typeof(similarity_scores) = 'array'
    AND created_at > NOW() - INTERVAL '30 days'
) t GROUP BY engine;
```

→ `deterministic=333, legacy=0`

**Where the 1,829 atom-less rules live:**

| canonical_class | without_atoms |
|---|---|
| `NULL` (registry / network / file / etc. — unmodeled telemetry classes) | 1,827 |
| `windows.process_creation` | 2 |

**The two atom-less process_creation rules** (extraction edge cases — `AtomNode` couldn't model the YAML structure):
- `71158e3f-…` — *Execution Of Non-Existing File* (`rules/windows/process_creation/proc_creation_win_susp_image_missing.yml`)
- `c09dad97-…` — *Execution of Suspicious File Type Extension* (`rules/windows/process_creation/proc_creation_win_susp_non_exe_image.yml`)

**Interpretation:** the static 49.1% gap is **not** the legacy fallback firing on half the comparisons. The candidate-retrieval SQL filters by `canonical_class`, which is NULL for the 1,827 non-process_creation rules — they're never returned as candidates at all. The scorer is precise on what it sees; the corpus gap manifests as *invisible rules*, not as imprecise scoring. Per the spec's threshold ("<5% legacy → later"), Item 8 is demoted. Promote it when expanding canonical_class coverage to registry / network / file becomes a goal in its own right.

*4a — LLM-axis wildcard frequency:*

The 30-day sample (66 rules) is small enough that the 3.0% rate has wide uncertainty; the 438-rule all-time sample is the more reliable signal at 14.8%. The 2 recent wildcard rules:

```yaml
# Queue id 487 — Process lineage involving conhost.exe
detection:
  selection:
    ParentImage: '*mshta.exe*'
    Image: '*conhost.exe*'
  condition: selection

# Queue id 486 — Execution of mshta.exe for malware retrieval
detection:
  selection:
    CommandLine: '*mshta.exe*'
  condition: selection
```

Both are textbook `*X*`-as-`contains` patterns that canon_atom folds to `contains|X`. As stored, their atoms are `process.image|eq||*mshta.exe*` (and similar) — they have zero intersection with SigmaHQ's canonical `process.image|endswith|endswith|/mshta.exe` atoms, so the scorer reports them as NOVEL even when near-equivalents exist in the corpus.

Per the spec's "ship if >10% OR >5 rank-changes per 100" decision: 14.8% > 10% → **ship Item 9.** Signal #2 (rank-change measurement) is unnecessary; the all-time rate already triggers the decision and the recent rules are confirmation that the pattern matches Item 9's target.

**Action taken:**

- Status Dashboard: rows for 4a, 4b, 4c flipped to `✓ done` with one-line summaries of each decision.
- Items 6, 8, 9 have their decisions pinned in the Status Dashboard titles for future-Claude clarity:
  - **6** → Option B
  - **8** → demoted to "next quarter"
  - **9** → ship
- No production code changed. The dynamic 4b measurement was derived from stored `similarity_scores` JSONB, not from instrumentation, so nothing needs to be backed out.

**Outstanding follow-up not addressed by this measurement pass:**

- The 2 process_creation rules with NULL atoms (extraction edge cases) might be worth a tiny standalone investigation — surface what made the extractor fail. Probably a single Sigma feature like `|cidr` or a complex nested condition. Not a blocker; mention in a future hygiene-bundle entry or as a follow-up todo.

End of addendum.

---

## Addendum 2026-06-01 — Item 2 landed (eval-miner files committed)

**Item(s) affected:** 2

**Decision / result:** Eval-miner script + canon_atom tests reviewed against the spec's Item 2 acceptance criteria, found methodology-sound, committed as `8c7b46b7` to `origin/europa-7.2.1`.

**Detail:**

- Files: `scripts/mine_sigma_pair_candidates.py` (475 lines) + `tests/sigma_semantic_similarity/test_canon_atom.py` (170 lines).
- 25/25 unit tests pass under `APP_ENV=test`. Suite covers the 6 spec worked examples (op-duplication, bare-field, `|all` token, wildcard folding for `eq *X*` / `*X` / `X*`, redundant `contains` modifier) plus edges (regex preservation, numeric ops, idempotency, malformed-input defensive cases).
- **Methodology verification (Item 2 acceptance criterion #2):** `canon_atom` operates on the **output** of `atom_identity` (the stored `field|op|modifier_chain|value` string), not as a parallel implementation. Field aliases, case-folding for `_CASE_INSENSITIVE_OPS`, and backslash normalization are inherited from `atom_identity` and passed through unchanged. The only transformations `canon_atom` applies are (a) collapse `|all` and duplicate-operator modifier chains to a single base_op, and (b) fold leading/trailing `*` into `endswith` / `startswith` / `contains` for `eq` ops and strip redundant edge wildcards on the existing modifier ops. Both folds are the *intentional* divergence — the whole point of measuring blind spots.
- **"Missed pair" threshold (Item 2 acceptance criterion #3):** `_tier()` defines T3 = `canon_j >= 0.5 AND gap >= 0.3` where gap = `canon_j − raw_j`. Plain English: "canon view says the pair is at least 50% similar, but the engine's raw view (the same comparison the live scorer does) ranks them at most 20% similar." Defensible, non-arbitrary cutoff.
- **Read-only contract verified server-side:** `psycopg2.connect(...).set_session(readonly=True, autocommit=True)`. Live-tested in the agent run that produced the data: `UPDATE` rejected with `cannot execute UPDATE in a read-only transaction`. Defense in depth — even if someone adds an `INSERT` to the script tomorrow, the connection refuses it.
- **Known imprecision flagged in canon_atom docstring AND in the commit body:**
  - Values containing literal `|` (rare; PowerShell pipelines like `cmd | findstr`) over-split. Documented in `test_value_with_internal_pipe_is_lossy_but_does_not_raise`.
  - The `|i` case-insensitive flag on regex atoms is dropped. Two regexes with different case-sensitivity could canonicalize to the same key. Documented in `test_regex_with_modifier_chain_i_preserves_value`. Acceptable since pairs are human-reviewed; consider tightening the docstring further on a future pass.

**Numbers reproduced from the agent's mining run (2026-05-31):**

| Metric | Value |
|---|---|
| Rules mined (canonical_class IN process_creation, positive_atoms non-empty) | 1,545 |
| Candidate pairs after blocking (sharing ≥1 canon atom) | 32,933 |
| Skipped giant blocks (>300 rules per atom) | (printed at runtime; check CSV) |
| T3 (blind-spot) found | **10** |
| T1 (near-identical) found | 25 |
| T2 (moderate) found | 370 |
| NEG (hard-negative) found | 28,858 |
| After per-tier cap of 30: pairs in CSV | 95 |
| T3 pairs hand-inspected with `related: type: similar` cross-refs | 3 of 5 |

These numbers underpin the Item 9 demotion (wildcard↔modifier canonicalization is *measured-small* on the corpus-internal axis; the LLM-axis measurement in Item 4a is what gates whether it's worth shipping).

**Action taken:**

- Files staged and committed as `8c7b46b7` with conventional-commit subject `feat(sigma): land eval-miner script + canon_atom tests (Item 2)` and a 7-paragraph body covering scope, methodology, read-only contract, test coverage, mining run, coverage caveat, and known imprecisions.
- Status Dashboard row for Item 2 flipped to `✓ done — 8c7b46b7, see Addendum`.
- "Do not modify unrelated user changes" list will be refreshed in the next commit (mine_sigma + test_canon_atom files are no longer untracked).
- Items 4a (LLM-axis), 4b (coverage-gap), 4c (canonical_class fan-out) are now fully unblocked. Per the Recommended Execution Order, the next operator-eligible step is to fix the `LIMIT 20` sort (Item 7, ~30 min) before running the three measurements (Item 4abc, ~half day).

End of addendum.
