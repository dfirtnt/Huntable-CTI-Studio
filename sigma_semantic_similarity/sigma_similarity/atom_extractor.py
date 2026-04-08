"""
Extract positive and negative atoms from DNF.
Atom identity: field|operator|modifier_chain|normalized_value.
Modifier order preserved; backslash normalization deterministic; FIELD_ALIAS_MAP static.
"""

from sigma_similarity.ast_builder import AtomNode

# Static, versioned. Unknown field -> normalize lowercase, keep as-is.
# Keys are stored in their canonical Sigma PascalCase form.
FIELD_ALIAS_MAP: dict[str, str] = {
    "CommandLine": "process.command_line",
    "Image": "process.image",
    "ProcessPath": "process.image",
    "ParentImage": "process.parent_image",
    "ProcessCommandLine": "process.command_line",
    "ParentCommandLine": "process.parent_command_line",
}

# Case-insensitive lookup table built once at import time.
# Handles LLM-generated rules that use lowercase/snake_case field names
# (e.g. 'image', 'command_line', 'parent_image') alongside standard PascalCase.
_FIELD_ALIAS_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in FIELD_ALIAS_MAP.items()}
# Also add common snake_case variants that LLMs produce
_FIELD_ALIAS_MAP_LOWER.update(
    {
        "command_line": "process.command_line",
        "image": "process.image",
        "parent_image": "process.parent_image",
        "parent_command_line": "process.parent_command_line",
        "process_path": "process.image",
        "process_command_line": "process.command_line",
    }
)


def _normalize_value(value: object, case_insensitive: bool = False) -> str:
    """Deterministic value normalization. Backslash normalization; regex vs literal preserved.

    Args:
        value: Raw detection value.
        case_insensitive: If True, lowercase string values. Sigma's contains/endswith/startswith
            modifiers are case-insensitive by default, so atom identities must fold case to avoid
            treating 'Delete' and 'delete' as different behavioral atoms.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        # Backslash normalization: deterministic (e.g. normalize to single backslash for path)
        s = value.strip()
        # Preserve re vs literal: we don't change pattern content; just canonicalize backslashes
        s = s.replace("\\\\", "\x00").replace("\\", "/").replace("\x00", "\\\\")
        if case_insensitive:
            s = s.lower()
        return s
    return str(value)


def _resolve_field(field: str) -> str:
    """Resolve field via FIELD_ALIAS_MAP (case-insensitive); unknown -> lowercase as-is."""
    # Fast path: exact match (covers standard PascalCase Sigma fields)
    if field in FIELD_ALIAS_MAP:
        return FIELD_ALIAS_MAP[field]
    # Case-insensitive + snake_case fallback (covers LLM-generated rules)
    resolved = _FIELD_ALIAS_MAP_LOWER.get(field.lower())
    if resolved is not None:
        return resolved
    return field.lower()


# Sigma modifiers that perform case-insensitive matching by default.
# Values for these operators must be lowercased in atom identity so that
# 'Delete' and 'delete' produce the same atom.
_CASE_INSENSITIVE_OPS = frozenset({"contains", "endswith", "startswith", "eq"})


def atom_identity(node: AtomNode) -> str:
    """Canonical atom identity: field|operator|modifier_chain|normalized_value."""
    field = _resolve_field(node.field)
    op = node.operator.lower()
    mod = node.modifier_chain  # order preserved
    # Sigma string matching is case-insensitive by default (contains, endswith, startswith, eq).
    # Only regex ('re') preserves case in its pattern.
    ci = op in _CASE_INSENSITIVE_OPS
    val = _normalize_value(node.value, case_insensitive=ci)
    return f"{field}|{op}|{mod}|{val}"


def extract_positive_atoms(dnf_branches: list[list[tuple[bool, AtomNode]]]) -> set[str]:
    """Extract positive atoms from DNF as sorted set of identity strings."""
    out: set[str] = set()
    for branch in dnf_branches:
        for is_negated, atom in branch:
            if not is_negated:
                out.add(atom_identity(atom))
    return set(sorted(out))


def extract_negative_atoms(dnf_branches: list[list[tuple[bool, AtomNode]]]) -> set[str]:
    """Extract negative atoms only when under AND NOT (branch has at least one positive literal).
    Ignore NOT under OR (branch that is only NOTs)."""
    out: set[str] = set()
    for branch in dnf_branches:
        has_positive = any(not is_negated for is_negated, _ in branch)
        if not has_positive:
            continue
        for is_negated, atom in branch:
            if is_negated:
                out.add(atom_identity(atom))
    return set(sorted(out))
