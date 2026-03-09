# Design: Decouple Sigma Indexing From LMStudio and Surface Accurate RAG Capability Warnings

**Date:** 2026-03-07
**Status:** Approved

## Problem

Sigma rule indexing is coupled to LMStudio embeddings. Users who choose "no LMStudio" lose metadata indexing and novelty comparison unnecessarily. UI warnings are imprecise about what RAG functionality is affected.

## Key Decisions

1. **Embedding provider:** Switch Sigma embedding generation from LMStudio to local sentence-transformers (`intfloat/e5-base-v2`). The RAG query side already uses this model locally, so this eliminates an external dependency while maintaining vector compatibility.
2. **Capability model location:** Python `CapabilityService` + CLI command. Single source of truth consumed by shell scripts (via CLI), Web UI (via API), and RAG responses.
3. **RAG API contract:** Top-level `capabilities` block in `/api/chat/rag` response, distinguishing "no matches" from "capability unavailable."
4. **Novelty fallback:** Exact-hash + canonical novelty assessment only (no deterministic similarity fallback). Embedding similarity is a bonus when available.

## Architecture

### Current State

```
sigma index
  --> parse YAML
  --> LMStudioEmbeddingClient.generate_embedding()  <-- FAILS without LMStudio
  --> compute canonical fields
  --> store everything (metadata + embeddings + canonical)
```

### Target State

```
sigma index (orchestrator)
  |
  +--> sigma index-metadata (always available)
  |      --> parse YAML
  |      --> compute canonical fields
  |      --> store metadata + canonical (embedding columns remain NULL)
  |
  +--> sigma index-embeddings (optional, uses local sentence-transformers)
         --> load EmbeddingService("intfloat/e5-base-v2")
         --> iterate rules where embedding IS NULL
         --> generate + store embeddings
```

## Story 1: Split Sigma Indexing

### `SigmaSyncService` refactor (`src/services/sigma_sync_service.py`)

**`index_metadata(db_session, force_reindex) -> dict`**
- Parses YAML files, stores rule metadata columns
- Computes canonical novelty fields: `canonical_json`, `exact_hash`, `canonical_text`, `logsource_key`
- No embedding dependency
- Returns `{"metadata_indexed": N, "skipped": M, "errors": K}`

**`index_embeddings(db_session, force_reindex) -> dict`**
- Uses `EmbeddingService("intfloat/e5-base-v2")` (local sentence-transformers, NOT LMStudio)
- Iterates rules where `embedding IS NULL` (or all if force_reindex)
- Generates main embedding + section embeddings (title, description, tags, signature)
- Returns `{"embeddings_indexed": N, "skipped": M, "errors": K}`

**`index_rules(db_session, force_reindex) -> dict` (orchestrator)**
- Calls `index_metadata()` first
- Attempts `index_embeddings()`, catches failures gracefully
- Returns combined result dict with partial-success semantics

### CLI additions (`src/cli/sigma_commands.py`)

- `sigma index-metadata` subcommand
- `sigma index-embeddings` subcommand
- `sigma index` remains as orchestrator (backward compatible)
- Output reports: metadata count, embedding count, skipped/failed counts

### LMStudio decoupling

- `sigma_sync_service.py` no longer imports `LMStudioEmbeddingClient`
- `LMStudioEmbeddingClient` remains for other use cases

### Database

No schema changes. Embedding columns on `SigmaRuleTable` are already nullable.

## Story 2: Capability Model + Accurate Warnings

### `CapabilityService` (`src/services/capability_service.py`)

```python
class CapabilityService:
    def compute_capabilities(self, db_session=None) -> dict:
        """Probe runtime state, return capability flags."""
        return {
            "article_retrieval": {
                "enabled": bool,
                "reason": str
            },
            "sigma_metadata_indexing": {
                "enabled": bool,  # sigma repo cloned
                "reason": str
            },
            "sigma_embedding_indexing": {
                "enabled": bool,  # embedding model loadable
                "reason": str
            },
            "sigma_retrieval": {
                "enabled": bool,  # sigma_rules with embeddings exist
                "reason": str,
                "action": str  # e.g., "Run sigma index-embeddings"
            },
            "sigma_novelty_comparison": {
                "enabled": bool,  # sigma_rules with canonical_json exist
                "reason": str
            },
            "llm_generation": {
                "enabled": bool,
                "provider": str,  # "openai"|"anthropic"|"lmstudio"|"none"
                "reason": str
            }
        }
```

Checks performed:
- `article_retrieval`: Try loading `EmbeddingService("all-mpnet-base-v2")`, check DB for articles with embeddings
- `sigma_metadata_indexing`: Check if `./data/sigma-repo/rules/` exists
- `sigma_embedding_indexing`: Try loading `EmbeddingService("intfloat/e5-base-v2")`
- `sigma_retrieval`: Query `SELECT COUNT(*) FROM sigma_rules WHERE embedding IS NOT NULL`
- `sigma_novelty_comparison`: Query `SELECT COUNT(*) FROM sigma_rules WHERE canonical_json IS NOT NULL`
- `llm_generation`: Check for configured provider keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, LMSTUDIO_API_URL)

### API endpoint

`GET /api/capabilities` in `src/web/routes/health.py` - returns the capability dict.

### CLI command

`cli capabilities check` - human-readable output
`cli capabilities check --json` - machine-readable for shell scripts

### Warning unification

**`start.sh` and `setup.sh`:** Replace hardcoded warning strings with:
```bash
capabilities_json=$($DC run --rm cli python -m src.cli.main capabilities check --json 2>/dev/null)
# Parse sigma_retrieval.enabled, llm_generation.enabled, etc.
# Display warnings derived from reason/action fields
```

**Web UI:** Settings page and RAG chat page call `/api/capabilities`, render status banners from response.

### Warning copy matrix

| Capability | When disabled |
|---|---|
| article_retrieval | "Article semantic search unavailable - embedding model not loaded" |
| sigma_retrieval | "Sigma rule search in RAG unavailable - run `sigma index-embeddings`" |
| sigma_novelty_comparison | "Sigma novelty comparison unavailable - run `sigma index-metadata`" |
| llm_generation | "LLM answer generation unavailable - configure an API key (OpenAI or Anthropic)" |

## Story 3: RAG API Degradation Contract

### `/api/chat/rag` response extension

Add `capabilities` block to response:

```json
{
    "response": "...",
    "relevant_articles": [...],
    "relevant_rules": [],
    "total_results": 5,
    "total_rules": 0,
    "capabilities": {
        "article_retrieval": {"enabled": true},
        "sigma_retrieval": {
            "enabled": false,
            "reason": "No Sigma rules with embeddings found",
            "action": "Run sigma index-embeddings to enable"
        },
        "llm_generation": {
            "enabled": true,
            "provider": "openai"
        }
    },
    ...existing fields unchanged...
}
```

### Distinguishing empty results from unavailable capability

- `sigma_retrieval.enabled=false` + `relevant_rules=[]` = capability unavailable
- `sigma_retrieval.enabled=true` + `relevant_rules=[]` = query found zero matches

### Frontend (`RAGChat.jsx`)

When `capabilities.sigma_retrieval.enabled === false`, display actionable banner with the `action` text.

### Backward compatibility

New `capabilities` field is additive. Existing clients ignoring it continue working.

## Story 4: Migration + Operational Backfill

### Backfill commands

- **`sigma backfill-metadata`** - Recomputes `canonical_json`, `exact_hash`, `canonical_text`, `logsource_key` for existing rows using stored `logsource`/`detection` JSONB. No file system access needed.
- **`sigma index-embeddings`** - Generates embeddings for rows where `embedding IS NULL` using local sentence-transformers. Doubles as both new-indexing and backfill command.

### Upgrade path for existing deployments

1. Existing rules with LMStudio-generated embeddings keep their embeddings (no data loss)
2. Run `sigma backfill-metadata` to populate canonical fields for rules missing them
3. New rules use local sentence-transformers for embeddings going forward
4. Optional: `sigma index-embeddings --force` to regenerate all embeddings for consistency

### Scheduler updates

Celery task calling `sync_service.index_rules()` uses the new orchestrator with partial-success semantics. Metadata indexing always runs; embedding indexing failure logs a warning instead of failing the job.

## Feature Matrix

| Feature | Requires Sigma Repo | Requires Embeddings | Requires LLM Provider | Requires LMStudio |
|---|---|---|---|---|
| Sigma metadata indexing | Yes | No | No | **No** |
| Sigma novelty comparison | Yes (metadata) | No | No | **No** |
| Sigma rule search in RAG | Yes (metadata) | Yes (local) | No | **No** |
| Article semantic search | No | No (local model) | No | **No** |
| LLM answer generation | No | No | Yes (any) | **No** |
| Local LLM inference | No | No | No | Yes |
| Local model loading/listing | No | No | No | Yes |

## Files Changed

### New files
- `src/services/capability_service.py`

### Modified files
- `src/services/sigma_sync_service.py` - split index_rules into phases
- `src/cli/sigma_commands.py` - add subcommands
- `src/web/routes/chat.py` - add capabilities to RAG response
- `src/web/routes/health.py` - add /api/capabilities endpoint
- `src/web/static/js/components/RAGChat.jsx` - capability banners
- `setup.sh` - capability-driven warnings
- `start.sh` - capability-driven warnings
- `src/worker/celery_app.py` - partial-success task handling
- `src/web/templates/settings.html` - capability status display

### Untouched
- `src/services/lmstudio_embedding_client.py` - remains for other use cases
- `src/database/models.py` - no schema changes
- `src/services/rag_service.py` - no changes needed
- `src/services/sigma_novelty_service.py` - no changes needed
- `src/services/embedding_service.py` - no changes needed

## Testing

1. **Metadata-only indexing:** Mock embedding service as unavailable, verify rules indexed with metadata + canonical fields, embeddings NULL
2. **Embeddings-available path:** Verify full pipeline works end-to-end with local sentence-transformers
3. **No-LMStudio capability messaging:** Verify CapabilityService returns correct flags when LMStudio env vars are unset
4. **RAG response metadata:** Verify capabilities block in /api/chat/rag response reflects actual state
5. **Degraded mode:** Verify RAG chat returns actionable message when sigma embeddings absent
6. **Backward compatibility:** Existing sigma index command still works, existing embedded rules preserved
7. **Shell script warnings:** Verify setup.sh/start.sh output matches /api/capabilities output
