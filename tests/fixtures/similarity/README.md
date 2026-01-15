# Similarity Search Golden Files

This directory contains golden files for deterministic similarity search testing.

## Files

- `input_queries.json` - Input queries for similarity search tests
- `expected_ordering.json` - Expected rule ordering with version metadata

## Versioning

The `expected_ordering.json` file includes:
- `version` - Schema version (increment when format changes)
- `created_date` - When this golden file was created
- `model_version` - Embedding model version used
- `rules` - Array of rule IDs in expected order
- `score_ranges` - Min/max score ranges for each rule (not exact floats)

## Invariants

What must remain stable:
- Relative ordering: Rule A > Rule B > Rule C relationships
- Score ranges: Min/max bounds (not exact values)
- Rule IDs: Must match corpus

## Update Process

1. Run similarity search with fixed corpus
2. Capture rule ordering and score ranges
3. Update `expected_ordering.json` with new version
4. Document what changed in version notes
5. Commit both input and expected files together

## Testing

Tests assert:
- Stable ranking for fixed corpus
- Relative comparisons ("A > B > C")
- Score ranges (not exact floats)

This prevents flaky tests from minor embedding model variations while ensuring deterministic ordering.
