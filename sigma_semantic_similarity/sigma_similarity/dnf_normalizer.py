"""
Normalize AST to shallow DNF: top-level OR of branches, each branch AND of atoms and NOTs.
Expand OR at top, distribute AND over OR, canonical sort. MAX_DNF_BRANCHES = 64.
"""

from sigma_similarity.ast_builder import AndNode, AtomNode, NotNode, OrNode
from sigma_similarity.errors import DeterministicExpansionLimitError

MAX_DNF_BRANCHES = 64


def _atom_key(node: AtomNode) -> tuple:
    """Canonical sort key for an AtomNode (field, operator, modifier_chain, value)."""
    v = node.value
    if isinstance(v, str):
        v = (v,)
    elif isinstance(v, (int, float, bool)):
        v = (str(type(v).__name__), str(v))
    else:
        v = (str(v),)
    return (node.field, node.operator, node.modifier_chain, *v)


def _distribute_to_dnf(node: OrNode | AndNode | NotNode | AtomNode) -> list[list[tuple[bool, AtomNode]]]:
    """Convert AST to list of DNF branches. Each branch is list of (is_negated, AtomNode).
    Raises DeterministicExpansionLimitError if more than MAX_DNF_BRANCHES branches.
    """
    if isinstance(node, AtomNode):
        return [[(False, node)]]
    if isinstance(node, NotNode):
        if isinstance(node.child, AtomNode):
            return [[(True, node.child)]]
        # NOT(OR(...)) -> AND(NOT each) - will distribute
        inner = _distribute_to_dnf(node.child)
        if not inner:
            return []
        # NOT(AND(a,b)) = OR(NOT a, NOT b) - so we need to push NOT down. Actually for DNF we want
        # OR of ANDs. NOT(AND(a,b)) = OR(NOT a, NOT b) which is two branches (NOT a) and (NOT b).
        # So we expand NOT over AND: NOT(AND(a,b)) -> OR(NOT(a), NOT(b)) -> two branches.
        if isinstance(node.child, AndNode):
            branches = []
            for c in node.child.children:
                branches.extend(_distribute_to_dnf(NotNode(c) if not isinstance(c, NotNode) else c.child))
            return branches
        if isinstance(node.child, OrNode):
            # NOT(OR(a,b)) = AND(NOT a, NOT b) -> one branch with two negated literals
            combined: list[tuple[bool, AtomNode]] = []
            for c in node.child.children:
                sub = _distribute_to_dnf(NotNode(c) if not isinstance(c, NotNode) else c.child)
                for branch in sub:
                    combined.extend(branch)
            return [combined] if combined else []
        return []
    if isinstance(node, OrNode):
        branches: list[list[tuple[bool, AtomNode]]] = []
        for c in node.children:
            branches.extend(_distribute_to_dnf(c))
        if len(branches) > MAX_DNF_BRANCHES:
            raise DeterministicExpansionLimitError(
                f"DNF expansion would produce {len(branches)} branches (max {MAX_DNF_BRANCHES})"
            )
        return branches
    if isinstance(node, AndNode):
        # AND(a, b, c): each of a,b,c is list of branches. We need cross-product (distribute).
        if not node.children:
            return []
        first = _distribute_to_dnf(node.children[0])
        for c in node.children[1:]:
            rest = _distribute_to_dnf(c)
            new_first: list[list[tuple[bool, AtomNode]]] = []
            for b1 in first:
                for b2 in rest:
                    new_first.append(b1 + b2)
            first = new_first
            if len(first) > MAX_DNF_BRANCHES:
                raise DeterministicExpansionLimitError(
                    f"DNF expansion would produce {len(first)} branches (max {MAX_DNF_BRANCHES})"
                )
        return first
    return []


def _canonicalize_branch(branch: list[tuple[bool, AtomNode]]) -> tuple[tuple[tuple[bool, AtomNode], ...], ...]:
    """Sort literals within branch by atom key; return immutable for sorting branches."""
    sorted_lits = sorted(branch, key=lambda t: (_atom_key(t[1]), t[0]))
    return tuple(sorted_lits)


def ast_to_dnf(node: OrNode | AndNode | NotNode | AtomNode) -> list[list[tuple[bool, AtomNode]]]:
    """Convert AST to DNF: list of branches, each branch list of (is_negated, AtomNode).
    Canonical sort of branches and of literals within branch. Raises if > MAX_DNF_BRANCHES.
    """
    branches = _distribute_to_dnf(node)
    if len(branches) > MAX_DNF_BRANCHES:
        raise DeterministicExpansionLimitError(
            f"DNF expansion would produce {len(branches)} branches (max {MAX_DNF_BRANCHES})"
        )
    canonical = [_canonicalize_branch(b) for b in branches]

    # Sort branches by canonical representation (tuple of (is_negated, atom_key) per literal)
    def branch_key(b: tuple) -> tuple:
        return tuple((neg, _atom_key(a)) for neg, a in b)

    canonical.sort(key=branch_key)
    return [list(b) for b in canonical]
