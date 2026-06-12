# Retrieval: Semantic Search via MCP

Huntable CTI Studio indexes articles and Sigma rules as dense vectors and exposes retrieval through the **Huntable MCP server**, which any MCP-capable client (Claude Desktop, Cursor, etc.) can drive for conversational retrieval.

The previous in-app RAG Chat UI was removed in v6.0.0 and the in-app `/search` page has also been retired. All semantic search is now accessed via MCP tools.

## Core Components

1. **Embedding Service** (`src/services/embedding_service.py`)
   - Model: Sentence Transformers `all-mpnet-base-v2` (768-dimensional)
   - Device: CUDA if available, else CPU
   - Enriched text: title + source + summary + tags + content

2. **Vector Storage** (`src/database/models.py`)
   - `articles.embedding` -- `Vector(768)` with pgvector index
   - `article_annotations.embedding` -- chunk-level
   - `sigma_rules.embedding` -- rule-level
   - `embedding_model` column tracks the model that produced each vector

3. **Semantic Search Service** (`src/services/rag_service.py`)
   - Dual search: article-level + chunk-level
   - Cosine similarity via pgvector `<=>`
   - Used by:
     - MCP tools: `search_articles`, `search_articles_by_keywords`, `search_unified`, `search_sigma_rules` (`src/huntable_mcp/tools/`)
     - CLI: `./run_cli.sh embed stats | similar` (`src/cli/commands/embed.py`)
     - Agentic workflow (`src/workflows/agentic_workflow.py`)

4. **Sigma similarity / novelty**
   - Workflow duplicate detection uses the behavioral novelty engine (Jaccard x Containment - Filter when `sigma_atom_similarity` is installed; exact-hash short-circuits are the only retained legacy label).
   - Cosine similarity is used for **rule retrieval**, not workflow duplicate ranking.

## Using MCP for retrieval

Point an MCP-capable client at the Huntable MCP server. See [MCP tools reference](../reference/mcp-tools.md).

The committed `.mcp.json` launches the server via `scripts/run_mcp_server.sh`, which runs it **inside the Docker `cli` container**. This is required, not incidental: query-time semantic search loads the local embedding model (torch / sentence-transformers), and those packages have no `macosx_x86_64` wheel — so a bare host process on an Intel Mac fails with `Could not load embedding model`. Running in the Linux container makes semantic search work on every platform. **Docker must be running** when the client launches the server.

Available tools (non-exhaustive):

| Tool | Purpose |
|---|---|
| `search_articles` | Natural-language article search |
| `search_articles_by_keywords` | Boolean/keyword article search |
| `search_unified` | Cross-source retrieval (articles + Sigma) |
| `search_sigma_rules` | Sigma rule retrieval by query |
| `get_article` / `get_sigma_rule` | Fetch by ID |
| `get_stats` | Embedding coverage stats |

## Indexing

Run once after setup, then again whenever Sigma rules change:

```
./run_cli.sh sigma index-embeddings
./run_cli.sh embed stats
```

Indexing runs inside the `cli` container and embeds rules **in chunks, committing each chunk** as it goes. This means the operation is **resumable**: without `--force` it only processes rules whose `embedding` is `NULL`, so if a run is interrupted (e.g. the container is OOM-killed on a memory-constrained host while the full stack is up), simply re-run the same command and it continues from where it stopped — already-embedded rows are kept. Check progress any time with `./run_cli.sh embed stats` or MCP `get_stats`.

On a low-memory host, lower the per-chunk working set with the `SIGMA_EMBED_RULES_PER_CHUNK` environment variable (default 64) to reduce peak memory at the cost of more commits:

```
SIGMA_EMBED_RULES_PER_CHUNK=32 ./run_cli.sh sigma index-embeddings
```

## Embedding coverage API

`GET /api/embeddings/stats` returns a `sigma_corpus` block (SigmaHQ row counts vs. rows with embeddings). Consumed by CLI `embed stats` and MCP `get_stats`.

_Last updated: 2026-06-08_
