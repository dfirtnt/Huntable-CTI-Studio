---
title: "AI Agents Incorrectly Attribute pgvector Cosine Similarity to Sigma Deduplication Phase 1"
date: 2026-05-20
category: docs/solutions/documentation-gaps/
module: sigma_matching_service
problem_type: documentation_gap
component: service_object
severity: high
applies_when:
  - agent or developer reasons about the Sigma rule deduplication pipeline
  - code path through assess_rule_novelty (or deprecated compare_proposed_rule_to_embeddings) is being analyzed
  - someone asks how Phase 1 of Sigma novelty assessment retrieves candidates
symptoms:
  - agent concludes Phase 1 deduplication uses pgvector cosine similarity
  - agent cites intfloat/e5-base-v2 (768 dimensions) as the Phase 1 similarity mechanism
  - agent conflates the article→Sigma RAG matching path with the Sigma dedup path
root_cause: inadequate_documentation
resolution_type: documentation_update
related_components:
  - assistant
  - database
tags:
  - sigma-dedup
  - pgvector
  - embeddings
  - misconception
  - ai-agent
  - documentation
  - service-object
  - rag
---

# AI Agents Incorrectly Attribute pgvector Cosine Similarity to Sigma Deduplication Phase 1

## Context

During multiple development sessions, AI agents (including Claude) consistently misidentified the Sigma rule deduplication pipeline as using pgvector cosine similarity with the `intfloat/e5-base-v2` model (768 dimensions). This misconception led to incorrect architectural descriptions, misleading explanations of similarity scores, and at least one rejected attempt to add an embedding fallback to the dedup pipeline (see Related section).

Three compounding signals in `sigma_matching_service.py` pointed agents toward the wrong conclusion:

1. The module-level docstring said "Uses pgvector for efficient similarity search on embeddings" — true for one path in the class, but the docstring drew no distinction between paths.
2. The deduplication entry point was named `compare_proposed_rule_to_embeddings`, implying an embedding-based mechanism.
3. The `sigma_embedding_client` property in the same class instantiates `EmbeddingService(model_name="intfloat/e5-base-v2")`, which agents read as evidence that the dedup path uses that model.

None of these signals describes the dedup path. All three describe the unrelated article-matching path that lives in the same class.

## Guidance

`sigma_matching_service.py` contains two completely independent computation paths. Do not conflate them.

### Path 1 — Article → Sigma Rule Matching (uses embeddings)

Methods: `match_article_to_sigma_rules`, `match_chunks_to_sigma_rules`

- Embeds article text with `intfloat/e5-base-v2` (768-dimensional vectors).
- Runs a pgvector HNSW cosine similarity search against stored rule embeddings (`vector_cosine_ops`).
- This is the RAG path. It uses `sigma_embedding_client` and pgvector operators.

### Path 2 — Sigma → Sigma Deduplication (no embeddings, no pgvector)

Methods: `assess_rule_novelty` (canonical), `compare_proposed_rule_to_embeddings` (deprecated alias)

**Phase 1 — Candidate retrieval** (`sigma_novelty_service.py::retrieve_candidates`):

```python
if use_deterministic and canonical_class:
    # Primary: plain SQL filter on canonical_class, no LIMIT
    candidates = (
        self.db_session.query(SigmaRuleTable)
        .filter(SigmaRuleTable.canonical_class == canonical_class)
        .all()
    )
    if not candidates and logsource_key and logsource_key != "|":
        # Fallback: logsource_key + top_k limit
        candidates = (
            self.db_session.query(SigmaRuleTable)
            .filter(SigmaRuleTable.logsource_key == logsource_key)
            .limit(top_k)
            .all()
        )
```

No embeddings are computed. No pgvector operators are invoked.

**Phase 2 — Behavioral scoring** (`sigma_novelty_service.py:353`):

```python
weighted_sim = max(0.0, min(1.0, (atom_jaccard * B) - filter_penalty))
```

- `atom_jaccard` — Jaccard similarity over **atom-level tuples** (field + value + operator), NOT field-level overlap. `len(intersection) / len(union)` over normalized atom identity strings.
- `B` (containment factor) — a **discrete value** from `compute_containment()`: `1.0` (equivalent), `0.85` (subset), `0.75` (superset), `0.65` (partial overlap). Not a continuous ratio.
- `filter_penalty` — symmetric difference of **negative atoms** (exclusion / NOT conditions), capped at `0.5`.

### Fixes Applied (2026-05-20)

1. `sigma_matching_service.py` module docstring rewritten — explicitly separates both paths, calls out the AI-agent misconception by name.
2. Method renamed: `compare_proposed_rule_to_embeddings` → `assess_rule_novelty`. Old name preserved as a deprecated alias with a docstring that explicitly states it does not use embeddings.
3. "Known AI-Agent Misconceptions" section added to `AGENTS.md` with the exact wrong conclusion, why agents reach it, and where to verify the truth.

## Why This Matters

Misidentifying the dedup mechanism causes several categories of downstream error:

- **Incorrect debugging**: an agent debugging low similarity scores looks at embedding distance or index coverage, not atom set overlap or the containment factor `B`.
- **Wrong optimization advice**: pgvector HNSW tuning (`ef_search`, `m`) is irrelevant to dedup performance. The actual bottleneck is the number of candidates from the SQL filter and the cost of atom set operations.
- **Misleading documentation**: citing the 768-dimension model in dedup-path docs sends readers to the wrong subsystem.
- **Threshold misinterpretation**: pgvector cosine similarity scores have different distributional properties than the deterministic Jaccard × Containment − Filter formula. A score of `0.65` means different things in each context.

## When to Apply

Apply this guidance whenever:

- Reading or modifying `src/services/sigma_matching_service.py` or `src/services/sigma_novelty_service.py`.
- Explaining or documenting how the Sigma deduplication queue works.
- Debugging why a proposed rule is or is not flagged as a duplicate or near-duplicate.
- Interpreting similarity scores from `assess_rule_novelty`.
- Adding tests for the novelty assessment pipeline.
- Investigating zero candidates (look at `canonical_class` and `logsource_key` values — not embedding index coverage).

The `sigma_embedding_client` property and `intfloat/e5-base-v2` model are only relevant for `match_article_to_sigma_rules` / `match_chunks_to_sigma_rules`. They play no role in deduplication.

## Examples

### Wrong: conflating paths

> Phase 1 of Sigma deduplication retrieves candidate rules by computing cosine similarity between the proposed rule's embedding and stored rule embeddings using `intfloat/e5-base-v2` via pgvector's HNSW index.

### Correct: SQL-filter retrieval

> Phase 1 of Sigma deduplication retrieves candidates using a plain SQL equality filter on `canonical_class`. If unresolvable, it falls back to `logsource_key` + `LIMIT`. No embeddings are computed; no pgvector operators are used.

---

### Wrong: method name taken at face value

> `compare_proposed_rule_to_embeddings` retrieves the top-K most similar rules from the vector store, then scores them.

### Correct: deprecated alias, no embeddings

> `assess_rule_novelty` (canonical name; `compare_proposed_rule_to_embeddings` is a deprecated alias) performs SQL candidate retrieval followed by deterministic scoring: `weighted_sim = max(0.0, min(1.0, (atom_jaccard * B) - filter_penalty))`. Neither step uses embeddings.

---

### Wrong: debugging approach

> Dedup is returning low scores. I should check whether the pgvector HNSW index is populated and whether the rule embedding was generated correctly.

### Correct: debugging approach

> Dedup is returning low scores. Check: (1) whether `canonical_class` was resolved — if not, candidate retrieval falls back to the weaker `logsource_key` filter; (2) whether `positive_atoms` sets actually overlap — Jaccard of `0.0` means `weighted_sim = 0.0` regardless of semantic similarity; (3) whether a `filter_penalty` is being applied due to mismatched negative conditions.

## Related

- `docs/solutions/logic-errors/sigma-cross-field-soft-matching-zero-similarity-2026-04-12.md` — documents a zero-similarity bug in the same dedup pipeline; the "What Didn't Work" section records a rejected proposal to add an embedding fallback, which is the closest existing evidence of this same misconception being acted on.
- `docs/CHANGELOG.md` — two entries (approx. 2026-04-30, 2026-03-20) still reference the deprecated `compare_proposed_rule_to_embeddings` name without noting the rename; low-urgency staleness.
