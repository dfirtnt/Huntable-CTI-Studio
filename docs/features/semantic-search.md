# Retrieval: Semantic Search and MCP

Huntable CTI Studio indexes articles and Sigma rules as dense vectors and exposes retrieval two ways:

- The in-app **semantic search** page (`/search`)
- The **Huntable MCP server**, which any MCP-capable client (Claude Desktop, Cursor, etc.) can drive for conversational retrieval

The previous in-app RAG Chat UI was removed in v5.5.0. Conversational retrieval has moved to MCP.

## Core Components

1. **Embedding Service** (`src/services/embedding_service.py`)
   - Model: Sentence Transformers `all-mpnet-base-v2` (768-dimensional)
   - Device: CUDA if available, else CPU
   - Enriched text: title + source + summary + tags + content

2. **Vector Storage** (`src/database/models.py`)
   - `articles.embedding` — `Vector(768)` with pgvector index
   - `article_annotations.embedding` — chunk-level
   - `sigma_rules.embedding` — rule-level
   - `embedding_model` column tracks the model that produced each vector

3. **RAG Service** (`src/services/rag_service.py`)
   - Dual search: article-level + chunk-level
   - Cosine similarity via pgvector `<=>`
   - Used by:
     - Web semantic search at `/search` (`src/web/routes/search.py`)
     - MCP tools: `search_articles`, `search_articles_by_keywords`, `search_unified`, `search_sigma_rules` (`src/huntable_mcp/tools/`)
     - CLI: `./run_cli.sh embed stats | similar` (`src/cli/commands/embed.py`)
     - Agentic workflow (`src/workflows/agentic_workflow.py`)

4. **Sigma similarity / novelty**
   - Workflow duplicate detection uses the behavioral novelty engine (Jaccard × Containment − Filter when `sigma_semantic_similarity` is installed; legacy Atom/Logic-shape scoring otherwise).
   - Cosine similarity is used for **rule retrieval**, not workflow duplicate ranking.

## Using MCP for conversational retrieval

Point an MCP-capable client at the Huntable MCP server. See [MCP tools reference](../reference/mcp-tools.md).

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

## Embedding coverage API

`GET /api/embeddings/stats` returns a `sigma_corpus` block (SigmaHQ row counts vs. rows with embeddings). Consumed by `/search`, CLI `embed stats`, and MCP `get_stats`.

_Last updated: 2026-05-01_
