"""
CLI wrapper for Sigma semantic similarity. Exit 0 when a structured result is returned.
Non-zero only for unrecoverable errors (file/parse, UnknownTelemetryClassError, UnsupportedSigmaFeatureError).
"""

import json
import sys
from pathlib import Path

import yaml
from sigma_similarity.errors import (
    UnknownTelemetryClassError,
    UnsupportedSigmaFeatureError,
)
from sigma_similarity.similarity_engine import compare_rules


def _load_rule(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid rule YAML: {path}")
    return data


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: sigma-similarity <rule1.yaml> <rule2.yaml>", file=sys.stderr)
        return 2
    path_a = Path(sys.argv[1])
    path_b = Path(sys.argv[2])
    if not path_a.exists():
        print(f"File not found: {path_a}", file=sys.stderr)
        return 1
    if not path_b.exists():
        print(f"File not found: {path_b}", file=sys.stderr)
        return 1
    try:
        rule_a = _load_rule(path_a)
        rule_b = _load_rule(path_b)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    try:
        result = compare_rules(rule_a, rule_b)
    except (UnknownTelemetryClassError, UnsupportedSigmaFeatureError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    # DeterministicExpansionLimitError is converted to result by engine; we never see it here.
    out = result.to_dict()
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
