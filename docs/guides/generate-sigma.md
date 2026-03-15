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

## 2) Trigger workflow for the article
Sigma runs automatically after extraction:
```bash
EXECUTION_ID=$(curl -s -X POST "http://localhost:8001/api/workflow/articles/${ARTICLE_ID}/trigger" | jq -r '.execution_id')
```
The Sigma agent uses filtered article content (minus junk) when `sigma_fallback_enabled` is true. Otherwise, it uses `extraction_result.content` when `discrete_huntables_count > 0`.

## 3) Retrieve generated rules
```bash
curl -s "http://localhost:8001/api/workflow/executions/${EXECUTION_ID}" \
  | jq '{status, sigma_rules, similarity:.similarity_results}'
```
Each entry includes validation details, attempt logs, and similarity matches against the indexed repository.

UI paths:
- Article page Sigma section: `http://localhost:8001/articles/${ARTICLE_ID}#sigma`
- Workflow page execution detail: shows Sigma attempts and coverage classifications.

## 4) Match existing rules from CLI (optional)
Run similarity matching outside the workflow or re-classify coverage:
```bash
./run_cli.sh sigma match ${ARTICLE_ID} --threshold 0.7 --save
```
This compares the article (and its chunks) to indexed Sigma rules and stores results in the database.

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
cd ../Huntable-SIGMA-Rules
mkdir -p rules/{windows,linux,macos,network,cloud}
# Add .gitkeep or initial rules, then commit and push
```

Configure in **Settings → GitHub**:

- SIGMA Repository Path: `sigma-repo` (default)
- GitHub Repository: `owner/repo`
- GitHub Personal Access Token: required

## Troubleshooting
- If validation fails, the Sigma agent retries up to three times with pySigma error feedback.
- No rules are generated when extraction produces zero huntables and the filtered content toggle is disabled.
- Similarity search requires embeddings; run `sigma index-embeddings` (uses local sentence-transformers). Use `capabilities check` to verify status.
