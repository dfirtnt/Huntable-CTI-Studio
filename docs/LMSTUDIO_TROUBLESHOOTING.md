# LMStudio Model Loading Troubleshooting

## Error: "missing tensor 'blk.0.ffn_down_exps.weight'"

This error indicates an incomplete, corrupted, or architecture-mismatched model file.

### Solutions

#### 1. **Re-download the Model**
- Open LMStudio
- Go to **Models** tab
- Find the Mixtral 7B model
- Click **Delete** to remove the corrupted download
- Click **Download** again and wait for complete download
- **Verify download completes** - check file size matches expected size

#### 2. **Check File Integrity**
- Navigate to LMStudio model directory:
  - **Mac**: `~/Library/Application Support/LM Studio/models/`
  - **Windows**: `%APPDATA%\LM Studio\models\`
- Check if `.gguf` files are present and complete
- For Mixtral 7B, you should see files like:
  - `mixtral-7b-instruct-v0.1-Q4_K_M.gguf`
  - Or similar quantization variants

#### 3. **Try Different Quantization**
- The quantized version may be incompatible
- Try a different quantization level:
  - **Q4_K_M** (balanced, recommended first try)
  - **Q5_K_M** (higher quality)
  - **Q8_0** (highest quality, larger files)
- Or try **unquantized** if available (very large files)

#### 4. **Verify Model Architecture**
- Ensure you're loading **Mixtral 7B**, not **Mixtral 8x7B** (different architecture)
- Check model name matches exactly:
  - `mistralai/Mixtral-7B-Instruct-v0.1`
  - Not `mistralai/Mixtral-8x7B-Instruct-v0.1`

#### 5. **Clear LMStudio Cache**
```bash
# Mac
rm -rf ~/Library/Application\ Support/LM\ Studio/cache/

# Windows (PowerShell)
Remove-Item "$env:APPDATA\LM Studio\cache" -Recurse -Force
```
- Restart LMStudio
- Re-download model

#### 6. **Check Available Models**
```bash
curl http://localhost:1234/v1/models | python3 -m json.tool
```
- Verify model appears in the list
- If missing, it's not fully downloaded/corrupted

#### 7. **Alternative: Use Different Model**
If Mixtral 7B continues to fail:
- **Mistral 7B Instruct v0.2** (similar architecture, often more stable)
- **Mixtral 8x7B Instruct** (if you have enough VRAM/RAM - 47GB)
- **qwen2-7b-instruct** (tested and working in our benchmarks)

### Prevention

1. **Ensure stable internet connection** during download
2. **Don't interrupt downloads** - let them complete
3. **Check disk space** before downloading (7B quantized models ~4-8GB)
4. **Use official HuggingFace repositories** via LMStudio's model browser

### Next Steps

After fixing:
1. Load the model in LMStudio UI
2. Set context length to **16384** (for article scoring)
3. Test with a simple prompt
4. Verify model appears in `/v1/models` API endpoint
