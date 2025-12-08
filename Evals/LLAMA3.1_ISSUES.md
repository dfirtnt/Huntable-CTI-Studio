# LLaMA 3.1 8B Instruct - Garbled Output Issue

## Symptoms

LMStudio logs show garbled output:
- Patterns like `*-**-**-**-**-**-*` or `**-**-**-**-**-**-`
- `**Grading:**-**[1] **0.0 (null)**`
- Model generates 856 tokens but content is corrupted

## Possible Causes

1. **Corrupted Model File**
   - Download interrupted or file corrupted
   - Solution: Re-download model in LMStudio

2. **Wrong Quantization**
   - Model quantized incorrectly
   - Solution: Try different quantization (Q4_K_M, Q5_K_M, Q8_0)

3. **Context Length Too High**
   - Exceeds model's capabilities
   - Solution: Try lower context length (8192, 16384 instead of 32768)

4. **Model Architecture Mismatch**
   - Wrong variant loaded (instruct vs base)
   - Solution: Ensure `meta-llama-3.1-8b-instruct` (not base)

5. **LMStudio Version Issue**
   - Version incompatibility with LLaMA 3.1
   - Solution: Update LMStudio to latest version

## Troubleshooting Steps

### Step 1: Test Simple Prompt
```bash
curl -X POST http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama-3.1-8b-instruct",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 20
  }'
```

If this also returns garbled output, the model file is corrupted.

### Step 2: Reload Model
1. In LMStudio: **Models** tab
2. Select `meta-llama-3.1-8b-instruct`
3. Click **Unload**
4. Click **Download** again (or use **Load** if already downloaded)
5. Set context length to **16384** (not higher initially)
6. Test again

### Step 3: Try Different Quantization
- Delete current model files
- Re-download with different quantization:
  - **Q4_K_M** (default, balanced)
  - **Q5_K_M** (higher quality)
  - **Q8_0** (highest quality, larger files)

### Step 4: Check LMStudio Version
- **Help → About** - ensure latest version
- LLaMA 3.1 requires LMStudio v0.2.20+

## Alternative: Use Different Model

If LLaMA 3.1 8B continues to have issues:
- **Mistral 7B Instruct v0.3** (tested, working)
- **qwen2-7b-instruct** (tested, working)
- **codellama-7b-instruct** (tested, working)

These models have proven reliable for article scoring.
