"""
Extract positive and negative atoms from DNF.
Atom identity: field|operator|modifier_chain|normalized_value.
Modifier order preserved; backslash normalization deterministic; FIELD_ALIAS_MAP static.
"""

from sigma_similarity.ast_builder import AtomNode

# Static, versioned. No fuzzy matching. Unknown field -> normalize lowercase, keep as-is.
FIELD_ALIAS_MAP: dict[str, str] = {
    "CommandLine": "process.command_line",
    "Image": "process.image",
    "ProcessPath": "process.image",
    "ParentImage": "process.parent_image",
    "ProcessCommandLine": "process.command_line",
    "ParentCommandLine": "process.parent_command_line",
}


def _normalize_value(value: object) -> str:
    """Deterministic value normalization. Backslash normalization; regex vs literal preserved."""
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
        return s
    return str(value)


def _resolve_field(field: str) -> str:
    """Resolve field via FIELD_ALIAS_MAP; unknown -> lowercase as-is."""
    if field in FIELD_ALIAS_MAP:
        return FIELD_ALIAS_MAP[field]
    return field.lower()


def atom_identity(node: AtomNode) -> str:
    """Canonical atom identity: field|operator|modifier_chain|normalized_value."""
    field = _resolve_field(node.field)
    op = node.operator.lower()
    mod = node.modifier_chain  # order preserved
    val = _normalize_value(node.value)
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
