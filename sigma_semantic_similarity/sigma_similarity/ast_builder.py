"""
Build explicit AST from normalized detection tree.
Tree of AND/OR/NOT and leaf atoms (field, operator, modifier_chain, value).
Deterministic ordering of children; no semantic simplification (DNF does that).
"""

from typing import Any


class ASTNode:
    """Base for AST nodes."""

    pass


class AndNode(ASTNode):
    __slots__ = ("children",)

    def __init__(self, children: list[ASTNode]):
        self.children = tuple(children)

    def __repr__(self):
        return f"AndNode({list(self.children)})"


class OrNode(ASTNode):
    __slots__ = ("children",)

    def __init__(self, children: list[ASTNode]):
        self.children = tuple(children)

    def __repr__(self):
        return f"OrNode({list(self.children)})"


class NotNode(ASTNode):
    __slots__ = ("child",)

    def __init__(self, child: ASTNode):
        self.child = child

    def __repr__(self):
        return f"NotNode({self.child})"


class AtomNode(ASTNode):
    """Leaf: field + operator + modifier_chain + value. Value normalized later in atom_extractor."""

    __slots__ = ("field", "operator", "modifier_chain", "value")

    def __init__(self, field: str, operator: str, modifier_chain: str, value: Any):
        self.field = field
        self.operator = operator
        self.modifier_chain = modifier_chain
        self.value = value

    def __repr__(self):
        return f"AtomNode({self.field!r}, {self.operator!r}, {self.modifier_chain!r}, {self.value!r})"


def _parse_field_spec(key: str) -> tuple[str, str, str]:
    """Parse detection key like 'Image', 'CommandLine|contains', 'CommandLine|re|i'.
    Returns (field, operator, modifier_chain). Modifier chain is pipe-separated after field.
    """
    parts = key.split("|")
    field = parts[0] if parts else ""
    if len(parts) <= 1:
        return (field, "eq", "")
    # Sigma: field|modifier or field|modifier|modifier. Operator can be contains, endswith, startswith, re, eq, lt, gt, etc.
    modifier_parts = parts[1:]
    operator = "eq"
    for p in modifier_parts:
        low = p.lower()
        if low in ("contains", "endswith", "startswith", "re", "eq", "lt", "gt", "lte", "gte", "neq"):
            operator = low
            break
    modifier_chain = "|".join(modifier_parts)
    return (field, operator, modifier_chain)


def _dict_to_atoms(block: dict[str, Any]) -> list[ASTNode]:
    """Convert a selection block to list of ASTNodes. List values: |all -> AND (separate atoms), else OR."""
    nodes: list[ASTNode] = []
    for key in sorted(block.keys()):
        value = block[key]
        field, operator, modifier_chain = _parse_field_spec(key)
        use_all = "all" in modifier_chain.lower().split("|")
        if isinstance(value, list):
            atom_list = [AtomNode(field, operator, modifier_chain, v) for v in value]
            if not atom_list:
                continue
            if use_all:
                nodes.extend(atom_list)
            else:
                nodes.append(OrNode(atom_list) if len(atom_list) > 1 else atom_list[0])
        else:
            nodes.append(AtomNode(field, operator, modifier_chain, value))
    return nodes


def _selection_to_ast(selection: list[dict]) -> ASTNode:
    """selection is list of dicts (OR of blocks per Sigma: list -> OR). Each block AND of atoms."""
    if not selection:
        return AndNode([])  # empty AND for empty selection
    if len(selection) == 1:
        nodes = _dict_to_atoms(selection[0])
        if len(nodes) <= 1:
            return nodes[0] if nodes else AndNode([])
        return AndNode(nodes)
    # Multiple blocks: OR of ANDs
    branches = []
    for block in selection:
        nodes = _dict_to_atoms(block)
        if nodes:
            branches.append(AndNode(nodes) if len(nodes) > 1 else nodes[0])
    if not branches:
        return AndNode([])
    return OrNode(branches) if len(branches) > 1 else branches[0]


def _normalized_to_ast(normalized: Any) -> ASTNode:
    """Convert normalized tree (from detection_normalizer) to AST. Deterministic sort."""
    if isinstance(normalized, dict):
        if "and" in normalized:
            children = [_normalized_to_ast(x) for x in normalized["and"]]
            return AndNode(children)
        if "or" in normalized:
            children = [_normalized_to_ast(x) for x in normalized["or"]]
            return OrNode(children)
        if "not" in normalized:
            return NotNode(_normalized_to_ast(normalized["not"]))
        if "selection" in normalized:
            return _selection_to_ast(normalized["selection"])
    return AndNode([])


def build_ast(normalized_detection: dict[str, Any]) -> ASTNode:
    """Build AST from normalized detection tree. Stable structure; canonical sort of children."""
    return _normalized_to_ast(normalized_detection)


def ast_to_snapshot_string(node: ASTNode) -> str:
    """Serialize AST to stable string for snapshot tests. Deterministic order."""
    if isinstance(node, AndNode):
        parts = sorted(ast_to_snapshot_string(c) for c in node.children)
        return "AND(" + ",".join(parts) + ")"
    if isinstance(node, OrNode):
        parts = sorted(ast_to_snapshot_string(c) for c in node.children)
        return "OR(" + ",".join(parts) + ")"
    if isinstance(node, NotNode):
        return "NOT(" + ast_to_snapshot_string(node.child) + ")"
    if isinstance(node, AtomNode):
        val = node.value
        if isinstance(val, str):
            val = val.replace("\\", "\\\\").replace(")", "\\)")
        return f"ATOM({node.field}={val})"
    return "?"
