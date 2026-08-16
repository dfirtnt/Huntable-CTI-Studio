"""API coverage for Save-time prompt validation and asset cache-busting wiring.

Both behaviors are read-only: these tests never write a workflow config version, so the
module carries no ``agent_config_mutation`` marker.

Context: a config that lost every extractor prompt ran to ``status: completed`` with zero
observables and zero rules and reported no error -- the loss was visible only in worker
logs. The validation endpoint exists so that state is refused at Save time instead.
"""

import httpx
import pytest

EXTRACTORS = [
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
    "NetworkIndicatorExtract",
]


class TestPromptValidationEndpoint:
    """POST /api/workflow/config/prompts/validate"""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_missing_extractor_prompts_are_reported(self, async_client: httpx.AsyncClient):
        """The exact config shape that produced a silent zero-rule execution."""
        response = await async_client.post(
            "/api/workflow/config/prompts/validate",
            json={"agent_prompts": {"ExtractAgentSettings": {"disabled_agents": []}}},
        )

        assert response.status_code == 200
        warnings = response.json()["warnings"]
        assert len(warnings) == len(EXTRACTORS)
        for agent in EXTRACTORS:
            assert any(agent in w for w in warnings), f"{agent} not reported"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_disabled_extractors_produce_no_warnings(self, async_client: httpx.AsyncClient):
        """A deliberately disabled extractor is not a defect and must not block Save."""
        response = await async_client.post(
            "/api/workflow/config/prompts/validate",
            json={"agent_prompts": {"ExtractAgentSettings": {"disabled_agents": EXTRACTORS}}},
        )

        assert response.status_code == 200
        assert response.json()["warnings"] == []

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_empty_prompt_body_is_reported(self, async_client: httpx.AsyncClient):
        """RankAgent/SigmaAgent were persisted as empty records, not missing keys."""
        payload = {
            "agent_prompts": {"ExtractAgentSettings": {"disabled_agents": EXTRACTORS}, "SigmaAgent": {"prompt": ""}}
        }

        response = await async_client.post("/api/workflow/config/prompts/validate", json=payload)

        assert response.status_code == 200
        assert any("empty" in w for w in response.json()["warnings"])

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_malformed_payload_does_not_500(self, async_client: httpx.AsyncClient):
        """Validation is advisory; it must degrade to a warning rather than an error."""
        response = await async_client.post(
            "/api/workflow/config/prompts/validate",
            json={"agent_prompts": "not-an-object"},
        )

        assert response.status_code == 200
        assert response.json()["warnings"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_route_is_not_shadowed_by_the_agent_name_routes(self, async_client: httpx.AsyncClient):
        """`validate` must not be parsed as an {agent_name} path parameter."""
        response = await async_client.post("/api/workflow/config/prompts/validate", json={"agent_prompts": {}})

        assert response.status_code == 200
        assert "warnings" in response.json()


class TestAssetCacheBustingWiring:
    """asset_url is a Jinja global: if registration is lost, every page fails to render."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_page_emits_versioned_asset_urls(self, async_client: httpx.AsyncClient):
        """workflow.html carries 6 of the 12 asset_url references and no other API coverage."""
        response = await async_client.get("/workflow")

        assert response.status_code == 200
        assert "/static/js/workflow/config.js?v=" in response.text
        # An unrendered global would leave the literal call in the markup.
        assert "asset_url(" not in response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_no_page_serves_a_stale_hardcoded_token(self, async_client: httpx.AsyncClient):
        """The old tokens were fixed dates that only changed when a human edited them."""
        response = await async_client.get("/workflow")

        assert "?v=20260729" not in response.text
        assert "?v=20260804" not in response.text
