"""Ratchet test for the routes -> service layering contract.

Route modules under ``src/web/routes`` must not reach into ``src.database`` directly:
they take a session via ``Depends(get_db_session)`` (or ``session_scope()`` for work
that outlives the request) and delegate data access to services.

``UNMIGRATED_ROUTE_MODULES`` is the pre-existing backlog. It is a ratchet: entries come
off as modules are migrated, and nothing may be added. A module that is migrated and
then regresses fails ``test_no_new_direct_database_imports``; a module that is migrated
but left in the list fails ``test_allowlist_has_no_stale_entries``, so the list cannot
silently rot.

Tracked by the "Interpose a service layer between routes and the DB (+ session DI)"
task. See ``src/web/routes/ml_hunt_comparison.py`` for the reference implementation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROUTES_DIR = Path(__file__).resolve().parents[2] / "src" / "web" / "routes"

# Modules that still import src.database directly. DO NOT ADD TO THIS LIST.
UNMIGRATED_ROUTE_MODULES = {
    "actions.py",
    "ai.py",
    "analytics.py",
    "annotations.py",
    "articles.py",
    "audit.py",
    "dashboard.py",
    "debug.py",
    "embeddings.py",
    "evaluation.py",
    "evaluation_api.py",
    "evaluation_ui.py",
    "export.py",
    "feedback.py",
    "health.py",
    "metrics.py",
    "models.py",
    "observable_evaluation.py",
    "pages.py",
    "pdf.py",
    "scheduled_jobs.py",
    "scrape.py",
    "search.py",
    "settings.py",
    "sigma_ab_test.py",
    "sigma_queue.py",
    "sigma_similarity_test.py",
    "sources.py",
    "workflow_config.py",
    "workflow_executions.py",
}


def _route_modules() -> list[Path]:
    return sorted(p for p in ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


def _imports_database(path: Path) -> bool:
    """True if the module imports from ``src.database`` anywhere, including inside functions.

    Walks the AST rather than grepping so comments and docstrings mentioning
    ``src.database`` do not count, and so the 566 in-function imports used across the
    web layer to dodge import cycles are still caught.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "src.database" or node.module.startswith("src.database.")):
                return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.database" or alias.name.startswith("src.database."):
                    return True
    return False


@pytest.mark.parametrize("module", _route_modules(), ids=lambda p: p.name)
def test_no_new_direct_database_imports(module: Path) -> None:
    """Migrated route modules must not import src.database."""
    if module.name in UNMIGRATED_ROUTE_MODULES:
        pytest.skip(f"{module.name} is on the known-unmigrated allowlist")

    assert not _imports_database(module), (
        f"{module.name} imports src.database directly. Route handlers should take "
        "`session: Session = Depends(get_db_session)` and delegate to a service; "
        "background work should use `session_scope()`. Both live in src.web.dependencies. "
        "See src/web/routes/ml_hunt_comparison.py for the pattern."
    )


def test_allowlist_has_no_stale_entries() -> None:
    """Every allowlisted module must still actually import src.database.

    Keeps the ratchet honest: once a module is migrated its entry must be deleted,
    otherwise the allowlist would keep shielding it from the check above.
    """
    stale = sorted(
        module.name
        for module in _route_modules()
        if module.name in UNMIGRATED_ROUTE_MODULES and not _imports_database(module)
    )
    assert not stale, (
        f"These route modules no longer import src.database and must be removed from UNMIGRATED_ROUTE_MODULES: {stale}"
    )


def test_allowlist_references_existing_modules() -> None:
    """Allowlist entries must correspond to real files (catches renames/deletions)."""
    existing = {module.name for module in _route_modules()}
    missing = sorted(UNMIGRATED_ROUTE_MODULES - existing)
    assert not missing, f"UNMIGRATED_ROUTE_MODULES names files that no longer exist: {missing}"
