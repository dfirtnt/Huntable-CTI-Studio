# Source-provided Sigma import contract

Publisher-authored Sigma rules use a dedicated import path. They are not LLM
outputs and never enter the generation, repair, or intra-batch deduplication
paths.

## Source and fidelity

- The only authoritative input is `articles.content`. `hunt_queries` and other
  extracted observables are non-authoritative display/evaluation data.
- A candidate must parse as one YAML mapping with a non-empty `title`, mapping
  `logsource`, mapping `detection`, string `detection.condition`, and a last
  top-level key that is part of the Sigma rule specification. The last-key
  check exists because publisher annotation lines printed after a rule
  (`Tier:`, `Robustness:`, `Confidence:`, ...) are valid YAML and would
  otherwise be absorbed as extra top-level keys on the rule itself.
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

## CI-parity gate

Because a source rule's YAML is never edited, the only way to keep a queue
approval from failing the destination repository's CI is to check the same
things CI checks before the rule leaves the queue. `src/services/sigma_ci_parity.py`
re-runs, over the raw `rule_yaml`, what the destination's `Validate` workflow
does: duplicate YAML keys, pySigma parse/condition errors, and the blocking
validator set read from the destination repo's own
`.sigma/validation-blocking.yml` (the bundled mirror is the fallback when that
file is absent). This gate is independent of, and additional to, the license
and delivery policy above -- a rule can pass one and fail the other. PR
submission enforces it the same way: the existing atomic preflight in
`POST /api/sigma-queue/submit-pr` runs it over the whole approved batch and
returns 409 with a per-rule reason before any git or GitHub side effect, and
`GET /api/sigma-queue/submit-pr/preflight` is a dry run of the same check.
Not covered: the destination's cross-rule duplicate-detection script and its
yamllint style rules, and any drift between this app's pySigma/pyparsing
versions and the destination's pinned `requirements-ci.txt` (reported as
`toolchain_drift`, not enforced).

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
