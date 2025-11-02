# Fixing Mixtral 8x7B Load Error

## ⚠️ Critical Issue: LMStudio Version Incompatibility

**The model appears in `/v1/models` but fails when actually loaded.** This indicates your LMStudio version doesn't fully support Mixtral 8x7B's MoE architecture.

## Error: "missing tensor 'blk.0.ffn_down_exps.weight'"

This error on Mixtral 8x7B typically indicates a **GGUF file format incompatibility** with your LMStudio version.

### Quick Fix

**Option 1: Use the Already-Loaded Model**
- `mixtral-8x7b-instruct-v0.1` is already loaded in your LMStudio
- You can use this for testing - it should work

**Option 2: Update LMStudio**
1. Check LMStudio version: **Help → About**
2. Update to latest version if available
3. Mixtral 8x7B requires LMStudio **v0.2.20+** (verify your version supports MoE models)

**Option 3: Try Different Download Source**
- Instead of TheBloke, try **direct HuggingFace download**:
  - LMStudio → Models → Browse
  - Search: `mistralai/Mixtral-8x7B-Instruct-v0.1`
  - Download Q4_K_M from HuggingFace directly

**Option 4: Clear and Re-download**
```bash
# Mac - clear LMStudio cache
rm -rf ~/Library/Application\ Support/LM\ Studio/cache/
rm -rf ~/Library/Application\ Support/LM\ Studio/models/mistralai*
```
- Restart LMStudio
- Re-download from LMStudio's built-in browser (not manual download)

### Why This Happens

TheBloke's GGUF files sometimes use newer GGUF versions that older LMStudio releases don't support. The `ffn_down_exps.weight` tensor is part of Mixtral's MoE (Mixture of Experts) architecture, and the GGUF format for MoE models requires specific support.

### Recommended Action

**❌ Don't use Mixtral 8x7B** - Your LMStudio version doesn't support it properly.

**✅ Use alternatives that work:**

1. **Mistral 7B Instruct v0.3** (Recommended - Similar to Mixtral, non-MoE)
   - Already loaded: `mistralai/mistral-7b-instruct-v0.3`
   - Similar architecture to Mixtral (same base, just not MoE)
   - Better compatibility with LMStudio 0.3.30
   - **Action:** Use this model for scoring instead

2. **qwen2-7b-instruct** (Already tested, excellent scores)
   - Fast and reliable
   - Already in your benchmarks

3. **For Mixtral 8x7B specifically:**
   - You're on LMStudio 0.3.30 (latest) - version is fine
   - The model file may be corrupted or incomplete
   - **Try:** Delete model → Download via LMStudio's browser (not manual)
   - **Or:** Try a different quantization (Q3_K_M, Q5_K_M) to see if format differs

### Why This Fails

Mixtral 8x7B uses **MoE (Mixture of Experts)** with 8 expert networks. The `ffn_down_exps.weight` tensor is part of the expert routing system. Older LMStudio versions don't fully implement this architecture, causing the tensor to be missing even when the model file is correct.
