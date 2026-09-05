"""Web routes must not import workflow-only modules.

The web image builds its venv from ``uv sync --frozen --no-default-groups``
(Dockerfile stage ``builder-web``), so the ``workflow`` dependency group --
``langgraph`` and friends -- is deliberately absent at runtime. Importing
``src.workflows.agentic_workflow`` from a web route therefore raises
``ModuleNotFoundError: No module named 'langgraph'`` inside ``cti_web`` even
though the same import resolves fine in the dev/test venv, which installs
every group. A function-level import defers the failure to the first request,
so it surfaces as a bare HTTP 500 rather than a startup crash.
"""

import ast
import importlib
import sys
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[2] / "src" / "web" / "routes"

WORKFLOW_ONLY_MODULE = "src.workflows.agentic_workflow"

# Empty on purpose: every web route is import-clean. ``trigger_stuck_executions``
# was the last holdout -- it ran the LangGraph pipeline in-process and now
# re-dispatches pending executions through Celery instead. Do not re-add entries
# here; move the shared helper into ``src/services/`` and keep the guard total.
ALLOWED_WORKFLOW_IMPORTERS: set[str] = set()


def _imports_workflow_module(source: str) -> bool:
    """True when the module imports ``src.workflows.agentic_workflow`` anywhere.

    Covers module-level and function-level (deferred) imports alike -- the
    deferred form is what turns this into a runtime 500 instead of a crash.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == WORKFLOW_ONLY_MODULE:
            return True
        if isinstance(node, ast.Import):
            if any(alias.name == WORKFLOW_ONLY_MODULE for alias in node.names):
                return True
    return False


@pytest.mark.parametrize(
    "route_file",
    sorted(p for p in ROUTES_DIR.glob("*.py") if p.name not in ALLOWED_WORKFLOW_IMPORTERS),
    ids=lambda p: p.name,
)
def test_web_route_does_not_import_agentic_workflow(route_file: Path) -> None:
    assert not _imports_workflow_module(route_file.read_text(encoding="utf-8")), (
        f"{route_file.name} imports {WORKFLOW_ONLY_MODULE}, which is unavailable in the "
        "web container (langgraph is in the 'workflow' dependency group). Move the shared "
        "helper into src/services/ instead."
    )


class _BlockLangGraph:
    """Meta-path finder that makes ``langgraph`` unimportable, as in cti_web."""

    def find_module(self, fullname, path=None):  # pragma: no cover - legacy hook
        return None

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "langgraph" or fullname.startswith("langgraph."):
            raise ModuleNotFoundError(f"No module named '{fullname}'", name=fullname)
        return


def test_summarize_rule_novelty_importable_without_langgraph() -> None:
    """The novelty summariser the queue route needs must live outside the graph module."""
    module_name = "src.services.sigma_novelty_service"
    saved = {name: mod for name, mod in sys.modules.items() if name == module_name}
    for name in saved:
        del sys.modules[name]

    blocker = _BlockLangGraph()
    sys.meta_path.insert(0, blocker)
    try:
        module = importlib.import_module(module_name)
        summarize_rule_novelty = module.summarize_rule_novelty
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)

    # Inconclusive comparator (candidates evaluated, zero behavioral matches)
    # must stay unscored rather than collapse to a confident 0.0.
    summary = summarize_rule_novelty({"matches": [], "total_candidates_evaluated": 7, "behavioral_matches_found": 0})
    assert summary["max_similarity"] is None
    assert summary["comparator_inconclusive"] is True
