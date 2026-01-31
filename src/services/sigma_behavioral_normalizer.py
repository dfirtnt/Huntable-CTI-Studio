"""
SIGMA Behavioral Core Normalizer.

Extracts normalized behavioral selectors from SIGMA rules and generates
SHA256 fingerprints for comparison and stability testing.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class BehavioralCore:
    """Normalized behavioral core extracted from SIGMA rule."""

    behavior_selectors: list[str]
    commandlines: list[str]
    process_chains: list[str]
    core_hash: str
    selector_count: int


class SigmaBehavioralNormalizer:
    """
    Normalizes SIGMA rules to extract behavioral core for comparison.

    Extracts:
    - Normalized commandlines
    - Normalized process chains
    - Normalized selections/conditions
    """

    def __init__(self):
        """Initialize normalizer."""
        # Patterns for normalization
        self.wildcard_pattern = re.compile(r"\*+")
        self.whitespace_pattern = re.compile(r"\s+")

    def extract_behavioral_core(self, rule_yaml: str) -> BehavioralCore:
        """
        Extract normalized behavioral core from SIGMA rule.

        Args:
            rule_yaml: YAML string containing SIGMA rule

        Returns:
            BehavioralCore with normalized selectors and hash
        """
        try:
            rule_data = yaml.safe_load(rule_yaml)
        except Exception as e:
            logger.error(f"Failed to parse rule YAML: {e}")
            return BehavioralCore([], [], [], "", 0)

        if not rule_data or not isinstance(rule_data, dict):
            return BehavioralCore([], [], [], "", 0)

        detection = rule_data.get("detection", {})
        if not isinstance(detection, dict):
            return BehavioralCore([], [], [], "", 0)

        # Extract all selectors
        behavior_selectors = []
        commandlines = []
        process_chains = []

        # Get all selection blocks
        for key, value in detection.items():
            if key in ["condition", "timeframe"]:
                continue

            if isinstance(value, dict):
                # Extract field-based selectors
                selectors = self._extract_selectors_from_dict(value, key)
                behavior_selectors.extend(selectors)

                # Extract commandlines
                cmd_selectors = self._extract_commandlines(value)
                commandlines.extend(cmd_selectors)

                # Extract process chains
                chain_selectors = self._extract_process_chains(value)
                process_chains.extend(chain_selectors)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        selectors = self._extract_selectors_from_dict(item, key)
                        behavior_selectors.extend(selectors)
                        cmd_selectors = self._extract_commandlines(item)
                        commandlines.extend(cmd_selectors)
                        chain_selectors = self._extract_process_chains(item)
                        process_chains.extend(chain_selectors)

        # Normalize all selectors
        normalized_selectors = [self._normalize_selector(s) for s in behavior_selectors]
        normalized_commandlines = [self._normalize_commandline(c) for c in commandlines]
        normalized_chains = [self._normalize_process_chain(c) for c in process_chains]

        # Remove duplicates while preserving order
        seen = set()
        unique_selectors = []
        for sel in normalized_selectors:
            if sel not in seen:
                seen.add(sel)
                unique_selectors.append(sel)

        # Generate hash from sorted selectors
        sorted_selectors = sorted(unique_selectors)
        core_hash = self._generate_hash(sorted_selectors)

        return BehavioralCore(
            behavior_selectors=unique_selectors,
            commandlines=normalized_commandlines,
            process_chains=normalized_chains,
            core_hash=core_hash,
            selector_count=len(unique_selectors),
        )

    def _extract_selectors_from_dict(self, d: dict, context: str = "") -> list[str]:
        """Extract selector strings from a dictionary."""
        selectors = []

        for key, value in d.items():
            if isinstance(value, str):
                # Format: "field=value" or "field|contains: value"
                selector = f"{key}={value}"
                selectors.append(selector)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        selector = f"{key}={item}"
                        selectors.append(selector)
                    elif isinstance(item, dict):
                        # Nested structure
                        nested = self._extract_selectors_from_dict(item, f"{context}.{key}")
                        selectors.extend(nested)
            elif isinstance(value, dict):
                # Nested structure
                nested = self._extract_selectors_from_dict(value, f"{context}.{key}")
                selectors.extend(nested)

        return selectors

    def _extract_commandlines(self, d: dict) -> list[str]:
        """Extract commandline-related selectors."""
        commandlines = []

        for key, value in d.items():
            key_lower = key.lower()
            if "commandline" in key_lower or "command" in key_lower:
                if isinstance(value, str):
                    commandlines.append(value)
                elif isinstance(value, list):
                    commandlines.extend([v for v in value if isinstance(v, str)])
            elif isinstance(value, dict):
                nested = self._extract_commandlines(value)
                commandlines.extend(nested)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        nested = self._extract_commandlines(item)
                        commandlines.extend(nested)

        return commandlines

    def _extract_process_chains(self, d: dict) -> list[str]:
        """Extract process chain information (Image, ParentImage combinations)."""
        chains = []

        image = None
        parent_image = None

        for key, value in d.items():
            key_lower = key.lower()
            if "image" in key_lower and "parent" not in key_lower:
                if isinstance(value, str):
                    image = value
            elif "parentimage" in key_lower or "parent_image" in key_lower:
                if isinstance(value, str):
                    parent_image = value

        if image:
            if parent_image:
                chains.append(f"{parent_image} -> {image}")
            else:
                chains.append(image)

        # Recursively check nested structures
        for key, value in d.items():
            if isinstance(value, dict):
                nested = self._extract_process_chains(value)
                chains.extend(nested)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        nested = self._extract_process_chains(item)
                        chains.extend(nested)

        return chains

    def _normalize_selector(self, selector: str) -> str:
        """Normalize a selector string for comparison."""
        # Convert to lowercase
        normalized = selector.lower()

        # Normalize wildcards (* -> *)
        normalized = self.wildcard_pattern.sub("*", normalized)

        # Normalize whitespace
        normalized = self.whitespace_pattern.sub(" ", normalized)

        # Remove leading/trailing whitespace
        normalized = normalized.strip()

        return normalized

    def _normalize_commandline(self, cmdline: str) -> str:
        """Normalize a commandline for comparison."""
        # Convert to lowercase
        normalized = cmdline.lower()

        # Normalize whitespace
        normalized = self.whitespace_pattern.sub(" ", normalized)

        # Remove quotes
        normalized = normalized.replace('"', "").replace("'", "")

        # Normalize wildcards
        normalized = self.wildcard_pattern.sub("*", normalized)

        # Remove leading/trailing whitespace
        normalized = normalized.strip()

        return normalized

    def _normalize_process_chain(self, chain: str) -> str:
        """Normalize a process chain for comparison."""
        # Convert to lowercase
        normalized = chain.lower()

        # Normalize path separators
        normalized = normalized.replace("\\", "/")

        # Normalize whitespace
        normalized = self.whitespace_pattern.sub(" ", normalized)

        # Remove leading/trailing whitespace
        normalized = normalized.strip()

        return normalized

    def _generate_hash(self, selectors: list[str]) -> str:
        """Generate SHA256 hash from sorted selectors."""
        # Create a canonical string representation
        canonical = "\n".join(selectors)

        # Generate hash
        hash_obj = hashlib.sha256(canonical.encode("utf-8"))
        return f"sha256:{hash_obj.hexdigest()}"

    def compare_cores(self, core1: BehavioralCore, core2: BehavioralCore) -> dict[str, Any]:
        """
        Compare two behavioral cores.

        Returns:
            Dictionary with comparison metrics
        """
        set1 = set(core1.behavior_selectors)
        set2 = set(core2.behavior_selectors)

        common = set1 & set2
        only_in_1 = set1 - set2
        only_in_2 = set2 - set1

        similarity = len(common) / max(len(set1), len(set2), 1)

        return {
            "similarity": similarity,
            "common_selectors": len(common),
            "only_in_first": len(only_in_1),
            "only_in_second": len(only_in_2),
            "hash_match": core1.core_hash == core2.core_hash,
            "selector_count_diff": abs(core1.selector_count - core2.selector_count),
        }
