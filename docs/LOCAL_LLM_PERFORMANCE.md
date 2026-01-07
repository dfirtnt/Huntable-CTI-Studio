# Local LLM Performance Testing Guide

This document provides comprehensive guidance for setting up and testing local LLM providers for maximum performance on Apple Silicon Macs.

## Overview

CTI Scraper now supports 6 LLM providers with a performance-optimized fallback chain:

1. **MLX** (Apple Metal) - Fastest for Apple Silicon
2. **llama.cpp** (Metal backend) - Highly optimized C++ inference
3. **LM Studio** (OpenAI-compatible) - User-friendly GUI with server mode
4. **OpenAI** (Cloud) - GPT-4o-mini API
5. **Anthropic** (Cloud) - Claude Haiku API

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

## Integration with CTI Scraper

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

**Note:** This performance testing system is part of CTI Scraper v3.0.0-beta "Copernicus" - a major release focused on local LLM performance optimization for Apple Silicon Macs.
