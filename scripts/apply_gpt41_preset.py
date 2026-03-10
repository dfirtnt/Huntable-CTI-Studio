#!/usr/bin/env python3
"""
Apply the GPT 4.1 preset to workflow config via API.

Thin wrapper around apply_preset.py for the OpenAI GPT 4.1 preset.
For other presets (Anthropic, Gemini, LMStudio), use:
  python3 scripts/apply_preset.py <path-to-preset.json>

Usage:
  python3 scripts/apply_gpt41_preset.py [--base-url http://localhost:8001]
"""

import sys
from pathlib import Path

PRESET_PATH = (
    Path(__file__).resolve().parent.parent
    / "config/presets/AgentConfigs/quickstart/Quickstart-openai-gpt-4.1-mini.json"
)

if __name__ == "__main__":
    # Inject preset path and re-run apply_preset
    sys.argv = [sys.argv[0], str(PRESET_PATH)] + [a for a in sys.argv[1:] if a != str(PRESET_PATH)]
    import runpy

    runpy.run_path(Path(__file__).resolve().parent / "apply_preset.py", run_name="__main__")
