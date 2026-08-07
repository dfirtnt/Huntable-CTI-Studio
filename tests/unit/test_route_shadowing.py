"""No registered route may be unreachable because an earlier route swallows it.

FastAPI matches routes in registration order, so a literal path declared after a
same-shape parameterized one never runs. `/api/articles/search` was dead this
way for months: `articles.router` declares `/api/articles/{article_id}` and is
included before `search.router`, so the literal string "search" was parsed as an
article id and every request 422'd.

Ordering inside one router is easy to eyeball; ordering *across* routers is not,
because it depends on the `include_router` sequence in `routes/__init__.py`. This
test resolves every registered path against the real router and fails if the
winner is not the route that declared it.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from starlette.routing import Match

pytestmark = pytest.mark.unit


def _app():
    from src.web.modern_main import app

    return app


def _concrete_path(route: APIRoute) -> str | None:
    """A request path that must reach this route, or None if it takes parameters.

    Routes with path parameters are skipped as *targets* — they are the potential
    shadowers, not the victims. Only fully literal paths have one obvious
    request path to test.
    """
    return None if "{" in route.path else route.path


def _first_match(app, method: str, path: str):
    """The route Starlette would actually dispatch to.

    Only FULL matches count. A PARTIAL match means the path matched but the
    method did not; Starlette falls back to those only to raise 405, so treating
    them as winners would flag every route that shares a path with a sibling
    declared under a different verb.
    """
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "root_path": "",
        "headers": [],
        "query_string": b"",
    }
    for route in app.routes:
        match, _ = route.matches(scope)
        if match is Match.FULL:
            return route
    return None


def test_no_literal_route_is_shadowed_by_an_earlier_route():
    app = _app()
    shadowed: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = _concrete_path(route)
        if path is None:
            continue
        for method in sorted(route.methods or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            winner = _first_match(app, method, path)
            winner_path = getattr(winner, "path", None)
            if winner_path != route.path:
                shadowed.append(f"{method} {path} (declared by {route.name}) is served by {winner_path}")

    assert not shadowed, "Literal routes swallowed by an earlier parameterized route:\n" + "\n".join(shadowed)


def test_articles_search_specifically_resolves_to_the_search_handler():
    """The original instance, pinned by name so a regression is unambiguous."""
    winner = _first_match(_app(), "GET", "/api/articles/search")

    assert winner is not None
    assert getattr(winner, "name", None) == "api_search_articles"
