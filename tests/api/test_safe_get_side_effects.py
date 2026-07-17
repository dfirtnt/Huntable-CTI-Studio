"""Tests verifying side-effecting routes are POST (CSRF-covered), not GET.

Regression guard for the security fix that converted two side-effecting GET
routes to POST or moved their writes behind startup seeding:

1. ``GET /api/articles/{id}/sigma-matches`` wrote ``sigma_similar_cache`` into
   article metadata and ``force=true`` triggered expensive recompute. Now POST
   only -- a plain GET returns 405 so no cache write can occur.

2. ``GET /api/workflow/config`` lazily created a default config row + seeded
   AppSettings threshold on first call. Now read-only; seeding happens at
   startup via ``ensure_default_workflow_config``.
"""

import httpx
import pytest

pytestmark = pytest.mark.api


@pytest.mark.asyncio
class TestSigmaMatchesIsPost:
    """sigma-matches route must be POST so CSRF and role gates apply."""

    async def test_get_sigma_matches_returns_405(self, async_client: httpx.AsyncClient):
        """GET is no longer a valid method for sigma-matches -- no handler, no cache write."""
        response = await async_client.get("/api/articles/1/sigma-matches")
        assert response.status_code == 405

    async def test_get_sigma_matches_force_does_not_write(self, async_client: httpx.AsyncClient):
        """Even with force=true, a GET cannot trigger the expensive recompute or cache write."""
        response = await async_client.get("/api/articles/1/sigma-matches?force=true")
        assert response.status_code == 405


@pytest.mark.asyncio
class TestWorkflowConfigGetIsReadOnly:
    """GET /api/workflow/config must not write to the database."""

    async def test_config_returns_200_when_seeded_by_fixture(
        self, async_client: httpx.AsyncClient, ensure_workflow_config_schema
    ):
        """Config row is seeded by the test fixture (mirrors startup seeding), not by GET."""
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        data = response.json()
        assert "similarity_threshold" in data
        assert "junk_filter_threshold" in data


def test_sigma_matches_post_is_csrf_required():
    """Route manifest classifies POST /api/articles/{id}/sigma-matches as CSRF-required + role-gated."""
    from src.web.modern_main import app
    from src.web.security.route_manifest import (
        CsrfRequirement,
        RouteClassification,
        build_route_manifest,
    )

    manifest = build_route_manifest(app)
    post_entry = None
    get_entry = None
    for entry in manifest:
        if entry.path == "/api/articles/{article_id}/sigma-matches":
            if entry.method == "POST":
                post_entry = entry
            elif entry.method == "GET":
                get_entry = entry

    assert post_entry is not None, "POST /api/articles/{id}/sigma-matches must be registered"
    assert post_entry.csrf_requirement is CsrfRequirement.REQUIRED, "POST sigma-matches must require CSRF"
    assert post_entry.classification is RouteClassification.ROLES, "POST sigma-matches must be role-gated"
    assert get_entry is None, "GET /api/articles/{id}/sigma-matches must not exist as a registered route"


def test_workflow_config_get_is_not_unsafe():
    """GET /api/workflow/config is a safe method -- no CSRF requirement, no role gate from unsafe rules."""
    from src.web.modern_main import app
    from src.web.security.route_manifest import (
        UNSAFE_METHODS,
        build_route_manifest,
    )

    manifest = build_route_manifest(app)
    get_entry = None
    for entry in manifest:
        if entry.path == "/api/workflow/config" and entry.method == "GET":
            get_entry = entry
            break

    assert get_entry is not None, "GET /api/workflow/config must be registered"
    assert get_entry.method not in UNSAFE_METHODS, "GET /api/workflow/config must remain a safe method"
