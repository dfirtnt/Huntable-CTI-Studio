"""Pre-submit checks that mirror the Huntable-SIGMA-Rules CI ``Validate`` workflow.

A queued rule is published byte-for-byte, so these checks read the raw YAML and never
clean, repair, or rewrite it. They cover the CI steps a rule can fail on its own:

* yamllint ``key-duplicates`` (PyYAML silently keeps the last duplicate key, which drops
  a detection condition);
* pySigma parse and condition errors (``sigma check --fail-on-error``);
* the blocking validator set (``sigma check --validation-config .sigma/validation-blocking.yml``),
  read from the destination repository's own file so the gate follows CI, with the bundled
  mirror as the fallback.

Not covered here: the cross-rule duplicate-detection script and yamllint style rules.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import yaml

from src.services.sigma_validator import (
    PYSIGMA_AVAILABLE,
    SIGMAHQ_BLOCKING_CONFIG_PATH,
    run_sigmahq_blocking_validators,
)

if PYSIGMA_AVAILABLE:
    from sigma.collection import SigmaCollection

logger = logging.getLogger(__name__)

DESTINATION_BLOCKING_CONFIG = Path(".sigma") / "validation-blocking.yml"
DESTINATION_REQUIREMENTS = Path("requirements-ci.txt")


@dataclass(frozen=True)
class CiParityFinding:
    """One reason the destination repository's CI would reject a rule."""

    check: str  # duplicate_key | parse | blocking_validator | validators_unavailable
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check, "message": self.message}


class _DuplicateKeyLoader(yaml.SafeLoader):
    """SafeLoader that records duplicate mapping keys instead of silently keeping the last."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.duplicates: list[tuple[str, int]] = []

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            try:
                key = self.construct_object(key_node, deep=True)
                hash(key)
            except (TypeError, yaml.YAMLError):
                continue
            if key in seen:
                self.duplicates.append((str(key), key_node.start_mark.line + 1))
            seen.add(key)
        return super().construct_mapping(node, deep)


def _duplicate_keys(rule_yaml: str) -> list[tuple[str, int]]:
    loader = _DuplicateKeyLoader(rule_yaml)
    try:
        while loader.check_data():
            loader.get_data()
    finally:
        loader.dispose()
    return loader.duplicates


def _compact(value: Any) -> str:
    """Readable issue detail: pySigma's logsource repr lists every unset field."""
    if all(hasattr(value, attr) for attr in ("category", "product", "service")):
        parts = [
            f"{attr}={getattr(value, attr)}" for attr in ("category", "product", "service") if getattr(value, attr)
        ]
        return "{" + ", ".join(parts) + "}"
    return str(value)


def destination_blocking_config(repo_path: Path) -> Path:
    """The destination repo's blocking config when present, else the bundled mirror."""
    candidate = Path(repo_path) / DESTINATION_BLOCKING_CONFIG
    return candidate if candidate.is_file() else SIGMAHQ_BLOCKING_CONFIG_PATH


def check_rule_ci_parity(rule_yaml: str, *, config_path: Path | None = None) -> list[CiParityFinding]:
    """Return every reason CI would reject ``rule_yaml`` (empty list means it passes)."""
    findings: list[CiParityFinding] = []

    try:
        duplicates = _duplicate_keys(rule_yaml)
    except yaml.YAMLError as exc:
        return [CiParityFinding("parse", f"Invalid YAML: {str(exc).splitlines()[0]}")]
    findings.extend(
        CiParityFinding("duplicate_key", f"Duplicate YAML key '{key}' at line {line}; only the last value is kept")
        for key, line in duplicates
    )

    if not PYSIGMA_AVAILABLE:
        return [*findings, CiParityFinding("validators_unavailable", "pySigma is not installed")]

    try:
        collection = SigmaCollection.from_yaml(rule_yaml)
        for sigma_rule in collection.rules:
            for condition in sigma_rule.detection.parsed_condition:
                _ = condition.parsed
    except Exception as exc:
        return [*findings, CiParityFinding("parse", f"pySigma {type(exc).__name__}: {exc}")]

    result = run_sigmahq_blocking_validators(
        list(collection.rules), config_path=config_path, exempt_pipeline_metadata=False
    )
    if not result["available"]:
        findings.append(
            CiParityFinding("validators_unavailable", f"Blocking validators could not run: {result['reason']}")
        )
    for issue in result["issues"]:
        details = ", ".join(f"{key}={_compact(value)}" for key, value in issue["details"].items())
        suffix = f" ({details})" if details else ""
        findings.append(CiParityFinding("blocking_validator", f"{issue['issue']}: {issue['description']}{suffix}"))
    return findings


_PIN = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#;]+)")


def toolchain_drift(repo_path: Path) -> list[dict[str, str]]:
    """Packages pinned in the destination's ``requirements-ci.txt`` that differ from this app.

    Informational: a different pySigma than CI can change what the validators report.
    Pins for packages this app does not install (yamllint, sigma-cli) are skipped.
    """
    requirements = Path(repo_path) / DESTINATION_REQUIREMENTS
    if not requirements.is_file():
        return []
    drift: list[dict[str, str]] = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = _PIN.match(line)
        if not match:
            continue
        package, pinned = match.groups()
        try:
            installed = version(package)
        except PackageNotFoundError:
            continue
        if installed != pinned:
            drift.append({"package": package, "pinned": pinned, "installed": installed})
    return drift
