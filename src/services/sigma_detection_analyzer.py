"""
SIGMA Detection Analyzer

Provides structural and field-level analysis of SIGMA rule detection blocks
for enhanced similarity matching.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def analyze_detection_structure(detection: dict[str, Any]) -> dict[str, Any]:
    """
    Extract structural elements from detection block.

    Args:
        detection: Detection block from SIGMA rule

    Returns:
        Dictionary with structural analysis results
    """
    structure = {
        "selection_count": 0,
        "selection_keys": [],
        "max_nesting_depth": 0,
        "boolean_operators": set(),
        "modifiers": set(),
        "condition_string": "",
        "condition_unrolled": "",
    }

    if not detection or not isinstance(detection, dict):
        return structure

    # Count selection keys and extract them
    for key in detection:
        if key != "condition" and key.startswith("selection"):
            structure["selection_count"] += 1
            structure["selection_keys"].append(key)

    # Analyze condition string
    condition = detection.get("condition", "")
    if condition:
        structure["condition_string"] = str(condition)
        structure["condition_unrolled"] = unroll_logical_expression(str(condition))

        # Extract boolean operators
        operators = re.findall(r"\b(and|or|not|1 of|all of|any of)\b", str(condition).lower())
        structure["boolean_operators"] = set(operators)

    # Analyze modifiers in detection fields
    modifiers = extract_modifiers(detection)
    structure["modifiers"] = modifiers

    # Calculate nesting depth (approximate by counting parentheses pairs)
    if structure["condition_string"]:
        depth = 0
        max_depth = 0
        for char in structure["condition_string"]:
            if char == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == ")":
                depth -= 1
        structure["max_nesting_depth"] = max_depth

    return structure


def analyze_detection_fields(detection: dict[str, Any]) -> dict[str, Any]:
    """
    Extract field names and values from detection block.

    Args:
        detection: Detection block from SIGMA rule

    Returns:
        Dictionary with field analysis results
    """
    fields_analysis = {
        "field_names": [],
        "field_names_with_modifiers": [],
        "normalized_values": [],
        "high_signal_fields": [],
        "tokens": set(),
    }

    if not detection or not isinstance(detection, dict):
        return fields_analysis

    # High-signal fields that should be weighted more
    HIGH_SIGNAL_FIELDS = [
        "CommandLine",
        "ProcessCommandLine",
        "Image",
        "TargetImage",
        "RegistryKey",
        "TargetObject",
        "FileName",
        "TargetFileName",
        "ServiceName",
        "Command",
        "ImagePath",
        "OriginalFileName",
    ]

    # Extract fields from all selection blocks
    for key, value in detection.items():
        if key == "condition":
            continue

        if isinstance(value, dict):
            for field_name, field_value in value.items():
                # Extract base field name and modifiers
                base_field, modifiers = parse_field_with_modifiers(field_name)
                fields_analysis["field_names"].append(base_field)

                if modifiers:
                    fields_analysis["field_names_with_modifiers"].append(f"{base_field}|{'|'.join(modifiers)}")
                else:
                    fields_analysis["field_names_with_modifiers"].append(base_field)

                # Check if high-signal field
                if base_field in HIGH_SIGNAL_FIELDS:
                    fields_analysis["high_signal_fields"].append(base_field)

                # Normalize and extract values
                if isinstance(field_value, list):
                    for item in field_value:
                        normalized = normalize_detection_value(item)
                        if normalized:
                            fields_analysis["normalized_values"].append(normalized)
                            # Extract tokens
                            tokens = extract_tokens(normalized)
                            fields_analysis["tokens"].update(tokens)
                elif isinstance(field_value, (str, int, float)):
                    # Handle strings, integers (like EventID), and floats
                    normalized = normalize_detection_value(field_value)
                    if normalized:
                        fields_analysis["normalized_values"].append(normalized)
                        tokens = extract_tokens(normalized)
                        fields_analysis["tokens"].update(tokens)

    # Convert set to list for JSON serialization
    fields_analysis["tokens"] = list(fields_analysis["tokens"])

    return fields_analysis


def normalize_detection_value(value: Any) -> str:
    """
    Normalize detection values by replacing dynamic content with placeholders.

    Args:
        value: Field value from detection

    Returns:
        Normalized string value
    """
    if not isinstance(value, str):
        value = str(value)

    # Normalize file paths
    # Match Windows paths: C:\*, \\server\*, %SystemRoot%\*, etc.
    value = re.sub(
        r"([a-zA-Z]:\\|\\\\[^\\]+\\|%[^%]+%\\).*?(\\(?:[^\\\s]+|[*?])+)?", r"<path>", value, flags=re.IGNORECASE
    )

    # Normalize Unix paths: /usr/bin/*, /tmp/*, ~/*, etc.
    value = re.sub(r"/(?:usr|etc|var|tmp|home|opt|root|[~$])(?:/[^\s\*]+)*(?:/\*|\?)?", r"<path>", value)

    # Normalize IP addresses
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", r"<ip>", value)

    # Normalize IPv6 addresses (simplified)
    value = re.sub(r"\b([0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b", r"<ip>", value)

    # Normalize UUIDs
    value = re.sub(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", r"<uuid>", value)

    # Normalize hashes (MD5, SHA1, SHA256)
    value = re.sub(r"\b[0-9a-fA-F]{32}\b", r"<hash>", value)  # MD5
    value = re.sub(r"\b[0-9a-fA-F]{40}\b", r"<hash>", value)  # SHA1
    value = re.sub(r"\b[0-9a-fA-F]{64}\b", r"<hash>", value)  # SHA256

    return value


def extract_modifiers(detection: dict[str, Any]) -> set[str]:
    """
    Extract all modifiers used in detection fields.

    Args:
        detection: Detection block from SIGMA rule

    Returns:
        Set of modifier strings (e.g., 'contains', 're', 'base64offset')
    """
    modifiers = set()

    if not detection or not isinstance(detection, dict):
        return modifiers

    for key, value in detection.items():
        if key == "condition":
            continue

        if isinstance(value, dict):
            for field_name in value.keys():
                # Parse field name with modifiers: "CommandLine|contains|all"
                _, field_modifiers = parse_field_with_modifiers(field_name)
                modifiers.update(field_modifiers)

    return modifiers


def parse_field_with_modifiers(field_name: str) -> tuple[str, list[str]]:
    """
    Parse field name to extract base field and modifiers.

    Args:
        field_name: Field name potentially with modifiers (e.g., "CommandLine|contains|all")

    Returns:
        Tuple of (base_field_name, list_of_modifiers)
    """
    if "|" not in field_name:
        return field_name, []

    parts = field_name.split("|")
    base_field = parts[0]
    modifiers = parts[1:] if len(parts) > 1 else []

    return base_field, modifiers


def extract_tokens(value: str) -> set[str]:
    """
    Extract meaningful tokens from normalized detection values.

    Args:
        value: Normalized field value

    Returns:
        Set of token strings
    """
    tokens = set()

    if not isinstance(value, str):
        return tokens

    # Extract command-line tokens (split by common separators)
    # Remove wildcards and special chars
    cleaned = re.sub(r'[*?|&<>"\']', " ", value)

    # Split by whitespace and common separators
    parts = re.split(r"[\s,;:/=]+", cleaned)

    for part in parts:
        part = part.strip().lower()
        # Skip empty, very short, or placeholder tokens
        if part and len(part) > 2 and not part.startswith("<") and not part.endswith(">"):
            tokens.add(part)

    return tokens


def unroll_logical_expression(condition: str) -> str:
    """
    Flatten nested logical expressions by unrolling parentheses.

    Args:
        condition: Condition string (e.g., "selection1 and (selection2 or selection3)")

    Returns:
        Flattened space-separated string (e.g., "selection1 AND selection2 OR selection3")
    """
    if not condition:
        return ""

    # Normalize whitespace
    condition = re.sub(r"\s+", " ", condition.strip())

    # Remove parentheses and normalize operators
    unrolled = condition

    # Replace common operator variations
    unrolled = re.sub(r"\b(and|&|&&)\b", "AND", unrolled, flags=re.IGNORECASE)
    unrolled = re.sub(r"\b(or|\|)\b", "OR", unrolled, flags=re.IGNORECASE)
    unrolled = re.sub(r"\b(not|!)\b", "NOT", unrolled, flags=re.IGNORECASE)

    # Remove parentheses
    unrolled = re.sub(r"[()]", " ", unrolled)

    # Normalize whitespace
    unrolled = re.sub(r"\s+", " ", unrolled).strip()

    return unrolled
