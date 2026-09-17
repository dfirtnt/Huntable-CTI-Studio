#!/usr/bin/env python3
"""Regenerate config/attack_taxonomy.json from the MITRE ATT&CK STIX bundles.

The Sigma validator (``src/services/sigma_validator.py``) checks every ``attack.*`` tag
against this file so a rule citing a non-existent, revoked, or deprecated ATT&CK ID fails
validation with an actionable error instead of being silently accepted. The file is the
cached taxonomy: validation never touches the network.

Refresh cadence: MITRE ships ATT&CK releases roughly twice a year (spring/autumn). Re-run
this script when a release lands and commit the regenerated file, exactly as for
``scripts/build_attack_platform_map.py``. It is deliberately an operator-run batch step
rather than a scheduled worker job -- the output is a committed config artifact, and a
worker writing into the bind-mounted ``config/`` tree would leave the checkout dirty.

Requires network access (downloads ~65 MB across the Enterprise, Mobile, and ICS bundles)
unless ``--from-dir`` points at already-downloaded ``<domain>.json`` files.

Usage:
    python scripts/build_attack_taxonomy.py                 # download + write
    python scripts/build_attack_taxonomy.py --dry-run       # print summary only
    python scripts/build_attack_taxonomy.py --from-dir DIR  # use DIR/<domain>.json bundles

Output shape (one object per line for diff-friendly regeneration):
    {
      "_source": "mitre_attack_stix:19.2",
      "_domains": {"enterprise-attack": "19.2", ...},
      "tactics": ["collection", "command-and-control", ...],
      "objects": {
        "T1059.001": {"name": "PowerShell", "kind": "sub-technique", "status": "active",
                      "domains": ["enterprise"]},
        "T1086": {"name": "PowerShell", "kind": "technique", "status": "revoked",
                  "replaced_by": "T1059.001", "domains": ["enterprise"]},
        ...
      }
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # imported as scripts.build_attack_taxonomy (tests) or run directly from scripts/
    from scripts.build_attack_platform_map import _collection_version, _fetch_stix
except ImportError:  # pragma: no cover - direct execution path
    from build_attack_platform_map import _collection_version, _fetch_stix

STIX_BASE_URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master"

# Domain slug -> label written into each object's ``domains`` list.
DOMAINS = {
    "enterprise-attack": "enterprise",
    "mobile-attack": "mobile",
    "ics-attack": "ics",
}

OUT_PATH = Path(__file__).resolve().parents[1] / "config" / "attack_taxonomy.json"

# STIX object type -> (ATT&CK ID prefix, kind label). Only these carry IDs that Sigma
# ``attack.*`` tags can reference. Data sources, analytics, detection strategies and
# assets are intentionally excluded.
_TYPE_SPEC: dict[str, tuple[str, str]] = {
    "attack-pattern": ("T", "technique"),
    "x-mitre-tactic": ("TA", "tactic"),
    "intrusion-set": ("G", "group"),
    "malware": ("S", "software"),
    "tool": ("S", "software"),
    "course-of-action": ("M", "mitigation"),
    "campaign": ("C", "campaign"),
}

_MITRE_SOURCE_NAMES = {"mitre-attack", "mitre-mobile-attack", "mitre-ics-attack"}

# Status precedence when the same ID appears in several domains: an ID that is still
# active anywhere is active; otherwise revoked beats deprecated.
_STATUS_RANK = {"active": 0, "revoked": 1, "deprecated": 2}


def _attack_id(obj: dict, prefix: str) -> str | None:
    """Return the object's ATT&CK external ID if it carries the expected prefix."""
    for ref in obj.get("external_references", []):
        if ref.get("source_name") not in _MITRE_SOURCE_NAMES:
            continue
        ext = str(ref.get("external_id", ""))
        if not ext.startswith(prefix):
            continue
        # "T" must not swallow "TA" tactic IDs.
        if prefix == "T" and ext.startswith("TA"):
            continue
        return ext
    return None


def _status(obj: dict) -> str:
    if obj.get("revoked"):
        return "revoked"
    if obj.get("x_mitre_deprecated"):
        return "deprecated"
    return "active"


def _kind(obj: dict, base_kind: str) -> str:
    if base_kind == "technique" and obj.get("x_mitre_is_subtechnique"):
        return "sub-technique"
    return base_kind


def build_taxonomy(bundles: dict[str, dict]) -> dict:
    """Pure transform: {domain_slug: stix_bundle} -> taxonomy payload (without ``_note``).

    Merges IDs across domains. ``replaced_by`` is derived from ``revoked-by``
    relationships and points at the ATT&CK ID of the replacement object.
    """
    objects: dict[str, dict] = {}
    tactics: set[str] = set()
    domain_versions: dict[str, str] = {}

    for slug, bundle in bundles.items():
        label = DOMAINS.get(slug, slug)
        domain_versions[slug] = _collection_version(bundle)
        stix_objects = bundle.get("objects", [])

        # stix id -> attack id, for resolving revoked-by relationships in this bundle.
        stix_to_attack: dict[str, str] = {}
        for obj in stix_objects:
            spec = _TYPE_SPEC.get(obj.get("type", ""))
            if spec is None:
                continue
            prefix, base_kind = spec
            attack_id = _attack_id(obj, prefix)
            if attack_id is None:
                continue
            stix_to_attack[obj["id"]] = attack_id

            status = _status(obj)
            entry = {
                "name": str(obj.get("name", "")),
                "kind": _kind(obj, base_kind),
                "status": status,
                "domains": [label],
            }
            if base_kind == "tactic":
                shortname = obj.get("x_mitre_shortname")
                if shortname:
                    entry["shortname"] = str(shortname)
                    if status == "active":
                        tactics.add(str(shortname))

            existing = objects.get(attack_id)
            if existing is None:
                objects[attack_id] = entry
            else:
                if label not in existing["domains"]:
                    existing["domains"].append(label)
                if _STATUS_RANK[status] < _STATUS_RANK[existing["status"]]:
                    # Keep the healthier status (and its name) as the canonical record.
                    existing.update({"name": entry["name"], "kind": entry["kind"], "status": status})
                    existing.pop("replaced_by", None)

        for obj in stix_objects:
            if obj.get("type") != "relationship" or obj.get("relationship_type") != "revoked-by":
                continue
            source = stix_to_attack.get(obj.get("source_ref", ""))
            target = stix_to_attack.get(obj.get("target_ref", ""))
            if not source or not target or source == target:
                continue
            record = objects.get(source)
            if record is not None and record["status"] == "revoked" and "replaced_by" not in record:
                record["replaced_by"] = target

    versions = sorted({v for v in domain_versions.values() if v != "unknown"})
    source_version = versions[-1] if versions else "unknown"

    return {
        "_source": f"mitre_attack_stix:{source_version}",
        "_domains": dict(sorted(domain_versions.items())),
        "tactics": sorted(tactics),
        "objects": dict(sorted(objects.items())),
    }


def render_taxonomy(payload: dict) -> str:
    """Serialize with one object per line so regeneration diffs stay reviewable."""
    lines = ["{"]
    lines.append(f'  "_note": {json.dumps(payload["_note"])},')
    lines.append(f'  "_source": {json.dumps(payload["_source"])},')
    lines.append(f'  "_domains": {json.dumps(payload["_domains"], sort_keys=True)},')
    lines.append(f'  "tactics": {json.dumps(payload["tactics"])},')
    lines.append('  "objects": {')
    items = list(payload["objects"].items())
    for i, (attack_id, entry) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"    {json.dumps(attack_id)}: {json.dumps(entry, ensure_ascii=True)}{comma}")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _load_bundles(from_dir: str | None, base_url: str) -> dict[str, dict]:
    bundles: dict[str, dict] = {}
    for slug in DOMAINS:
        if from_dir:
            path = Path(from_dir) / f"{slug}.json"
            print(f"Reading {path} ...", file=sys.stderr)
            bundles[slug] = json.loads(path.read_text(encoding="utf-8"))
        else:
            bundles[slug] = _fetch_stix(f"{base_url}/{slug}/{slug}.json")
    return bundles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print summary; do not write the file")
    parser.add_argument("--from-dir", default=None, help="directory holding <domain>.json bundles (skips download)")
    parser.add_argument("--base-url", default=STIX_BASE_URL, help="override the attack-stix-data base URL")
    args = parser.parse_args()

    payload = build_taxonomy(_load_bundles(args.from_dir, args.base_url))
    objects = payload["objects"]
    by_status: dict[str, int] = {}
    for entry in objects.values():
        by_status[entry["status"]] = by_status.get(entry["status"], 0) + 1
    print(
        f"ATT&CK objects: {len(objects)} {by_status}; tactics: {len(payload['tactics'])}; "
        f"source {payload['_source']} domains {payload['_domains']}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(json.dumps({"count": len(objects), "by_status": by_status, "tactics": payload["tactics"]}, indent=2))
        return 0

    payload = {
        "_note": (
            "MITRE ATT&CK taxonomy for Sigma tag validation. AUTO-GENERATED from the "
            "attack-stix-data Enterprise/Mobile/ICS bundles; regenerate via "
            "scripts/build_attack_taxonomy.py when MITRE ships a new ATT&CK release."
        ),
        **payload,
    }
    OUT_PATH.write_text(render_taxonomy(payload), encoding="utf-8")
    print(f"Wrote {len(objects)} objects to {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
