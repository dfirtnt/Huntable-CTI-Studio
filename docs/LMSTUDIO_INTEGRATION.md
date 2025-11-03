# LMStudio Integration Guide

## Setup

1. **Start LMStudio**:
   - Open LMStudio
   - Go to Developer tab → Local Server
   - Enable "Serve on local network"
   - Start server (default port: 1234)
   - Load your preferred model

2. **Run CTIScraper with LMStudio**:
```bash
# Start with LMStudio override
docker-compose -f docker-compose.yml -f docker-compose.lmstudio.yml up web

# Or start all services
docker-compose -f docker-compose.yml -f docker-compose.lmstudio.yml up
```

3. **Configure Model Name**:
   - Edit `docker-compose.lmstudio.yml`
   - Set `LMSTUDIO_MODEL` to your loaded model name
   - Example: `LMSTUDIO_MODEL=llama-3.1-8b-instruct`

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

## Environment Variables

### Required
- `LMSTUDIO_API_URL`: LMStudio API endpoint (default: `http://host.docker.internal:1234/v1`)
- `LMSTUDIO_MODEL`: Model name in LMStudio (default: `llama-3.2-1b-instruct`)

### Recommended Settings (for Deterministic Scoring)
- `LMSTUDIO_TEMPERATURE`: Temperature for inference (default: `0.15`, recommended: `0.1-0.2`)
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

#### Context Length Requirements by Use Case

**Article Scoring (SIGMA Huntability Ranking):**
- **Minimum Required:** 8192 tokens (for smaller articles)
- **Recommended:** 16384-32768 tokens (for full article analysis)
- **Prompt Size:** ~6000-8000 input tokens (full rubric + article content)
- **Error if too small:** "Trying to keep the first X tokens when context overflows. However, the model is loaded with context length of only Y tokens"

**SIGMA Rule Generation:**
- CTIScraper automatically truncates content based on detected model size:
  - 1B models: ~550 tokens of content (~2200 chars)
  - 3B models: ~2600 tokens of content (~10400 chars)  
  - 8B+ models: ~6700 tokens of content (~26800 chars)

**Chat/RAG Queries:**
- Varies by conversation length
- Typically requires 4096-8192 tokens for standard queries

The application uses the OpenAI-compatible HTTP API (`/v1/chat/completions`), which does not support runtime context length configuration. If you need programmatic context length control, you would need to switch to the LMStudio Python SDK, which is not currently implemented.
