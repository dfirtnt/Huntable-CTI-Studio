# Sigma Semantic Similarity

Deterministic Sigma rule semantic similarity engine. Compares two Sigma rules and returns a structured `SimilarityResult` using canonical telemetry class matching, modifier-aware atom extraction, DNF normalization, Jaccard overlap, containment heuristics, and filter penalties.

**No embeddings. No cosine similarity. No metadata comparison. No fuzzy matching.**

## Install

```bash
pip install -e .
```

Requires Python 3.11+ and PyYAML only.

## Usage

### API

```python
from sigma_similarity import compare_rules, SimilarityResult

rule_a = {"logsource": {...}, "detection": {...}}  # or YAML string
rule_b = {"logsource": {...}, "detection": {...}}
result = compare_rules(rule_a, rule_b)
# result.similarity, result.jaccard, result.explanation.reason_flags, etc.
```

### CLI

```bash
python3 -m sigma_similarity rule1.yaml rule2.yaml
# or: sigma-similarity rule1.yaml rule2.yaml
```

Output is JSON with stable key order (`sort_keys=True`).

## Supported condition grammar

- Boolean: AND, OR, NOT, parentheses
- Selection references: `selection_name`, `selection*`
- Quantifiers: `1 of selection*`, `all of selection*`
- Lists → OR; `|all` modifier lists → AND

## Rejected (raise `UnsupportedSigmaFeatureError`)

count(), near, temporal joins, aggregation, multiple logsource blocks, correlation rules, sequence operators.

## Determinism

Same input → identical byte-for-byte output. Canonical sort of atoms and DNF branches; stable JSON serialization; no global state.

## Error types

- `UnsupportedSigmaFeatureError`: Unsupported condition/detection feature
- `UnknownTelemetryClassError`: Rule cannot be mapped to a canonical telemetry class (raise; no result)
- `DeterministicExpansionLimitError`: DNF expansion exceeds 64 branches (engine converts to result with `reason_flags=["dnf_expansion_limit"]`)

## Integration with Huntable CTI Studio

When this package is installed in the same environment as Huntable CTI Studio (e.g. `pip install -e sigma_semantic_similarity/` from the repo root), the app uses it for:

- **Novelty assessment** (`SigmaNoveltyService`): Pairwise rule comparison uses the deterministic engine when available; otherwise the in-app atom/jaccard + logic-shape similarity is used.
- **Eval semantic scoring** (`SigmaSemanticScorer`): When no LLM service is configured, the evaluator uses the deterministic engine for `similarity_score` (no missing/extraneous behavior details).

The dependency is optional: if the package is not installed, the app falls back to existing (LLM/embedding or in-app) logic.
