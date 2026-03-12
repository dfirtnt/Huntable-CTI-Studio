"""
Surface score = number of DNF branches. Invariant: >= 1 for valid rules; empty DNF raises.
"""

from sigma_similarity.ast_builder import ASTNode
from sigma_similarity.errors import UnsupportedSigmaFeatureError

# Lazy import to avoid cycle
def _get_dnf(ast: ASTNode):
    from sigma_similarity.dnf_normalizer import ast_to_dnf
    return ast_to_dnf(ast)


def surface_score_from_dnf(dnf_branches: list) -> float:
    """Surface score = number of DNF branches. Returns float (integer value).
    For valid rules, surface_score >= 1. If branches empty, raise."""
    n = len(dnf_branches)
    if n == 0:
        raise UnsupportedSigmaFeatureError("DNF has no branches (malformed or empty rule)")
    return float(n)


def surface_score_from_ast(ast: ASTNode) -> float:
    """Compute surface score from AST (builds DNF internally). Use when DNF already built elsewhere."""
    dnf = _get_dnf(ast)
    return surface_score_from_dnf(dnf)
