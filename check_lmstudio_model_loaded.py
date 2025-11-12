#!/usr/bin/env python3
"""Check if a specific model is loaded and ready in LMStudio."""
import httpx
import sys

MODEL_TO_CHECK = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-r1-0528-qwen3-8b"

print(f"Checking if model '{MODEL_TO_CHECK}' is loaded in LMStudio...")
print()

try:
    # Try a quick test request
    response = httpx.post(
        "http://localhost:1234/v1/chat/completions",
        json={
            "model": MODEL_TO_CHECK,
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 5,
            "temperature": 0
        },
        timeout=15.0
    )
    
    if response.status_code == 200:
        print(f"✅ Model '{MODEL_TO_CHECK}' is loaded and responding")
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"   Test response: {content}")
    else:
        error = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        error_msg = error.get("error", {}).get("message", response.text[:200])
        print(f"❌ Model not ready: {error_msg}")
        print()
        print("Action needed:")
        print(f"  1. Open LMStudio")
        print(f"  2. Load model: {MODEL_TO_CHECK}")
        print(f"  3. Wait for it to fully load")
        print(f"  4. Run this check again")
        
except httpx.TimeoutException:
    print(f"❌ Request timed out - model '{MODEL_TO_CHECK}' is likely not loaded")
    print()
    print("Action needed:")
    print(f"  1. Open LMStudio")
    print(f"  2. Load model: {MODEL_TO_CHECK}")
    print(f"  3. Wait for it to fully load")
    print(f"  4. Run this check again")
    
except httpx.ConnectError:
    print("❌ Cannot connect to LMStudio")
    print("   Make sure LMStudio is running on http://localhost:1234")
    
except Exception as e:
    print(f"❌ Error: {e}")

