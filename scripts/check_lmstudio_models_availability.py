#!/usr/bin/env python3
"""Check availability of LMStudio models."""

import asyncio
import json

import httpx

LMSTUDIO_URL = "http://localhost:1234/v1"

MODELS_TO_CHECK = [
    "deepseek-r1-qwen3-8b",
    "llama-3-13b-instruct",
    "qwen2.5-14b-coder",
    "qwen2.5-coder-32b",
    "mixtral-8x7b-instruct",
    "qwen/qwen3-next-80b",
]


async def check_model_availability(model_name: str) -> dict:
    """Check if a model is available in LMStudio."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Try a simple completion request
            response = await client.post(
                f"{LMSTUDIO_URL}/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10,
                    "temperature": 0,
                },
            )

            if response.status_code == 200:
                return {"model": model_name, "available": True, "status": "✅ Available"}
            error_text = response.text[:200]
            return {
                "model": model_name,
                "available": False,
                "status": f"❌ Error {response.status_code}",
                "error": error_text,
            }
        except httpx.TimeoutException:
            return {"model": model_name, "available": False, "status": "❌ Timeout"}
        except httpx.ConnectError:
            return {"model": model_name, "available": False, "status": "❌ Cannot connect to LMStudio (is it running?)"}
        except Exception as e:
            return {"model": model_name, "available": False, "status": f"❌ Error: {str(e)[:100]}"}


async def main():
    """Check all models."""
    print("=" * 80)
    print("LMStudio Model Availability Check")
    print("=" * 80)
    print(f"\nChecking {len(MODELS_TO_CHECK)} models...")
    print(f"LMStudio URL: {LMSTUDIO_URL}\n")

    results = []

    for model in MODELS_TO_CHECK:
        print(f"Checking: {model}...", end=" ", flush=True)
        result = await check_model_availability(model)
        results.append(result)
        print(result["status"])
        await asyncio.sleep(1)  # Brief pause between checks

    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    available = [r for r in results if r["available"]]
    unavailable = [r for r in results if not r["available"]]

    print(f"\n✅ Available ({len(available)}/{len(MODELS_TO_CHECK)}):")
    for r in available:
        print(f"   {r['model']}")

    if unavailable:
        print(f"\n❌ Unavailable ({len(unavailable)}/{len(MODELS_TO_CHECK)}):")
        for r in unavailable:
            print(f"   {r['model']}: {r['status']}")
            if "error" in r:
                print(f"      {r['error']}")

    print()

    # Save results
    with open("lmstudio_model_availability.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Results saved to: lmstudio_model_availability.json")


if __name__ == "__main__":
    asyncio.run(main())
