# Fixing LLaMA 3.1 8B Instruct Corrupted Output

## Problem
Model generates garbled output:
- `'**. \n\nThe End of the story is near...'`
- `'assistantassistantassistant...'` (repetition loops)
- Asterisk patterns: `*-**-**-**-**-**-*`

## Root Cause
**Model file is corrupted or incompatible quantization.**

## Fix Steps

### Step 1: Unload and Reload Model
1. **LMStudio → Models tab**
2. Find `meta-llama-3.1-8b-instruct`
3. Click **Unload** (or Stop)
4. Delete the model files if needed:
   ```bash
   # Mac
   rm -rf ~/Library/Application\ Support/LM\ Studio/models/meta-llama/Meta-Llama-3.1-8B-Instruct*
   ```
5. Re-download in LMStudio

### Step 2: Try Different Quantization
Current may be corrupted. Try:
- **Q5_K_M** (higher quality, less likely corrupted)
- **Q8_0** (highest quality)
- Avoid Q4_K_M if that's what failed

### Step 3: Check Context Length
- Set to **8192** initially (not 16384)
- Test with simple prompts first
- Gradually increase if working

### Step 4: Verify Model Version
Ensure you have:
- `meta-llama-3.1-8b-instruct` (not `meta-llama-3-8b-instruct`)
- From HuggingFace repository
- Not a custom/fine-tuned variant

### Step 5: Test Simple Prompt
After reload, test:
```bash
curl -X POST http://localhost:1234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama-3.1-8b-instruct",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 10
  }'
```

If still garbled → model file is corrupted, re-download.

## Alternative: Skip This Model

If issues persist after re-download:
- **Mistral 7B Instruct v0.3** ✅ (working, similar size)
- **qwen2-7b-instruct** ✅ (working, tested)
- **codellama-7b-instruct** ✅ (working, tested)

All provide similar performance for scoring.
