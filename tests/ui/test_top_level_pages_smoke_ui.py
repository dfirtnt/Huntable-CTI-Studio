"""
Fast smoke tests for top-level HTML pages that do not need a browser.
"""

import httpx
import pytest


@pytest.mark.asyncio
@pytest.mark.smoke
class TestTopLevelPagesSmoke:
    """Verify high-value pages render without server-side failures."""

    @pytest.mark.parametrize(
        ("path", "expected_snippets"),
        [
            ("/analytics", ("Analytics Dashboard", "Quick Overview")),
            ("/mlops", ("MLOps Control Center", "Observable Training")),
            ("/mlops/agent-evals", ("Agent Evaluations", "Configuration")),
            ("/settings", ("Settings", "Save Settings")),
            ("/diags", ("System Diagnostics & Health", "Quick Actions")),
            ("/jobs", ("Job Monitor", "Worker Status")),
            ("/pdf-upload", ("Upload PDF Report",)),
            ("/observables-training", ("Observable Extractor Training",)),
            ("/evaluations", ("Agent Evaluations", "Recent Evaluations")),
        ],
    )
    async def test_top_level_page_loads(
        self,
        async_client: httpx.AsyncClient,
        path: str,
        expected_snippets: tuple[str, ...],
    ):
        response = await async_client.get(path)

        assert response.status_code == 200, f"{path} returned {response.status_code}"
        for snippet in expected_snippets:
            assert snippet in response.text, f"{path} missing expected text: {snippet}"


@pytest.mark.asyncio
@pytest.mark.smoke
class TestWorkflowRedirectsSmoke:
    """Verify lightweight workflow helper routes keep redirecting correctly."""

    @pytest.mark.parametrize(
        ("path", "expected_location"),
        [
            ("/workflow/config", "/workflow#config"),
            ("/workflow/execution", "/workflow#executions"),
            ("/workflow/executions", "/workflow#executions"),
            ("/workflow/queue", "/workflow#queue"),
        ],
    )
    async def test_workflow_route_redirects(
        self,
        async_client: httpx.AsyncClient,
        path: str,
        expected_location: str,
    ):
        response = await async_client.get(path, follow_redirects=False)

        assert response.status_code == 302, f"{path} returned {response.status_code}"
        assert response.headers["location"] == expected_location
