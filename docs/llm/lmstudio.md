# LM Studio Integration

## Overview

This guide covers setting up and optimizing LM Studio for local LLM inference with Huntable CTI Studio.

## Setup

1. **Start LMStudio**:
   - Open LMStudio
   - Go to Developer tab → Local Server
   - Enable "Serve on local network"
   - Start server (default port: 1234)
   - Load your preferred model

2. **Run Huntable CTI Studio with LMStudio**:
```bash
# Start services (LMStudio config is already in docker-compose.yml)
docker-compose up web

# Or start all services
docker-compose up
```

3. **Configure Model Name**:
   - Edit `.env` file or set environment variables
   - Set `LMSTUDIO_MODEL` to your loaded model name
   - Example: `LMSTUDIO_MODEL=deepseek/deepseek-r1-0528-qwen3-8b`
   - The main `docker-compose.yml` already includes LMStudio configuration pointing to `host.docker.internal:1234/v1`

## API Usage

In the web interface, select `lmstudio` as the LLM provider in chat settings.

## Troubleshooting

- **Connection refused**: Ensure LMStudio server is running and accessible
- **Model not found**: Verify model name matches exactly in LMStudio
- **Timeout errors**: Increase timeout in `_call_lmstudio()` method if needed
- **Context length errors**: 
  - Error: "context overflow" or "context length of only X tokens, which is not enough"
  - **Solution**: Increase context length in LMStudio UI (Context tab) to at least 16384 tokens for article scoring
  - **For article scoring**: Use 16384-32768 tokens minimum
  - Model must be reloaded after changing context length

## Configuring the LM Studio URL

The LM Studio server URL can change (e.g. different machine or IP). You can set it in two places:

1. **Setup**: When you run `./setup.sh` and choose to use LM Studio, you can optionally enter the server URL (e.g. `http://192.168.1.65:1234`). Leave blank for the default `host.docker.internal:1234`.
2. **Settings UI**: In **Settings → Agentic Workflow Configuration**, enable "Use LM Studio" and use the **LM Studio server URL (base)** and **LM Studio embedding URL** fields. These override `.env` and take effect after save (and on next app startup).

If the configured URL is unreachable, the app tries fallback hosts (e.g. localhost, host.docker.internal) automatically for embedding requests.

## Environment Variables

### Required
- `LMSTUDIO_API_URL`: LMStudio API endpoint (default: `http://host.docker.internal:1234/v1`). Can also be set in Settings UI.
- `LMSTUDIO_MODEL`: Model name in LMStudio (default: `deepseek/deepseek-r1-0528-qwen3-8b`)

- `LMSTUDIO_EMBEDDING_URL`: Embedding API endpoint (default: `http://host.docker.internal:1234/v1/embeddings`). Used for Sigma rule embeddings (e.g. `sigma index`). Can also be set in Settings UI. The app tries fallback URLs if the primary is unreachable.

### Per-Agent Model Overrides
- `LMSTUDIO_MODEL_RANK`: Model for ranking agent (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MODEL_EXTRACT`: Model for extraction agent (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MODEL_SIGMA`: Model for SIGMA generation (default: `qwen/qwen3-4b-2507`)
- `LMSTUDIO_MAX_CONTEXT`: Maximum context window size (tokens). Must also be set in LM Studio UI.

### Recommended Settings (for Deterministic Scoring)
- `LMSTUDIO_TEMPERATURE`: Temperature for inference (default: `0.0` for deterministic scoring)
- `LMSTUDIO_TOP_P`: Top-p sampling parameter (default: `0.9`)
- `LMSTUDIO_SEED`: Random seed for deterministic outputs (default: `42`)

## Model Configuration (Must be set in LMStudio UI)

### Quantization
Quantization (Q4_K_M, Q6_K, Q8_0) must be set in LMStudio UI when loading the model - this cannot be controlled via API. For speed: Q4_K_M. For accuracy: Q6_K or Q8_0.

### Context Length
**Context length cannot be set remotely via the OpenAI-compatible HTTP API.** The context window must be configured when loading the model in LMStudio UI or CLI:

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

**Article Scoring (SIGMA Huntability Ranking):**
- **Minimum Required:** 8192 tokens (for smaller articles)
- **Recommended:** 16384-32768 tokens (for full article analysis)
- **Prompt Size:** ~6000-8000 input tokens (full rubric + article content)
- **Error if too small:** "Trying to keep the first X tokens when context overflows. However, the model is loaded with context length of only Y tokens"

**SIGMA Rule Generation:**
- Huntable CTI Studio automatically truncates content based on detected model size:
  - 1B models: ~550 tokens of content (~2200 chars)
  - 3B models: ~2600 tokens of content (~10400 chars)  
  - 8B+ models: ~6700 tokens of content (~26800 chars)

**Chat/RAG Queries:**
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
| **Permission keys** | Low | If exposing LM Studio (or llmster) on a shared network, generate keys in Settings → Server and pass via header. Document when we add optional auth to LM Studio requests. |

**Recommendation:** Document llmster and parallel-request settings for users who run LM Studio 0.4.0+; consider `/v1/chat` only if we need smaller payloads or response metrics for multi-turn flows.

## Test Endpoint

Use `POST /api/test-lmstudio` from the web UI to validate LMStudio connectivity. This endpoint checks that the LMStudio server is reachable and the configured model is loaded and responding.

---

## Performance Benchmarks

## Local LLM Performance Testing

### Active Providers

1. **LM Studio** (OpenAI-compatible) — Active local model provider with GUI server mode
2. **OpenAI** (Cloud) — GPT-4o-mini API
3. **Anthropic** (Cloud) — Claude Haiku API

> **Note**: MLX and llama.cpp providers are planned but not yet implemented.

## Expected Performance Improvements

| Provider | 1B Model | 7B Model | Setup Complexity | Best For |
|----------|----------|----------|------------------|----------|
| **MLX** | 2-3s | 5-8s | Medium | Maximum speed on Apple Silicon |
| **llama.cpp** | 2-4s | 6-10s | Medium | Balanced speed and compatibility |
| **LM Studio** | 3-5s | 8-12s | Low | Easy setup with GUI |

## Setup Instructions

### 1. MLX (Apple Metal) - FASTEST

**Requirements:**
- macOS with Apple Silicon (M1/M2/M3)
- Python 3.11+ (Docker uses 3.11; local MLX setup supports 3.8+)

**Installation:**
```bash
# Install MLX packages
pip install mlx-lm

# Download models using setup script
./scripts/setup_local_models.sh --with-mlx --all-models
```

**Configuration:**
```bash
# In your .env file
MLX_ENABLED=true
MLX_MODEL_PATH=models/mlx/llama-3.2-1b-instruct
```

**Manual Model Download:**
```bash
# Download specific model
python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='mlx-community/Llama-3.2-1B-Instruct-4bit',
    local_dir='models/mlx/llama-3.2-1b-instruct',
    local_dir_use_symlinks=False
)
```

### 2. llama.cpp (Metal Backend) - VERY FAST

**Requirements:**
- macOS with Apple Silicon
- Python 3.11+ (Docker uses 3.11; local llama.cpp setup supports 3.8+)

**Installation:**
```bash
# Install llama-cpp-python with Metal support
pip install llama-cpp-python

# Download GGUF models
./scripts/setup_local_models.sh --with-llamacpp --all-models
```

**Configuration:**
```bash
# In your .env file
LLAMACPP_ENABLED=true
LLAMACPP_MODEL_PATH=models/gguf/llama-3.2-1b-instruct.gguf
```

**Manual Model Download:**
```bash
# Download GGUF file
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='microsoft/Llama-3.2-1B-Instruct-GGUF',
    filename='*.gguf',
    local_dir='models/gguf',
    local_dir_use_symlinks=False
)
```

### 3. LM Studio (OpenAI-Compatible) - EASY SETUP

**Requirements:**
- macOS/Windows/Linux
- LM Studio desktop app

**Installation:**
1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai/)
2. Install and launch the application
3. Go to "Models" tab and search for:
   - `llama-3.2-1b-instruct`
   - `llama-3.2-3b-instruct`
4. Download desired models
5. Go to "Server" tab and start local server (default: localhost:1234)

**Configuration:**
```bash
# In your .env file
LMSTUDIO_ENABLED=true
LMSTUDIO_API_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=llama-3.2-1b-instruct
```

## Performance Testing

### Automated Benchmark

Run the comprehensive benchmark script:

```bash
# Test all providers
python scripts/benchmark_llm_providers.py

# Test specific provider
python scripts/benchmark_llm_providers.py --provider mlx

# Quick test (fewer prompts)
python scripts/benchmark_llm_providers.py --quick
```

### Manual Testing

1. **Web UI Testing:**
   - Go to Settings page
   - Select provider from dropdown
   - Click "Test Connection" button
   - Verify successful connection

2. **RAG Chat Testing:**
   - Go to RAG Chat page
   - Select provider from dropdown
   - Ask threat intelligence questions
   - Compare response times and quality

### Benchmark Results

The benchmark script generates:
- **Terminal output:** Real-time progress and summary table
- **JSON results:** `logs/llm_benchmark_results_TIMESTAMP.json`
- **Markdown report:** `logs/LLM_BENCHMARK_REPORT_TIMESTAMP.md`

## Configuration Guide

### Environment Variables

Add to your `.env` file:

```bash
# Performance Testing - Local LLM Providers
LMSTUDIO_API_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=llama-3.2-1b-instruct
LMSTUDIO_ENABLED=false
# Docker: Use http://host.docker.internal:1234/v1 (default in Docker).
# Use http://localhost:1234/v1 only for non-Docker local development.

MLX_MODEL_PATH=models/mlx/llama-3.2-1b-instruct
MLX_ENABLED=false

LLAMACPP_MODEL_PATH=models/gguf/llama-3.2-1b-instruct.gguf
LLAMACPP_SERVER_URL=http://localhost:8080
LLAMACPP_ENABLED=false
```

### Provider Selection

The system uses an intelligent fallback chain:

1. **MLX** (if enabled and available)
2. **llama.cpp** (if enabled and available)
3. **LM Studio** (if enabled and available)
4. **Cloud APIs** (OpenAI/Anthropic)

## Troubleshooting

### Common Issues

**MLX Issues:**
```bash
# Error: MLX not installed
pip install mlx-lm

# Error: Model not found
./scripts/setup_local_models.sh --with-mlx llama-3.2-1b-instruct

# Error: Metal backend not available
# Ensure you're on Apple Silicon Mac
```

**llama.cpp Issues:**
```bash
# Error: llama-cpp-python not installed
pip install llama-cpp-python

# Error: GGUF model not found
./scripts/setup_local_models.sh --with-llamacpp llama-3.2-1b-instruct

# Error: Metal backend compilation failed
# Reinstall with Metal support
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --force-reinstall
```

**LM Studio Issues:**
```bash
# Error: Cannot connect to LM Studio
# 1. Ensure LM Studio is running
# 2. Check server is started (Server tab)
# 3. Verify port 1234 is not blocked
# 4. Check LMSTUDIO_API_URL in .env

# Error: Model not loaded
# 1. Go to Models tab in LM Studio
# 2. Load the model you want to use
# 3. Ensure model name matches LMSTUDIO_MODEL
```

### Performance Optimization

**MLX Optimization:**
- Use 4-bit quantized models for best speed/memory balance
- Ensure sufficient RAM (8GB+ recommended for 7B models)
- Close other GPU-intensive applications

**llama.cpp Optimization:**
- Use `n_gpu_layers=-1` to utilize all Metal layers
- Adjust `n_ctx` based on your use case (higher = more memory)
- Use GGUF format for best compatibility

**LM Studio Optimization:**
- Use GPU acceleration in LM Studio settings
- Load models into GPU memory when possible
- Close unnecessary applications to free GPU memory

### Memory Requirements

| Model Size | MLX RAM | llama.cpp RAM | LM Studio RAM |
|------------|---------|---------------|---------------|
| 1B | 2-3GB | 2-3GB | 2-3GB |
| 3B | 4-6GB | 4-6GB | 4-6GB |
| 7B | 8-12GB | 8-12GB | 8-12GB |

## Model Recommendations

### For Maximum Speed (Apple Silicon)
1. **MLX** with 1B model: 2-3 second responses
2. **llama.cpp** with 1B model: 2-4 second responses
3. **LM Studio** with 1B model: 3-5 second responses

### For Best Quality/Speed Balance
1. **MLX** with 3B model: 4-6 second responses
2. **llama.cpp** with 3B model: 5-8 second responses
3. **LM Studio** with 3B model: 6-10 second responses

### For Maximum Quality
1. **MLX** with 7B model: 8-12 second responses
2. **llama.cpp** with 7B model: 10-15 second responses
3. **LM Studio** with 7B model: 12-20 second responses

## Integration with Huntable CTI Studio

### RAG System Integration

The local LLM providers integrate seamlessly with the RAG system:

1. **Provider Selection:** Choose provider in Settings or use auto-selection
2. **Fallback Chain:** Automatic fallback if primary provider fails
3. **Context Management:** All providers use the same conversation context
4. **Response Format:** Consistent response format across all providers

### API Integration

All providers expose the same API interface:

```python
# Example usage
from src.services.llm_generation_service import get_llm_generation_service

service = get_llm_generation_service()

response = await service.generate_rag_response(
    query="Analyze this threat intelligence",
    retrieved_chunks=chunks,
    provider="mlx"  # or "auto" for automatic selection
)
```

## Best Practices

1. **Start with MLX** for maximum Apple Silicon performance
2. **Use llama.cpp** as backup for compatibility
3. **Keep LM Studio** for easy model management
4. **Test thoroughly** with the benchmark script
5. **Monitor memory usage** during extended use
6. **Update models regularly** for security and performance

## Support

For issues or questions:
1. Check this documentation first
2. Run the benchmark script for diagnostics
3. Check the logs in `logs/` directory
4. Verify environment variables and model paths
5. Test individual providers in the web UI

---

**Note:** Currently only LM Studio is implemented as an active local provider. MLX and llama.cpp are planned for future releases.
