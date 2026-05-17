# LM Studio Integration

## Overview

This guide covers setting up and optimizing LM Studio for local LLM inference with Huntable CTI Studio.

## Setup

1. **Start LMStudio**:
   - Open LMStudio
   - Go to Developer tab -> Local Server
   - Enable "Serve on local network"
   - Start server (default port: 1234)
   - Load your preferred model

2. **Run Huntable CTI Studio with LMStudio**:
```bash
# Start services (LMStudio config is already in docker-compose.yml)
docker compose up web

# Or start all services
docker compose up
```

3. **Configure Model Name**:
   - Edit `.env` file or set environment variables
   - Set `LMSTUDIO_MODEL` to your loaded model name
   - Example: `LMSTUDIO_MODEL=deepseek/deepseek-r1-0528-qwen3-8b`
   - The main `docker-compose.yml` already includes LMStudio configuration pointing to `host.docker.internal:1234/v1`

## API Usage

In the web interface, select `lmstudio` as the LLM provider in chat settings.

## Troubleshooting

- **Workflow fails immediately with "LMStudio is not reachable"**: The workflow engine probes LMStudio before starting any run that uses an LMStudio provider. If the probe fails, the execution is marked failed right away rather than timing out mid-run. Start LMStudio, confirm the server is running (green indicator in the LMStudio UI), then re-trigger the workflow.
- **Connection refused**: Ensure LMStudio server is running and accessible
- **Model not found**: Verify model name matches exactly in LMStudio
- **Timeout errors**: Increase timeout in `_call_lmstudio()` method if needed
- **Context length errors**: 
  - Error: "context overflow" or "context length of only X tokens, which is not enough"
  - **Solution**: Increase context length in LMStudio UI (Context tab) to at least 16384 tokens for article scoring
  - **For article scoring**: Use 16384-32768 tokens minimum
  - Model must be reloaded after changing context length

## Configuring the LM Studio URL

The LM Studio server URL can change (e.g. different machine or IP). Set it in two places:

1. **Setup**: When you run `./setup.sh` and choose to use LM Studio, you can optionally enter the server URL (e.g. `http://192.168.1.65:1234`). Leave blank for the default `host.docker.internal:1234`.
2. **Settings UI**: In **Settings -> Agentic Workflow Configuration**, enable "Use LM Studio" and use the **LM Studio server URL (base)** and **LM Studio embedding URL** fields. These override `.env` and take effect after save (and on next app startup).

If the configured URL is unreachable, the app tries fallback hosts (e.g. localhost, host.docker.internal) automatically for embedding requests.

## Environment Variables

### Required
- `LMSTUDIO_API_URL`: LMStudio API endpoint (default: `http://host.docker.internal:1234/v1`). Can also be set in Settings UI.
- `LMSTUDIO_MODEL`: Model name in LMStudio (default: `deepseek/deepseek-r1-0528-qwen3-8b`)

- `LMSTUDIO_EMBEDDING_URL`: Embedding API endpoint (default: `http://host.docker.internal:1234/v1/embeddings`). Used for Sigma rule embeddings (e.g. `sigma index`). Can also be set in Settings UI. The app tries fallback URLs if the primary is unreachable.

### Per-Agent Model Overrides
- `LMSTUDIO_MODEL_RANK`: Model for ranking agent (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MODEL_EXTRACT`: Model for extraction agent (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MODEL_SIGMA`: Model for Sigma generation (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MAX_CONTEXT`: Maximum context window size (tokens). Must also be set in LM Studio UI.

### Recommended Settings (for Deterministic Scoring)
- `LMSTUDIO_TEMPERATURE`: Temperature for inference (default: `0.0` for deterministic scoring)
- `LMSTUDIO_TOP_P`: Top-p sampling parameter (default: `0.9`)
- `LMSTUDIO_SEED`: Random seed for deterministic outputs (default: `42`)

## Model Configuration (Must be set in LMStudio UI)

### Quantization
Quantization (Q4_K_M, Q6_K, Q8_0) must be set in LMStudio UI when loading the model; this cannot be controlled via API. For speed: Q4_K_M. For accuracy: Q6_K or Q8_0.

### Context Length
**Context length cannot be set remotely via the OpenAI-compatible HTTP API.** Configure the context window when loading the model in LMStudio UI or CLI:

**Automated (Recommended):**
- Use the provided script to load with correct context length:
  ```bash
  ./scripts/load_lmstudio_model.sh
  ```
  - Reads `LMSTUDIO_MODEL` and `LMSTUDIO_MAX_CONTEXT` from `.env`
  - Automatically loads model with specified context length
  - Run this after starting LMStudio server, or add to startup sequence

**Manual Options:**
- **In LMStudio UI**: 
  1. Load your model in LMStudio
  2. Go to the **Context** tab in the right panel
  3. Adjust the **Context Length** slider (or enter value directly)
  4. Model must be reloaded for changes to take effect
- **Via CLI**: Use `lms load <model-name> --context-length <tokens>`

**Important:** 
- Context length is set at model load time and cannot be changed via API calls
- Exceeding the model's maximum context length will cause errors like: "context overflow" or "context length of only X tokens, which is not enough"
- Default context windows: 1B models (~2048), 3B models (~4096), 8B models (~8192), 20B+ models (~4096-8192 default)

**Docker Compose variance:** In `docker-compose.yml`, the web service and worker/workflow_worker services can set different per-model context lengths (e.g. `LMSTUDIO_CONTEXT_LENGTH_<model_slug>`). For example, the web service may use 16384 for article scoring while workers use 4096. Check the compose file for your service if you see context-length errors in one component but not another.

#### Context Length Requirements by Use Case

**Article Scoring (Sigma Huntability Ranking):**
- **Minimum Required:** 8192 tokens (for smaller articles)
- **Recommended:** 16384-32768 tokens (for full article analysis)
- **Prompt Size:** ~6000-8000 input tokens (full rubric + article content)
- **Error if too small:** "Trying to keep the first X tokens when context overflows. However, the model is loaded with context length of only Y tokens"

**Sigma Rule Generation:**
- Huntable CTI Studio automatically truncates content based on detected model size:
  - 1B models: ~550 tokens of content (~2200 chars)
  - 3B models: ~2600 tokens of content (~10400 chars)  
  - 8B+ models: ~6700 tokens of content (~26800 chars)

**MCP / Semantic Queries:**
- Varies by conversation length
- Typically requires 4096-8192 tokens for standard queries

The application uses the OpenAI-compatible HTTP API (`/v1/chat/completions`), which does not support runtime context length configuration. If you need programmatic context length control, you would need to switch to the LMStudio Python SDK, which is not currently implemented.

## LM Studio 0.4.0+ (optional improvements)

The following features from [LM Studio 0.4.0](https://lmstudio.ai/blog/0.4.0) are relevant to Huntable CTI Studio:

| Feature | Relevance | Action |
|--------|-----------|--------|
| **llmster (headless daemon)** | High | Run LM Studio backend without the GUI on a server/GPU rig. Install: `curl -fsSL https://lmstudio.ai/install.sh \| bash` then `lms daemon up`, `lms server start`. Point `LMSTUDIO_API_URL` at that host. No app code change. |
| **Parallel requests (continuous batching)** | High | Multiple concurrent requests to the same model instead of queuing. In LM Studio model loader: set **Max Concurrent Predictions** (e.g. 4) and keep **Unified KV Cache** enabled. Improves throughput for workflow (rank, extract, sigma) and multi-article runs. No app code change. |
| **Stateful `/v1/chat` API** | Medium | New endpoint with `response_id` / `previous_response_id` for smaller follow-up payloads and response stats. Current app uses stateless `/chat/completions`; migrating is optional and would require a dedicated client path and tests. |
| **Permission keys** | Low | If exposing LM Studio (or llmster) on a shared network, generate keys in Settings -> Server and pass via header. Document when we add optional auth to LM Studio requests. |

**Recommendation:** Document llmster and parallel-request settings for users who run LM Studio 0.4.0+; consider `/v1/chat` only if we need smaller payloads or response metrics for multi-turn flows.

## Test Endpoint

Use `POST /api/test-lmstudio` from the web UI to validate LMStudio connectivity. This endpoint checks that the LMStudio server is reachable and the configured model is loaded and responding.

---

## Benchmark Tooling

<!-- AUDIT: Accuracy -- The "Performance Benchmarks" section that previously appeared here (lines 146-463) documented MLX and llama.cpp as active providers with installation instructions and benchmark timing tables. These providers are NOT implemented in src/. Only LM Studio is active. The section has been removed to prevent user confusion. Scripts exist (scripts/benchmark_llm_providers.py, scripts/setup_local_models.sh) for future use once providers are implemented. -->

`scripts/benchmark_llm_providers.py` runs performance tests against active LLM providers. Currently only LM Studio is an active local provider; MLX and llama.cpp are planned but not implemented.

```bash
# Test LM Studio performance
python scripts/benchmark_llm_providers.py --provider lmstudio

# Quick test (fewer prompts)
python scripts/benchmark_llm_providers.py --quick
```

Results are written to `logs/llm_benchmark_results_TIMESTAMP.json`.

_Last updated: 2026-05-17_
_Last reviewed: 2026-05-03_
