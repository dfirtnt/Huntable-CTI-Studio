#!/usr/bin/env python3
"""
Normalize quickstart preset JSON files in config/presets/AgentConfigs/quickstart/.

Reads each *.json file and rewrites it with canonical key order and any missing
top-level keys (e.g. osdetection_fallback_enabled added in a later schema version).

Run from repo root: python3 scripts/build_baseline_presets.py
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRESETS_DIR = REPO_ROOT / "config" / "presets" / "AgentConfigs"
QUICKSTART_DIR = PRESETS_DIR / "quickstart"


def main() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT))

    # Update quickstart/*.json with canonical order and missing keys (e.g. osdetection_fallback_enabled)
    if QUICKSTART_DIR.is_dir():
        from src.config.workflow_config_loader import export_preset_as_canonical_v2

        for jpath in sorted(QUICKSTART_DIR.glob("*.json")):
            try:
                data = json.loads(jpath.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Warning: skip {jpath}: {e}", file=sys.stderr)
                continue
            if data.get("Version") == "2.0" or data.get("version") == "1.0" or "thresholds" in data:
                try:
                    ordered = export_preset_as_canonical_v2(data)
                    jpath.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"Updated (UI-ordered) {jpath.name}")
                except Exception as e:
                    print(f"Warning: skip {jpath.name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
