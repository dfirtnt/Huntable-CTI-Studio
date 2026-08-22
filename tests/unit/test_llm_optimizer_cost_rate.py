"""Regression tests for the GPT-4o cost-rate constants in llm_optimizer.

Prior to this fix, the input rate ($5.00/1M) and output rate ($15.00/1M) were
hardcoded as float literals in six separate spots across llm_optimizer.py plus
one more in src/web/routes/debug.py -- both stale relative to OpenAI's current
published pricing ($2.50/1M input, $10.00/1M output, verified against
https://developers.openai.com/api/docs/models/gpt-4o) and free to drift apart
from each other. These tests pin the corrected values and prove every call
site now reads from the single shared constant instead of a local literal.
"""

import ast
from pathlib import Path

from src.utils.llm_optimizer import (
    GPT4O_INPUT_COST_PER_MILLION_TOKENS,
    GPT4O_OUTPUT_COST_PER_MILLION_TOKENS,
    llm_optimizer,
)

LLM_OPTIMIZER_SRC = Path("src/utils/llm_optimizer.py")
DEBUG_ROUTE_SRC = Path("src/web/routes/debug.py")

# The stale literals this fix removed. If either reappears as a bare float in
# either file, someone reintroduced a hardcoded rate instead of using the
# shared constants.
STALE_RATE_LITERALS = {5.0, 15.0}


def test_gpt4o_rate_constants_match_current_openai_pricing() -> None:
    """Pin the corrected rates so a future edit can't silently drift them."""
    assert GPT4O_INPUT_COST_PER_MILLION_TOKENS == 2.50
    assert GPT4O_OUTPUT_COST_PER_MILLION_TOKENS == 10.00


def test_get_cost_estimate_computes_from_the_shared_constants() -> None:
    """The public cost-estimate API must derive its dollar figures from the
    module constants, not from independent arithmetic that happens to agree.
    """
    # use_filtering=False takes the pure-math path (no ContentFilter/model
    # load required): input_tokens = len(content)//4, prompt_tokens = 1508,
    # max_output_tokens = 2000 are all fixed by get_cost_estimate itself.
    content = "x" * 4000  # -> 1000 input tokens
    result = llm_optimizer.get_cost_estimate(content, use_filtering=False)

    total_input_tokens = 1000 + 1508
    expected_input_cost = (total_input_tokens / 1_000_000) * GPT4O_INPUT_COST_PER_MILLION_TOKENS
    expected_output_cost = (2000 / 1_000_000) * GPT4O_OUTPUT_COST_PER_MILLION_TOKENS

    assert result["input_cost"] == expected_input_cost
    assert result["output_cost"] == expected_output_cost
    assert result["total_cost"] == expected_input_cost + expected_output_cost

    # Regression check against the pre-fix literals: at the old $5.00/$15.00
    # rates these totals would have been exactly double.
    stale_input_cost = (total_input_tokens / 1_000_000) * 5.00
    stale_output_cost = (2000 / 1_000_000) * 15.00
    assert result["input_cost"] != stale_input_cost
    assert result["output_cost"] != stale_output_cost


def _float_literals(tree: ast.Module) -> set[float]:
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)}


def test_no_stale_hardcoded_gpt4o_rate_remains_in_llm_optimizer() -> None:
    """Structural guard: fail if a $5.00/$15.00-shaped literal reappears.

    This is what actually enforces "exactly one definition of the rate exists
    in the codebase" -- a future edit that reverts to `* 5.00` inline would
    pass a hand-picked unit test but not this scan.
    """
    tree = ast.parse(LLM_OPTIMIZER_SRC.read_text(encoding="utf-8"))
    found = _float_literals(tree) & STALE_RATE_LITERALS
    assert not found, f"Stale hardcoded GPT-4o rate literal(s) reintroduced in {LLM_OPTIMIZER_SRC}: {found}"


def test_no_stale_hardcoded_gpt4o_rate_remains_in_debug_route() -> None:
    tree = ast.parse(DEBUG_ROUTE_SRC.read_text(encoding="utf-8"))
    found = _float_literals(tree) & STALE_RATE_LITERALS
    assert not found, f"Stale hardcoded GPT-4o rate literal(s) reintroduced in {DEBUG_ROUTE_SRC}: {found}"


def test_debug_route_imports_the_shared_constant_not_a_local_copy() -> None:
    """debug.py must import GPT4O_INPUT_COST_PER_MILLION_TOKENS from
    llm_optimizer rather than defining its own -- otherwise the two modules
    can drift apart exactly as they did before this fix.
    """
    tree = ast.parse(DEBUG_ROUTE_SRC.read_text(encoding="utf-8"))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.utils.llm_optimizer":
            imported_names.update(alias.name for alias in node.names)

    assert "GPT4O_INPUT_COST_PER_MILLION_TOKENS" in imported_names

    # And it must not also assign its own module-level constant of that shape.
    assigned_names = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "GPT4O_INPUT_COST_PER_MILLION_TOKENS" not in assigned_names
