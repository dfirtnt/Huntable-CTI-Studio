"""Static checks for the Sigma evals page (browser-free).

Full browser verification requires the live stack; these checks catch the
failures that are cheap to catch statically: the Jinja template must compile,
the page route must be registered, and the contract-relevant DOM hooks and API
calls the page depends on must be present.
"""

import pathlib

import pytest

_TEMPLATE = pathlib.Path(__file__).parent.parent.parent / "src" / "web" / "templates" / "sigma_evals.html"


@pytest.mark.unit
def test_template_compiles():
    from src.web.dependencies import templates

    # Raises TemplateSyntaxError on malformed Jinja.
    templates.env.get_template("sigma_evals.html")


@pytest.mark.unit
def test_route_registered():
    import src.web.routes.pages as pages

    paths = {getattr(r, "path", "") for r in pages.router.routes}
    assert "/mlops/sigma-evals" in paths


@pytest.mark.unit
def test_page_has_required_hooks():
    src = _TEMPLATE.read_text(encoding="utf-8")
    # Controls and containers the page JS wires up.
    for hook in ('id="runBtn"', 'id="resultsContainer"', 'id="articleList"', 'id="sigmaDetailModal"'):
        assert hook in src, f"missing DOM hook: {hook}"
    # API endpoints the page calls (must match evaluation_api routes).
    for endpoint in ("/sigma-eval-articles", "/run-sigma-eval", "/sigma-eval-results"):
        assert endpoint in src, f"page does not call expected endpoint: {endpoint}"


@pytest.mark.unit
def test_page_is_ascii():
    src = _TEMPLATE.read_text(encoding="utf-8")
    try:
        src.encode("ascii")
    except UnicodeEncodeError as e:
        pytest.fail(f"non-ASCII characters in sigma_evals.html: {e}")


@pytest.mark.unit
def test_uses_modal_manager_not_adhoc():
    """UI contract: modals must go through ModalManager, not ad-hoc toggles."""
    src = _TEMPLATE.read_text(encoding="utf-8")
    assert "ModalManager.open" in src and "ModalManager.close" in src
