# Generate Sigma Rules

Sigma generation is baked into the agentic workflow. It uses extracted observables when available, validates with pySigma, and compares output to SigmaHQ rules (behavioral novelty; embeddings used for candidate retrieval). See [Sigma Detection Rules](../features/sigma-rules.md).

## Prerequisites
- Stack running (`./start.sh`)
- Article ingested and processed by the workflow (extraction complete)
- Optional similarity search: Run `sigma index-metadata` then `sigma index-embeddings` (local sentence-transformers; no LM Studio required)

## 1) Make sure Sigma rules are indexed
Clone/pull the SigmaHQ repository and index rules into PostgreSQL:
```bash
./run_cli.sh sigma sync
./run_cli.sh sigma index            # add --force to re-index
```

To include **approved rules from your customer repo** (the repo at `SIGMA_REPO_PATH` used for PR submission) in similarity search, index them so the workflow and MCP compare against both SigmaHQ and your repo:
```bash
./run_cli.sh sigma index-customer-repo   # metadata + embeddings; use --no-embeddings for metadata only
```
Re-run after adding or changing rules in the customer repo. See [Sigma Detection Rules: Customer repo rules in similarity search](../features/sigma-rules.md#customer-repo-rules).

## 2) Trigger workflow for the article
Sigma runs automatically after extraction:
```bash
EXECUTION_ID=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger" | jq -r '.execution_id')
```
The Sigma agent uses junk-filtered full article content as the main generation content when `sigma_fallback_enabled` is true. Otherwise, it uses `extraction_result.content` when `discrete_huntables_count > 0`. Extracted observables remain available to the Sigma prompt when present; the toggle changes the main `{content}` block, not whether observables are collected.

## 3) Retrieve generated rules
```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, sigma_rules, similarity:.similarity_results}'
```
Each entry includes validation details, attempt logs, and similarity matches against the indexed repository.

UI paths:
- Workflow page Sigma queue: generated rules land there for review, enrichment and PR submission.
- Workflow page execution detail: shows Sigma attempts and coverage classifications.

## 4) Match existing rules from CLI (optional)
Run similarity matching outside the workflow or re-classify coverage:
```bash
./run_cli.sh sigma match ${ARTICLE_ID} --threshold 0.7
```
This compares the article (and its chunks) to indexed Sigma rules and prints a ranked table with coverage classification; it does not write results to the database.

## 5) Submit approved rules as PR (optional)

To submit approved rules from the Sigma Queue to your GitHub repo:

**One-time setup (run during `./setup.sh` or manually):**

1. Create a repo at [github.com/new](https://github.com/new) (e.g. `Huntable-SIGMA-Rules`)
2. Clone to `../Huntable-SIGMA-Rules` (or let setup.sh do it when prompted)
3. Add your **GitHub Personal Access Token** in **Settings → GitHub** (repo scope)
   - Create token at [github.com/settings/tokens](https://github.com/settings/tokens)

**Manual setup if you skipped setup.sh:**

```bash
git clone https://github.com/YOUR_USER/Huntable-SIGMA-Rules.git ../Huntable-SIGMA-Rules
mkdir -p ../Huntable-SIGMA-Rules/.huntable
cp config/sigma_rule_layout.yml ../Huntable-SIGMA-Rules/.huntable/rule-layout.yml
# Commit and push. Do not pre-create rules/<platform>/ folders; each PR creates what it needs.
```

Approved rules are written to `rules/<platform>/<logsource dir>/<slug>.yml`, or
`rules-emerging-threats/<family>/<slug>.yml` for rules tagged `detection.emerging-threats`
(`_unsorted/` when no family resolves). Before the PR is opened, each rule's author, date and
tags are normalized and saved to the queue row; a rule missing `references`,
`falsepositives` or `tags` goes back to **Pending** with a review note instead of into the
PR. Run **`GET /api/sigma-queue/submit-pr/preflight`** to see the result without side
effects. Details: [Publish layout and metadata](../features/sigma-rules.md#publish-layout-and-metadata).

**Migrating an existing flat repository** (every rule in `rules/windows/`):

```bash
.venv/bin/python scripts/migrate_sigma_repo_layout.py --repo ../Huntable-SIGMA-Rules --report migration.md
```

The dry run prints every old -> new path, the emerging-threat rules left in `_unsorted/`,
each metadata change, and the rules that still need a hand-written fix. `--apply --branch
<name>` creates the branch, commits the `git mv` renames, then commits the metadata fixes
separately. It never pushes and never changes `id`, `title`, `logsource` or `detection`.
After the migration merges, refresh the indexed paths:

```bash
./run_cli.sh sigma index-customer-repo --force
```

Configure in **Settings → GitHub**:

- SIGMA Repository Path: `sigma-repo` (default)
- GitHub Repository: `owner/repo`
- GitHub Personal Access Token: required

## Troubleshooting
- If validation fails, the Sigma agent retries up to three times with pySigma error feedback.
- No rules are generated when extraction produces zero huntables and the filtered content toggle is disabled.
- Similarity search requires embeddings; run `sigma index-embeddings` (uses local sentence-transformers). Use `capabilities check` to verify status.

_Last updated: 2026-10-17_
_Last reviewed: 2026-09-01_
