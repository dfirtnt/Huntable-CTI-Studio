#!/usr/bin/env python3
"""List all available models in LMStudio."""

import json

import httpx

LMSTUDIO_URL = "http://localhost:1234/v1"

try:
    response = httpx.get(f"{LMSTUDIO_URL}/models", timeout=5.0)
    if response.status_code == 200:
        data = response.json()
        models = data.get("data", [])

        print("=" * 80)
        print("Available Models in LMStudio")
        print("=" * 80)
        print()

        if models:
            print(f"Found {len(models)} model(s):\n")
            for i, model in enumerate(models, 1):
                model_id = model.get("id", "unknown")
                print(f"{i}. {model_id}")
        else:
            print("No models found. Make sure models are loaded in LMStudio.")

        print()
        print("=" * 80)

        # Save to file
        with open("lmstudio_available_models.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Full model list saved to: lmstudio_available_models.json")

    else:
        print(f"Error: {response.status_code}")
        print(response.text)

except httpx.ConnectError:
    print("❌ Cannot connect to LMStudio. Is it running on http://localhost:1234?")
except Exception as e:
    print(f"Error: {e}")
