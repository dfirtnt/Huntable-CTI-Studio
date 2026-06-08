"""
Extract positive and negative atoms from DNF.
Atom identity: field|modifier_chain|normalized_value.
The operator is the first token of modifier_chain (an empty chain ⟺ default ``eq``),
so a separate operator slot would be redundant and is not emitted.
Modifier order preserved; backslash normalization deterministic; FIELD_ALIAS_MAP static.
"""

from sigma_similarity.ast_builder import AtomNode

# Static, versioned. Unknown field -> normalize lowercase, keep as-is.
# Keys are stored in their canonical Sigma PascalCase form.
FIELD_ALIAS_MAP: dict[str, str] = {
    # Process execution (dotted canonical, legacy)
    "CommandLine": "process.command_line",
    "Image": "process.image",
    "ProcessPath": "process.image",
    "ParentImage": "process.parent_image",
    "ProcessCommandLine": "process.command_line",
    "ParentCommandLine": "process.parent_command_line",
    # Registry events (flat lowercase canonical to match sigma_novelty_service._ATOM_FIELD_ALIAS)
    "TargetObject": "registrypath",
    "RegistryKey": "registrypath",
    "RegistryPath": "registrypath",
    "RegistryValue": "registryvalue",
    # Service creation
    "ServiceName": "servicename",
    "ServiceFileName": "serviceimagepath",
    "ImagePath": "serviceimagepath",
    "StartType": "servicestarttype",
    "ServiceType": "servicetype",
    "ServiceStartType": "servicestarttype",
    # Scheduled tasks
    "TaskName": "taskname",
    "TaskContent": "taskcontent",
}

# Case-insensitive lookup table built once at import time.
# Handles LLM-generated rules that use lowercase/snake_case field names
# (e.g. 'image', 'command_line', 'parent_image') alongside standard PascalCase.
_FIELD_ALIAS_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in FIELD_ALIAS_MAP.items()}
# Also add common snake_case variants that LLMs produce
_FIELD_ALIAS_MAP_LOWER.update(
    {
        # Process
        "command_line": "process.command_line",
        "image": "process.image",
        "parent_image": "process.parent_image",
        "parent_command_line": "process.parent_command_line",
        "process_path": "process.image",
        "process_command_line": "process.command_line",
        # Registry
        "target_object": "registrypath",
        "registry_key": "registrypath",
        "registry_path": "registrypath",
        "registry_value": "registryvalue",
        # Service
        "service_name": "servicename",
        "service_file_name": "serviceimagepath",
        "servicefile_name": "serviceimagepath",
        "image_path": "serviceimagepath",
        "start_type": "servicestarttype",
        "service_type": "servicetype",
        "service_start_type": "servicestarttype",
        # Scheduled tasks
        "task_name": "taskname",
        "task_content": "taskcontent",
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

# Operators whose value can carry leading/trailing '*' wildcards meaningfully.
# Regex ('re') and numeric ops (lt, gt, lte, gte, neq) treat '*' as a literal
# pattern character and must NEVER be folded.
_WILDCARD_FOLDABLE_OPS = frozenset({"eq", "contains", "endswith", "startswith"})


def _fold_wildcards(op: str, mod: str, val: str) -> tuple[str, str, str]:
    """Spec Item 9 (P1-B): collapse leading/trailing literal '*' in value into
    the equivalent modifier op so '*foo'-as-eq matches 'foo'-as-endswith.

    Conservative by design — only edge wildcards are folded. Internal '*'
    patterns (``foo*bar*baz``) might be literal asterisks in a path or a
    complex pattern; we don't rewrite them.

    Folding rules (mirroring scripts/mine_sigma_pair_candidates.canon_atom,
    which is the reference policy spec for this fold):

    * ``op="eq"``, val starts AND ends with ``*`` (len >= 2)
        → ``op="contains"``, mod="contains", val with both stripped
    * ``op="eq"``, val starts with ``*``
        → ``op="endswith"``, mod="endswith", val with leading stripped
    * ``op="eq"``, val ends with ``*``
        → ``op="startswith"``, mod="startswith", val with trailing stripped
    * ``op`` in {contains, endswith, startswith}, val has redundant edge ``*``
        → strip the redundant ``*``; op and mod stay unchanged

    When op flips from eq to a modifier op, modifier_chain is set to the new
    op alone so the atom identity matches what an explicit-modifier rule
    produces. When op was already a modifier, modifier_chain (which may carry
    additional tokens like ``|all`` or case-insensitivity flags) is preserved.
    """
    if op not in _WILDCARD_FOLDABLE_OPS:
        return op, mod, val

    if op == "eq":
        starts = val.startswith("*")
        ends = val.endswith("*")
        if starts and ends and len(val) >= 2:
            return "contains", "contains", val[1:-1]
        if starts:
            return "endswith", "endswith", val[1:]
        if ends:
            return "startswith", "startswith", val[:-1]
        return op, mod, val

    # contains / endswith / startswith: strip redundant edge '*'. Op and mod
    # are already aligned with the explicit-modifier form; only value changes.
    if val.startswith("*"):
        val = val[1:]
    if val.endswith("*"):
        val = val[:-1]
    return op, mod, val


def atom_identity(node: AtomNode) -> str:
    """Canonical atom identity: ``field|modifier_chain|normalized_value``.

    The operator is *not* stored as a separate slot — it is always the first
    token of ``modifier_chain`` (``modifier_chain.split("|")[0]``), and an empty
    chain denotes the default ``eq``. ``op`` is still computed locally below to
    drive case-folding and the wildcard fold; it just isn't emitted verbatim.
    """
    field = _resolve_field(node.field)
    op = node.operator.lower()
    mod = node.modifier_chain  # order preserved
    # Sigma string matching is case-insensitive by default (contains, endswith, startswith, eq).
    # The |cased modifier forces case-sensitive matching, so a cased atom must preserve
    # case in its identity — otherwise two rules hunting different literal casings of the
    # same token (a real attacker-tradecraft signal) collapse into one atom. Only regex
    # ('re') preserves case in its pattern.
    ci = op in _CASE_INSENSITIVE_OPS and "cased" not in mod.lower().split("|")
    val = _normalize_value(node.value, case_insensitive=ci)
    # Wildcard fold: collapse '*X*'-as-eq into 'X'-as-contains and similar
    # (Spec Item 9 / P1-B). Must run AFTER _normalize_value so backslashes
    # are already canonicalized and the value's edge characters are stable.
    op, mod, val = _fold_wildcards(op, mod, val)
    # 3-slot identity: the operator is recoverable as mod.split("|")[0] (empty ⟺ eq),
    # so emitting it separately would duplicate the modifier (the old "endswith|endswith"
    # display bug). Wildcard folds already realign mod to the folded op above.
    return f"{field}|{mod}|{val}"


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
