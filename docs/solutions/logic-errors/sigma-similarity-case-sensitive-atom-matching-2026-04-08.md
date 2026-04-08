---
title: Sigma Similarity Search Returns Zero Results Due to Case-Sensitive Atom Matching
date: 2026-04-08
category: logic-errors
module: sigma-similarity
problem_type: logic_error
component: service_object
severity: high
symptoms:
  - Similarity Search button returns zero results for all queued rules
  - Field namespace mismatch between LLM-generated and SigmaHQ atoms (image vs process.image)
  - Value casing mismatch reduces Jaccard scores (Delete vs delete)
  - 1,167 candidates evaluated but zero behavioral overlap found
root_cause: logic_error
resolution_type: code_fix
tags:
  - sigma
  - similarity-search
  - atom-extractor
  - jaccard
  - case-sensitivity
  - field-alias
  - novelty-service
  - deterministic-engine
---

# Sigma Similarity Search Returns Zero Results Due to Case-Sensitive Atom Matching

## Problem

The "Similarity Search" button in the SIGMA Rule Preview modal returned zero similar rules for every queued rule, even for rules with obvious SigmaHQ matches (e.g., a vssadmin shadow copy deletion rule vs SigmaHQ's "Shadow Copies Deletion Using Operating Systems Utilities"). The deterministic engine evaluated 1,167 candidates but found zero behavioral overlap.

## Symptoms

- Similarity Search returns "No Behavioral Overlap Found" for all queued rules
- `behavioral_matches_found: 0` in API responses despite correct `canonical_class` matching
- `max_similarity: 0` stored for all queue entries
- SigmaHQ rules confirmed present via MCP search, but deterministic comparison finds no shared atoms

## What Didn't Work

- **Suspected logsource_key filtering too aggressive** -- but `windows|process_creation` was correct and retrieved 1,167 candidates. The candidates were there; the comparison was failing.
- **Suspected `canonical_class` not populated** -- but 1,287 rules had it populated after `recompute-semantics`. The retrieval path was correct.
- **Added `.lower()` to atom sets in novelty service** -- improved value casing but still got zero matches. This fixed the secondary bug but not the primary one. The field namespace mismatch was the real blocker.
- **Only visible when comparing raw atom strings side-by-side**: `command_line|contains|...` (proposed) vs `process.command_line|contains|...` (SigmaHQ). The field name itself was resolving to different namespaces.

## Solution

### Fix 1: Case-insensitive field alias resolution (`atom_extractor.py`)

`FIELD_ALIAS_MAP` only had PascalCase keys (`Image`, `CommandLine`). LLM-generated rules use lowercase/snake_case (`image`, `command_line`), which missed the map entirely.

**Before:**
```python
def _resolve_field(field: str) -> str:
    if field in FIELD_ALIAS_MAP:
        return FIELD_ALIAS_MAP[field]
    return field.lower()
```

**After:**
```python
_FIELD_ALIAS_MAP_LOWER = {k.lower(): v for k, v in FIELD_ALIAS_MAP.items()}
_FIELD_ALIAS_MAP_LOWER.update({
    "command_line": "process.command_line",
    "image": "process.image",
    "parent_image": "process.parent_image",
    "parent_command_line": "process.parent_command_line",
    "process_path": "process.image",
    "process_command_line": "process.command_line",
})

def _resolve_field(field: str) -> str:
    if field in FIELD_ALIAS_MAP:
        return FIELD_ALIAS_MAP[field]
    resolved = _FIELD_ALIAS_MAP_LOWER.get(field.lower())
    if resolved is not None:
        return resolved
    return field.lower()
```

### Fix 2: Case-insensitive value normalization (`atom_extractor.py`)

Sigma's `contains`, `endswith`, `startswith`, and `eq` modifiers are case-insensitive by spec. The atom identity must fold case for these operators.

```python
_CASE_INSENSITIVE_OPS = frozenset({"contains", "endswith", "startswith", "eq"})

def atom_identity(node: AtomNode) -> str:
    field = _resolve_field(node.field)
    op = node.operator.lower()
    mod = node.modifier_chain
    ci = op in _CASE_INSENSITIVE_OPS
    val = _normalize_value(node.value, case_insensitive=ci)
    return f"{field}|{op}|{mod}|{val}"
```

### Fix 3: Runtime normalizer for transition period (`sigma_novelty_service.py`)

The `atom_extractor.py` fix lives in the `sigma_semantic_similarity` package baked into the Docker image, but `src/` is bind-mounted. A runtime normalizer in the novelty service handles the mismatch between newly-computed proposed atoms and old-format stored SigmaHQ atoms:

```python
_ATOM_FIELD_ALIAS = {
    "commandline": "process.command_line",
    "command_line": "process.command_line",
    "image": "process.image",
    "parent_image": "process.parent_image",
    # ...
}

def _normalize_atom_identity(atom_id: str) -> str:
    lowered = atom_id.lower()
    parts = lowered.split("|", 1)
    if len(parts) < 2:
        return lowered
    field, rest = parts
    resolved = _ATOM_FIELD_ALIAS.get(field, field)
    return f"{resolved}|{rest}"
```

Applied to both the comparison path and explainability path in the precomputed-atom fast path (replacing bare `.lower()` calls).

### Results

| Metric | Before | After |
|--------|--------|-------|
| Behavioral matches (vssadmin rule) | 0 | 20 |
| Shadow copy SigmaHQ rule found | No | Yes (sim=0.057) |
| Jaccard for identical-intent rules | 0.125 | 0.500 |
| All existing tests | 25 pass | 25 pass |

### Post-deployment step

Run `sigma recompute-semantics` to regenerate stored atoms with the new normalization:

```bash
./run_cli.sh sigma recompute-semantics
```

## Why This Works

Atom identity strings are the unit of comparison in Jaccard similarity. The format is `field|operator|modifier_chain|value`. When field names resolve to different namespaces (`image` vs `process.image`) or values have different casing (`Delete` vs `delete`), atoms that detect the same behavior are treated as completely different predicates.

The primary bug (field namespace) caused **total failure**: every proposed atom had a different field prefix than every SigmaHQ atom. Zero intersection = zero Jaccard = zero similarity for all 1,167 candidates.

The secondary bug (value casing) caused **reduced accuracy**: even when fields matched, `Delete` and `delete` were different atoms, dropping Jaccard from 0.5 to 0.125.

The runtime normalizer in `sigma_novelty_service.py` is a transition shim. After rebuilding the Docker image and running `recompute-semantics`, stored atoms will have the correct format and the normalizer becomes a no-op safety net.

## Prevention

- **Always use case-insensitive lookup for field alias maps.** LLM-generated outputs are unpredictable in casing and naming conventions. Build a lowercased lookup table at import time and add common snake_case variants.
- **Match normalization to semantic contracts.** If the Sigma spec says `contains` is case-insensitive, the atom identity fingerprint must fold case. The identity string represents behavior, not syntax.
- **Test with LLM-generated rules, not just hand-written rules.** The test suite only used PascalCase fields (standard Sigma format). A single test case with `image` instead of `Image` would have caught the primary bug immediately.
- **After any change to atom identity generation, run `sigma recompute-semantics`** to regenerate stored atoms across the corpus.

## Related Issues

- `docs/features/sigma-rules.md` -- "No Similarity Results" troubleshooting section covers infra causes (sync/index/backfill) but not this case-sensitivity root cause. Consider adding an entry.
- No existing GitHub issues or solution docs cover this problem.
