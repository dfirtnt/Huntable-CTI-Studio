#!/usr/bin/env python3
"""Regenerate config/attack_technique_platforms.json from MITRE ATT&CK (Phase C).

This is the "import the maintained taxonomy" mechanism: instead of hand-maintaining
technique -> platform mappings, pull MITRE's authoritative ``x_mitre_platforms`` tags
and write the platform-DISCRIMINATIVE subset (Phase A scope: windows/linux/macos).

Requires network access (downloads the ATT&CK Enterprise STIX bundle, ~35 MB). Run it
when you want full coverage; the committed file is otherwise a curated seed.

Usage:
    python scripts/build_attack_platform_map.py            # download + write
    python scripts/build_attack_platform_map.py --dry-run  # print summary only

A (sub-)technique is kept only when its windows/linux/macos subset is non-empty and
NOT all three (all-three == no platform signal, so it is dropped).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# Official ATT&CK STIX (versioned bundle tracks the current release).
ATTACK_STIX_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
)

OUT_PATH = Path(__file__).resolve().parents[1] / "config" / "attack_technique_platforms.json"

_PLATFORM_MAP = {"windows": "windows", "linux": "linux", "macos": "macos"}
_SCOPE = ("windows", "linux", "macos")


def _fetch_stix(url: str) -> dict:
    print(f"Downloading ATT&CK STIX from {url} ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 (trusted MITRE URL)
        return json.loads(resp.read().decode("utf-8"))


def build_map(bundle: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern" or obj.get("revoked") or obj.get("x_mitre_deprecated"):
            continue
        tid = None
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack" and ref.get("external_id", "").startswith("T"):
                tid = ref["external_id"]
                break
        if not tid:
            continue
        platforms = [_PLATFORM_MAP[p.lower()] for p in obj.get("x_mitre_platforms", []) if p.lower() in _PLATFORM_MAP]
        platforms = sorted(set(platforms), key=_SCOPE.index)
        # Keep only platform-DISCRIMINATIVE techniques (1 or 2 of the 3 in scope).
        if platforms and len(platforms) < len(_SCOPE):
            out[tid] = platforms
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print summary; do not write the file")
    parser.add_argument("--url", default=ATTACK_STIX_URL, help="override the STIX bundle URL")
    args = parser.parse_args()

    bundle = _fetch_stix(args.url)
    mapping = build_map(bundle)
    version = next(
        (o.get("x_mitre_version") for o in bundle.get("objects", []) if o.get("type") == "x-mitre-collection"),
        "unknown",
    )
    print(f"Discriminative techniques: {len(mapping)} (ATT&CK collection version {version})", file=sys.stderr)

    if args.dry_run:
        print(json.dumps({"count": len(mapping), "sample": dict(list(mapping.items())[:10])}, indent=2))
        return 0

    payload = {
        "_note": (
            "ATT&CK (sub-)technique -> platform signal (Phase C). AUTO-GENERATED from MITRE "
            "x_mitre_platforms; platform-discriminative (windows/linux/macos) entries only. "
            "Regenerate via scripts/build_attack_platform_map.py."
        ),
        "_source": f"mitre_attack_stix:{version}",
        "techniques": dict(sorted(mapping.items())),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(mapping)} techniques to {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
