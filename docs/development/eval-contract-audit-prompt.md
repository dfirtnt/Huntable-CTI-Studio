# Eval Contract Audit Prompt — superseded by the `eval-fixture-audit` skill

This page previously held a 200-line paste-in prompt for auditing one
extractor's eval fixtures (Eval1 expected counts + Eval2 ground-truth items).
That prompt encoded an older authority model (the live DB config as the
contract source) and has been replaced.

**Use the project skill instead:** `.claude/skills/eval-fixture-audit/SKILL.md` (in the repo root, alongside this `docs/` tree).

In any Claude session opened at the repo root, just ask:

> audit the evals for RegistryExtract

The skill runs the full workflow — blind extraction against the authoritative
spec docs (`docs/contracts/<agent>-extract.md` on the
`extractor-standard.md` baseline), five-sink comparison (xlsx, DB,
`eval_articles.yaml`, `articles.json`, `ground_truth.json`), operator
adjudication with STOP gates, approved-only writes, and the
fixture-correction vs spec-change distinction that keeps regression scores
comparable across eval eras.

Key principles the skill enforces (and this doc's one surviving rule):

- **Extract first, compare second.** Recorded counts are anchors; reading them
  before blind extraction biases the audit. One agent per session.
- The spec docs in `docs/contracts/` are authoritative — not the seed prompt,
  not the live DB config (which churns with experimentation).
- Ground truth exists for regression tracking; spec changes are deliberate,
  changelogged events that create score-comparability boundaries.
