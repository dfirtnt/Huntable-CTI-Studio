# Sigma Rules

## Overview

Sigma rules are generated from threat intelligence articles by the workflow's
Sigma agent, validated with pySigma, and scored for behavioral novelty against
the indexed SigmaHQ repository before being queued for human review.

Three capabilities work together:

1. **Rule generation**: LLM produces Sigma YAML from extracted observables;
   pySigma validates the output.
2. **Rule matching**: Articles are matched to existing SigmaHQ rules using
   behavioral overlap scoring to determine coverage status.
3. **Similarity search**: Generated rules are compared against indexed SigmaHQ
   rules to detect duplication and classify novelty.

### System Flow

Two entry paths lead into Sigma rule processing:

- **Agentic Workflow** (primary): Triggered via `POST /api/workflow/articles/{id}/trigger` — OS Detection → Junk Filter → Rank → Extract → Generate Sigma → Similarity Search → Promote to Queue
- **Web/API path**: `POST /api/articles/{article_id}/generate-sigma` — Match Existing Rules → Classify Coverage → Generate New Rules (if needed) → Similarity Check → Store

### Signal Refinement Loop

![Sigma signal refinement loop](../diagrams/sigma-signal-refinement-loop.svg)

---

## Rule Generation

### Process

1. Content and extracted observables are passed to the Sigma generation LLM.
2. The LLM produces Sigma YAML with an additional `observables_used` field
   (not a valid Sigma field — stripped before pySigma validation).
3. pySigma validates the rule; if it fails, the error is injected into the next
   prompt and the LLM retries. Maximum 3 attempts.
4. The final rule and full attempt log are stored in
   `agentic_workflow_executions.sigma_results`.

Generation uses temperature 0.2 for deterministic output.

### Iterative Retry

- Up to 3 attempts per rule set
- Validation errors from pySigma are fed back into the next prompt
- All attempt logs (prompts, responses, validation results) are stored for
  post-mortem review

### Conversation Log Display

The article UI renders the LLM ↔ pySigma conversation:

- One card per attempt with pass/fail indicator
- Collapsible prompt and response blocks
- pySigma error detail when a rule fails validation

### Prerequisites

- AI model configured (OpenAI API key, or LMStudio local server)
- pySigma installed (bundled in requirements)
- For similarity search: Sigma rules indexed (`sigma index-metadata` then
  `sigma index-embeddings`)
- Threat hunting score < 65 shows a warning but does not block generation

---

## Rule Matching Pipeline

A three-layer pipeline matches CTI articles to existing Sigma rules from
SigmaHQ, classifies coverage, and gates new rule generation.

### Architecture Components

#### Database Schema

**`sigma_rules`** — stores indexed SigmaHQ rules:
- 768-dimensional pgvector embeddings (`intfloat/e5-base-v2`)
- JSONB fields for logsource and detection logic
- Full metadata: tags, level, status, author, references
- Source tracking: `file_path`, `repo_commit_sha`
- Canonical fields: `logsource_key`, `canonical_class` (precomputed for novelty scoring)

**`article_sigma_matches`** — stores article-to-rule matches:
- Similarity scores, match levels (article/chunk)
- Coverage classification: `covered`, `extend`, `new`
- Matched behaviors: discriminators, LOLBAS, intelligence indicators

#### Sigma Sync Service

**File**: `src/services/sigma_sync_service.py`

Clones/pulls the SigmaHQ repository, parses YAML rule files, generates
embeddings, and batch-indexes rules. Incremental updates only index new rules.

Key methods: `clone_or_pull_repository()`, `find_rule_files()`,
`parse_rule_file()`, `index_metadata()`, `index_embeddings()`, `index_rules()`

#### Sigma Matching Service

**File**: `src/services/sigma_matching_service.py`

- Article-level and chunk-level semantic search using pgvector cosine similarity
  for candidate retrieval
- Behavioral novelty scoring for final similarity assessment (see
  [Novelty Service Architecture](#novelty-service-architecture))
- Configurable candidate retrieval limits and matching threshold

#### Coverage Classification Service

**File**: `src/services/sigma_coverage_service.py`

Extracts behaviors from `chunk_analysis_results`, compares them to rule
detection patterns, and classifies each match:

| Status | Condition |
|---|---|
| `covered` | Similarity ≥ 0.85 and behavior overlap ≥ 0.7 |
| `extend` | Similarity ≥ 0.7 and overlap ≥ 0.3 |
| `new` | Low overlap — new detection opportunity |

### Enhanced Generation Workflow

**File**: `src/web/routes/ai.py`

1. Match article to existing rules (threshold 0.7)
2. Classify each match (`covered` / `extend` / `new`)
3. Store matches to database
4. If ≥ 2 rules are `covered`: skip generation, return matches
5. Otherwise: proceed with LLM generation

### Embedding Strategy

All Sigma embedding operations use `intfloat/e5-base-v2` via local
sentence-transformers (768 dimensions). Article embeddings already stored in
`articles.embedding` are reused; chunk embeddings are generated on-demand from
`chunk_analysis_results`. Rule embeddings combine title + description +
logsource + tags.

---

## Similarity Search

Compares generated rules against indexed SigmaHQ rules to detect duplication
and score novelty.

### How It Works

```
Generated Rule
  1. Extract detection atoms (or generate embedding as fallback)
  2. Filter sigma_rules by logsource_key (hard gate)
  3. Further filter by canonical_class when available
  4. Compute behavioral novelty score for each candidate
  5. Return top matches above threshold, sorted by similarity descending
```

### Behavioral Novelty Scoring

**Deterministic path** (when `sigma_semantic_similarity` package is installed):

```
novelty_score = 1 - similarity_score
similarity_score = (atom_jaccard * containment) - filter_penalty
```

Where:
- `atom_jaccard` = |atoms(A) ∩ atoms(B)| / |atoms(A) ∪ atoms(B)|
- `containment` = |atoms(A) ∩ atoms(B)| / |atoms(A)|
- `filter_penalty` = reduction when one rule's filters would exclude the other's detection

**Cross-field soft matching**: When strict atom intersection is empty, value-based
soft matching applies across process-executable fields (`Image`, `CommandLine`,
`ParentImage`, `ParentCommandLine`, `OriginalFileName`, and their canonical
`process.*` variants). Same executable value in different fields awards
50%-dampened partial Jaccard credit, preventing 0% similarity between rules
detecting the same binary via different Sigma fields.

**Legacy path** (when package is not installed): Atom Jaccard 70% + Logic Shape
Similarity 30%.

### Similarity Thresholds

| Range | Interpretation |
|---|---|
| > 0.9 | Consider using existing rule instead |
| 0.7 – 0.9 | Review for potential extension |
| < 0.7 | Novel detection opportunity |

### Candidate Retrieval

The `/api/sigma-queue/{id}/similar-rules` response includes
`total_candidates_evaluated`, `canonical_class`, and `logsource_key` so the UI
can explain why the candidate count may be lower than the total indexed rules.

### Customer Repo Rules

Similarity search uses the single `sigma_rules` table. To include approved rules
from your customer repo alongside SigmaHQ rules:

```bash
# Index approved rules from customer repo (metadata + embeddings)
./run_cli.sh sigma index-customer-repo

# Metadata only (embeddings later)
./run_cli.sh sigma index-customer-repo --no-embeddings
```

Customer rules use `rule_id` prefix `cust-` and `file_path` prefix `customer/`.

---

## Observables-Used Tracing

Every LLM-generated Sigma rule carries an `observables_used` field linking it
back to the extracted observables it was built from.

### What It Is

During generation the LLM includes a `observables_used` key in its YAML
alongside the valid Sigma fields:

```yaml
observables_used: [0, 3]   # indices into the observables array for this article
```

`observables_used` is not a valid Sigma field — the generation service strips it
before pySigma validation and stores it in rule metadata
(`SigmaGenerationResult.observables_used`). An empty list means the rule was
synthesized from article context without directly referencing an extracted
observable.

### Inference Fallback

If the LLM omits `observables_used`, `_infer_observables_used()` in
`src/services/sigma_generation_service.py` recovers it by:

1. Tokenizing each observable's `value` field into tokens ≥ 4 characters
2. Checking whether any token appears as a substring in the rule's `detection`
   block
3. Returning indices of matching observables, or `None` if none match

When recovered via inference, `observables_used_inferred: true` is set in rule
metadata.

### Storage

After generation the field is stored in `rule_metadata["observables_used"]`
within `WorkflowExecutionTable.sigma_results` and propagated to the `sigma_queue`
entry for display in the Sigma Queue UI.

---

## Novelty Service Architecture

| Layer | File | Role |
|---|---|---|
| Entry point | `sigma_matching_service.py` | Calls `SigmaNoveltyService.assess_novelty()` |
| Orchestrator | `sigma_novelty_service.py` | Retrieves candidates, computes Jaccard/containment/filter scores |
| Precompute | `sigma_semantic_precompute.py` | Materializes canonical atom sets and logsource keys at index time |
| Normalizer | `sigma_behavioral_normalizer.py` | Resolves field aliases (PascalCase / snake_case / lowercase) to canonical identities |
| Novelty detector | `sigma_novelty_detector.py` | Near-duplicate heuristics before full scoring |
| Semantic scorer | `sigma_semantic_scorer.py` | Embedding-based fallback when deterministic atoms are unavailable |
| Huntability scorer | `sigma_huntability_scorer.py` | Post-generation quality assessment (coverage, specificity) |
| External engine | `sigma_semantic_similarity` pkg | Optional deterministic engine; used when installed |

---

## CLI Commands

**File**: `src/cli/sigma_commands.py`

```bash
# Sync SigmaHQ repository
./run_cli.sh sigma sync

# Index rules: metadata first, then embeddings
./run_cli.sh sigma index-metadata
./run_cli.sh sigma index-embeddings

# Or both at once (partial success if embeddings fail)
./run_cli.sh sigma index [--force]

# Match a single article
./run_cli.sh sigma match <article_id> [--save] [--threshold 0.7]

# Show index statistics
./run_cli.sh sigma stats

# Recompute semantic fields (needed after atom identity normalization changes)
./run_cli.sh sigma recompute-semantics

# Backfill canonical fields for rules already in DB
./run_cli.sh sigma backfill-metadata

# Index approved rules from customer repo
./run_cli.sh sigma index-customer-repo [--no-embeddings] [--force]
```

---

## API Reference

### Generate Sigma Rules

**Endpoint**: `POST /api/articles/{article_id}/generate-sigma`

**Request:**
```json
{
  "force_regenerate": false,
  "include_content": true,
  "ai_model": "chatgpt",
  "api_key": "your_api_key_here",
  "author_name": "Huntable CTI Studio User",
  "temperature": 0.2,
  "skip_matching": false,
  "optimization_options": {
    "useFiltering": true,
    "minConfidence": 0.7
  }
}
```

**Response (article covered by existing rules):**
```json
{
  "success": true,
  "matched_rules": [...],
  "coverage_summary": {"covered": 2, "extend": 1, "new": 0, "total": 3},
  "generated_rules": [],
  "skipped_generation": true,
  "recommendation": "Article behaviors are covered by 2 existing Sigma rule(s). No new rules needed."
}
```

**Response (new rules generated):**
```json
{
  "success": true,
  "rules": [...],
  "similar_rules": [...],
  "validation_results": [...],
  "validation_passed": true,
  "attempts_made": 1,
  "matched_rules": [],
  "coverage_summary": {...}
}
```

### Get Existing Matches

**Endpoint**: `GET /api/articles/{article_id}/sigma-matches`

**Response:**
```json
{
  "success": true,
  "matches": [
    {
      "rule_id": "a1b2c3d4-...",
      "title": "PowerShell Suspicious Script Execution",
      "similarity_score": 0.875,
      "coverage_status": "covered",
      "matched_discriminators": ["powershell.exe", "EncodedCommand"],
      "matched_lolbas": ["powershell.exe", "cmd.exe"],
      "created_at": "2025-01-16T10:30:00"
    }
  ],
  "coverage_summary": {"covered": 2, "extend": 1, "new": 0, "total": 3}
}
```

---

## Configuration

### Environment Variables

```bash
# Sigma PR submission (your rules repo)
SIGMA_REPO_PATH=sigma-repo
GITHUB_REPO=owner/repo
GITHUB_TOKEN=ghp_xxx       # Add in Settings -> GitHub (repo scope)

# Similarity matching threshold
SIGMA_MATCH_THRESHOLD=0.7
```

### GitHub PR Setup

1. **During `./setup.sh`**: Create a repo at github.com/new, enter `owner/repo`
   when prompted. The script clones to `../Huntable-SIGMA-Rules` and creates
   the `rules/` structure.
2. **After setup**: Add your GitHub Personal Access Token in **Settings →
   GitHub** (repo scope).
3. **Settings → GitHub**: Configure Sigma Repository Path, GitHub Repository,
   and Git user name/email for commits.

### AI Model Configuration

| Model | Notes |
|---|---|
| OpenAI (gpt-4o-mini default) | API key required in request body; temperature 0.2 |
| LMStudio (local) | No API key; configure model in LMStudio settings |

### Sigma Rule Embeddings

Indexing uses `intfloat/e5-base-v2` via local sentence-transformers (no LMStudio
required). Run `sigma index-metadata` first, then `sigma index-embeddings` to
enable similarity search. The `LMSTUDIO_EMBEDDING_MODEL` env var or
`SigmaEmbeddingModel` workflow config key overrides the model when using LM
Studio as the embedding backend.

---

## Troubleshooting

### No Similarity Results

1. Ensure Sigma rules are synced and indexed:
   ```bash
   ./run_cli.sh sigma sync
   ./run_cli.sh sigma index
   ```
2. If rules were indexed before `logsource_key` existed, backfill canonical fields:
   ```bash
   python3 scripts/migrate_sigma_to_canonical.py
   ```
3. Check index status:
   ```bash
   ./run_cli.sh sigma stats
   ```
4. If similarity is still zero, atom identity normalization may be stale.
   LLM-generated rules may use lowercase/snake_case field names that don't
   match PascalCase atoms in SigmaHQ rules. Recompute:
   ```bash
   ./run_cli.sh sigma recompute-semantics
   ```
   See [Sigma Similarity Case-Sensitive Atom Matching](../solutions/logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md).

### Embedding Generation Failures

- `sentence-transformers not installed`: ensure it is in requirements
- Out of memory: `intfloat/e5-base-v2` loads on first use; ensure sufficient RAM
- Run `sigma index-metadata` before `sigma index-embeddings`

### pySigma Validation Failures

- Check rule format compliance; review the conversation log for per-attempt error detail
- Common issues: missing required fields (title, logsource, detection), invalid YAML,
  incorrect field types, missing condition

### Slow Performance

1. Rebuild the vector index:
   ```sql
   REINDEX INDEX idx_sigma_rules_embedding;
   ```
2. Adjust IVFFlat lists parameter
3. Increase database resources

### Debug Commands

```bash
LOG_LEVEL=DEBUG
docker-compose logs -f web | grep "SIGMA"
docker-compose exec web python3 -c "from src.services.embedding_service import EmbeddingService; print('OK')"
```

---

## References

- [SigmaHQ Repository](https://github.com/SigmaHQ/sigma)
- [Sigma Specification](https://github.com/SigmaHQ/sigma-specification)
- [pgvector](https://github.com/pgvector/pgvector)
- [Sentence Transformers](https://www.sbert.net/)
- [pySigma Documentation](https://sigmahq-pysigma.readthedocs.io/)
- [CLI Reference](../reference/cli.md#sigma)
- [Sigma Similarity Case-Sensitive Atom Matching](../solutions/logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md)
- [Sigma Cross-Field Soft Matching](../solutions/logic-errors/sigma-cross-field-soft-matching-zero-similarity-2026-04-12.md)

_Last updated: 2026-05-01_
