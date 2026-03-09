# Decouple Sigma Indexing — Session Summary

**Branch:** `feature/decouple-sigma-indexing`  
**Epic:** Decouple Sigma Indexing from LMStudio  
**Commits:** 18 (including 5 post-epic bug fixes)

---

## Problem Statement

`SigmaSyncService.index_rules()` raised `RuntimeError("LM Studio embedding client unavailable")` whenever LMStudio was offline — blocking **all** Sigma indexing, including metadata that has zero embedding dependency. The CLI, Celery worker, shell scripts, and frontend gave misleading errors or silently failed with no actionable guidance.

---

## What Was Built

### Task 1 — `index_metadata()` (always works)

- Split out `SigmaSyncService.index_metadata()`: parses YAML, stores all rule metadata + canonical novelty fields (`canonical_json`, `exact_hash`, `canonical_text`, `logsource_key`), leaves embedding columns NULL
- Uses `_UPDATABLE_COLUMNS` allowlist to prevent accidental overwrites
- `SigmaNoveltyService` instantiated once before loop for efficiency
- 5 unit tests

### Task 2 — `index_embeddings()` (optional, local model)

- New `SigmaSyncService.index_embeddings()` using local sentence-transformers (`intfloat/e5-base-v2`) instead of LMStudio
- Lazy import of `EmbeddingService` so `index_metadata()` paths never break when sentence-transformers is unavailable
- 4 unit tests

### Task 3 — Orchestrator

- New `index_rules()` calls `index_metadata()` then attempts `index_embeddings()`, returning a dict with partial-success semantics: `{metadata_indexed, embeddings_indexed, skipped, errors}`
- CLI updated: `sigma index` (backward compat), `sigma index-metadata`, `sigma index-embeddings`, `sigma backfill-metadata` subcommands added
- 3 unit tests

### Task 4 — Celery worker

- `sync_sigma_rules` task updated to handle dict return from `index_rules()`
- Logs partial success warning when metadata works but embeddings fail
- Always returns `status: "success"` when metadata indexing succeeds
- 1 unit test

### Task 5 — CapabilityService

- Single source of truth for runtime feature availability
- Probes DB, filesystem, env vars; returns 6 capability flags: `article_retrieval`, `sigma_metadata_indexing`, `sigma_embedding_indexing`, `sigma_retrieval`, `sigma_novelty_comparison`, `llm_generation`
- Each flag has `enabled` (bool), `reason` (str), optional `action` (str)
- 6 unit tests

### Task 6 — `/api/capabilities` endpoint + CLI command

- `GET /api/capabilities` — JSON capability map consumed by frontend
- `capabilities check` CLI command with Rich table output and `--json-output` flag for shell script consumption
- 1 unit test

### Task 7 — RAG API capabilities block

- `/api/chat/rag` response now includes capabilities subset: `article_retrieval`, `sigma_retrieval`, `llm_generation`
- Frontend receives real-time capability state with each chat response
- 1 unit test

### Task 8 — RAG Chat UI warning banners

- `RAGChat.jsx` fetches `/api/capabilities` on mount and merges updates from RAG responses
- Yellow warning banners rendered above message list when `sigma_retrieval` or `llm_generation` is disabled
- Actionable messages shown (e.g. "Run sigma index-embeddings to enable Sigma rule retrieval in RAG")

### Task 9 — Shell scripts

- `start.sh`: Sigma section split into `index-metadata` (always) + `index-embeddings` (optional, respects `SKIP_SIGMA_INDEX`); added capability-driven warnings block after sync using `capabilities check --json-output` and `python3` JSON parsing
- `setup.sh`: `handle_sigma_sync_and_index()` updated with same split pattern

### Task 10 — Integration test

- `tests/integration/test_sigma_decoupled_indexing.py`: full degraded-mode flow — index metadata → check capabilities → verify `sigma_retrieval` disabled, `sigma_metadata_indexing` enabled

### Task 11 — Final verification

- 22 tests passing across all new files, 0 regressions

---

## Post-Epic Bug Fixes (during live testing)

| Commit  | Issue | Root Cause | Fix |
|---------|-------|------------|-----|
| 2e4b9fa | All 3112 embeddings failed with `StatementError` | `begin_nested()` savepoints incompatible with pgvector type handling at commit time | Removed savepoints; old code never used them |
| 216ca0a | `DetachedInstanceError` at rule 101 | `db_session.commit()` calls `expire_all()`, expiring the pre-loaded rules list | Replaced mid-loop `commit()` with `flush()` (writes without expiring) |
| 7735a1d | No visibility into embedding progress (~21 min, no feedback) | `index-embeddings` used a spinner with no count | Added Rich progress bar with bar, M/N count, elapsed, ETA via `progress_callback` |
| e7d384e | HuggingFace network calls on every run | `SentenceTransformer()` always hits HuggingFace Hub to verify cache | Try `local_files_only=True` first, fall back to download on first use |
| a27f120 | HuggingFace calls still happening + batch optimization slower | Cache inside ephemeral container layer; CPU batch scaling ≠ GPU | Persistent `hf_cache` Docker volume; reverted batch optimization |

---

## Architecture After This Work

```
sigma sync           → clone/pull SigmaHQ repo (no change)
sigma index-metadata → parse YAML, store metadata + canonical fields (no embedding dep)
sigma index-embeddings → generate embeddings via local e5-base-v2 (optional)
sigma index          → orchestrates both (backward compat)
```

```
CapabilityService   → single source of truth, consumed by:
  ├── GET /api/capabilities  → frontend polling
  ├── /api/chat/rag         → per-response capability block
  ├── CLI: capabilities check → human table + --json-output for scripts
  └── start.sh / setup.sh   → post-boot capability warnings
```

```
RAGChat.jsx         → shows yellow banners when sigma_retrieval or llm_generation disabled
```

---

## Additional Opportunities

### Performance

- **Apple Silicon MPS acceleration:** `EmbeddingService` detects cuda or falls back to cpu. Apple Silicon has MPS (`torch.backends.mps.is_available()`). Adding MPS support would likely cut embedding time by 3–5×
- **Embedding cache warm-up in start.sh:** Run `sigma index-embeddings` async in background so the web service starts faster
- **Batch size tuning:** Current `batch_size=32` is the sentence-transformers default. Smaller batches (8–16) may perform better on CPU for the text lengths in Sigma rules

### Reliability

- **Checkpoint/resume for index-embeddings:** If killed mid-run, restarts from scratch for unembedded rules (this is already handled by the `embedding IS NULL` filter — it's actually safe, just not obvious to operators)
- **Celery task for on-demand embedding:** Currently only `sync_sigma_rules` Celery task exists. A dedicated `embed_sigma_rules` Celery task would allow triggering embedding from the UI or scheduling it separately from sync
- **`TRANSFORMERS_OFFLINE=1` env var:** More reliable than `local_files_only=True` fallback once the model is in the `hf_cache` volume. Could be set after first successful download

### Observability

- **sigma index-embeddings ETA accuracy:** Current ETA is unstable for the first ~50 rules because per-rule time varies significantly at model warm-up. Could smooth by starting the timer after rule 10
- **Capability status in the web UI Settings page:** CapabilityService exists but the Settings page doesn't surface capability warnings. Adding a "System Status" panel there would help operators diagnose issues without using the CLI

### Quality

- **sigma backfill-metadata for rules indexed before this refactor:** Rules that were embedded via the old LMStudio path have `canonical_json = NULL`. The `backfill-metadata` CLI command exists but isn't called from `start.sh`. Could be added as an optional step
- **sigma index-embeddings --force in Celery:** The Celery `sync_sigma_rules` task calls `index_rules(force_reindex=False)`. If embeddings drift (model changes), there's no scheduled way to force a full re-embed short of running the CLI manually

---

## Post-Summary Fix: pgvector B-tree Index (ProgramLimitExceeded)

**Issue:** `sigma index-embeddings` failed at first flush (100 rules) with:
```
psycopg2.errors.ProgramLimitExceeded: index row size 3088 exceeds btree version 4 maximum 2704 for index "ix_sigma_rules_embedding"
```

**Root cause:** `index=True` on `Vector(768)` columns creates a B-tree index; 768-dim vectors (~3088 bytes) exceed PostgreSQL's 2704-byte B-tree limit.

**Fix:** 
- `scripts/migrate_pgvector_indexes.py` — drops B-tree indexes on `sigma_rules.embedding`, `articles.embedding`, `article_annotations.embedding`; creates HNSW indexes with `vector_cosine_ops`
- `src/database/models.py` — removed `index=True` from all Vector(768) columns
- `docker-compose.yml` — added `./scripts` volume to cli service
- `start.sh` — runs migration before Sigma indexing section

**Verification:** Migration ran successfully; `sigma index-embeddings` passed the 100-rule flush without ProgramLimitExceeded.
