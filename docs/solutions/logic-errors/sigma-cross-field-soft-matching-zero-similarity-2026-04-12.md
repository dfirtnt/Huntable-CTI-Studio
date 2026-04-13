---
title: "SIGMA Similarity Returns 0% for Cross-Field Executable Matches"
date: 2026-04-12
category: logic-errors
module: sigma_novelty_service
problem_type: logic_error
component: service_object
symptoms:
  - "Queue UI shows 0% similarity for rules detecting the same executable via different fields"
  - "Similarity Search modal displays 'No Behavioral Overlap Found' despite evaluating 1000+ candidates"
  - "similarity_scores stored as empty list because all candidates had atom_jaccard == 0"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags:
  - sigma
  - similarity
  - jaccard
  - atom-matching
  - cross-field
  - soft-matching
  - process-executable
---

# SIGMA Similarity Returns 0% for Cross-Field Executable Matches

## Problem

The SIGMA rule similarity engine returned 0% Jaccard similarity between rules detecting the same executable (e.g., `\rundll32.exe`) via different detection fields (`Image|endswith` vs `CommandLine|endswith`). The queue UI showed no behavioral overlap even though both rules target the same binary.

## Symptoms

- Queue table showed 0.0% similarity for known-related rules (proposed rule using `Image|endswith: \rundll32.exe` vs SigmaHQ rule using `CommandLine|endswith: \rundll32.exe`)
- Similarity Search modal displayed "No Behavioral Overlap Found" after evaluating 1,167 candidates
- `similarity_scores` was stored as an empty list in the database because the `jaccard > 0` filter discarded all zero-score matches

## What Didn't Work

- **Semantic embedding fallback**: An initial approach added a sentence-level embedding pipeline (EmbeddingService, pgvector queries, frontend badges) as a fallback when Jaccard was zero. This was rejected as over-engineered -- it introduced a second LLM/embedding layer to paper over a structural deficiency in the atom comparison. The user explicitly wanted the fix in the atom/Jaccard computation itself.

## Solution

Three additions to `src/services/sigma_novelty_service.py`, plus frontend/backend filtering:

**1. Process-executable field allow-list** (module-level constant):

```python
_PROCESS_EXE_CANONICAL_FIELDS: set[str] = {
    "process.image", "process.parent_image", "process.command_line",
    "process.parent_command_line", "process.original_file_name",
    "image", "parentimage", "commandline", "parentcommandline",
    "originalfilename", "command_line", "parent_image",
}
```

**2. Value extractor** -- strips the field/operator prefix from an atom string, returning just the value for process-exe fields:

```python
def _extract_exe_value(atom_str: str) -> str | None:
    parts = atom_str.split("|", 1)
    if len(parts) < 2:
        return None
    field = parts[0].lower()
    if field not in _PROCESS_EXE_CANONICAL_FIELDS:
        return None
    segments = atom_str.split("|")
    return segments[-1] if len(segments) >= 3 else None
```

**3. Soft-Jaccard fallback** -- activates only when strict atom intersection is zero. Extracts values, finds shared ones, returns `(shared / union) * 0.5`:

```python
def _soft_exe_jaccard_from_atom_strings(A1, A2, union):
    vals1 = {v for a in A1 if (v := _extract_exe_value(a)) is not None}
    vals2 = {v for a in A2 if (v := _extract_exe_value(a)) is not None}
    shared = vals1 & vals2
    if not shared:
        return 0.0
    return min((len(shared) / len(union)) * 0.5, 1.0)
```

**4. Wired into both comparison paths** (deterministic + legacy):

```python
if atom_jaccard == 0.0:
    soft = _soft_exe_jaccard_from_atom_strings(A1, A2, union)
    if soft > 0.0:
        atom_jaccard = soft
```

**5. Backend filter** (`src/web/routes/sigma_queue.py`): Only matches with `jaccard > 0` are stored.

**6. Frontend filter** (`src/web/templates/sigma_queue.html`): `mapSimilarityResponseFromCache` applies the same `j > 0` filter for cached display.

## Why This Works

Atoms are keyed as `field|operator|op_type|value`. When two rules target the same executable via different fields, strict set intersection is always empty -- zero atoms in common. The soft-matching layer peels off the trailing value segment for any field in the process-executable allow-list, then checks for value-level overlap regardless of which field carried that value. This gives credit for behavioral similarity (both rules fire on the same binary) while the 0.5 dampening factor prevents the score from being conflated with an exact structural match.

The triggering scenario (proposed rule vs SigmaHQ rule 1775e15e) now produces ~8-10% soft Jaccard instead of 0%.

## Prevention

- **Regression tests**: 29 tests in `tests/services/test_soft_exe_jaccard.py` covering `_extract_exe_value` (canonical fields, legacy names, mixed-case, non-process fields), `_soft_exe_jaccard_from_atom_strings` (cross-field sharing, dampening arithmetic, empty sets), and `compute_atom_jaccard` integration (the exact rundll32 scenario, empty CommandLine safety, non-process fields)
- **50% dampening**: Cross-field matches are capped at half the Jaccard an exact atom match would produce, preventing inflated similarity scores
- **Closed allow-list**: Only process-executable fields participate in soft matching. DNS, registry, event ID fields never trigger it, preventing false positives across unrelated detection categories

## Related Issues

- [Sigma Similarity Case-Sensitive Atom Matching](sigma-similarity-case-sensitive-atom-matching-2026-04-08.md) -- prerequisite upstream fix that normalized field aliases and value casing at atom extraction time. This cross-field soft matching is the downstream fallback for cases where normalization alone is insufficient.
- Interactive visualization: `docs/diagrams/similarity-engine-explained.html`
- Feature docs: `docs/features/sigma-rules.md` (cross-field soft matching section)
