# Source-provided Sigma import contract

Publisher-authored Sigma rules use a dedicated import path. They are not LLM
outputs and never enter the generation, repair, or intra-batch deduplication
paths.

## Source and fidelity

- The only authoritative input is `articles.content`. `hunt_queries` and other
  extracted observables are non-authoritative display/evaluation data.
- A candidate must parse as one YAML mapping with a non-empty `title`, mapping
  `logsource`, mapping `detection`, and string `detection.condition`.
- `rule_yaml` is an exact substring of `articles.content`. Import never repairs,
  reformats, re-indents, enriches, or normalizes it.
- Source records are immutable. Reviewers create a generated copy before editing
  or enrichment; the source record remains available for provenance.

## Provenance

Every `rule_origin=source_provided` row records:

- article ID and canonical source URL;
- publisher rule ID and exact-content SHA-256;
- start/end character offsets into `articles.content`;
- declared license, exact license evidence and its offsets;
- publisher attribution;
- optional reviewer, basis, and timestamp for source-specific permission.

The source URL + publisher rule ID and the exact-content SHA-256 are protected
by partial unique indexes. Existing/manual/generated queue rows are explicitly
backfilled to `rule_origin=generated`.

## License and delivery policy

The destination rules repository owns
`.huntable/source-rule-license-policy.yml`. Missing or unreadable policy fails
closed. Its initial allowlist entry is `CC-BY-4.0`, with attribution, license
notice, change marking, and no-endorsement requirements.

Rules with no explicit license or a CC BY-NC license enter
`local_review_only`. They can be reviewed, annotated, copied, similarity-checked,
or rejected, but the server refuses approval. Source-specific permission can be
recorded by a reviewer and moves the item back to `pending` for normal review.

Single approval, bulk approval, and PR submission all enforce the same policy.
The PR endpoint re-evaluates every approved rule before invoking the repository
service; one ineligible item rejects the entire batch without opening a PR.

## Similarity and logsource handling

Similarity is reviewer context only. It never suppresses, changes, re-homes, or
deduplicates a source rule. An unresolved canonical logsource is stored as a
warning and does not reject otherwise valid Sigma.

## Deployment

Both scripts are read-only unless `--apply` is supplied:

```bash
python scripts/migrate_source_sigma_queue.py
python scripts/import_source_sigma_rules.py
```

After operator approval, apply the schema migration before the backfill:

```bash
python scripts/migrate_source_sigma_queue.py --apply
python scripts/import_source_sigma_rules.py --apply
```

Verify the live schema, confirm all pre-existing rows are `generated`, then
compare the backfill counts with the dry-run receipt.
