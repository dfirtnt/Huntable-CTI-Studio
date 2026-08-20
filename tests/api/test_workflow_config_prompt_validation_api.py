"""API coverage for Save-time prompt validation and asset cache-busting wiring.

The validation and cache-busting tests are read-only and carry no marker. The
Save-rejection class is marked ``agent_config_mutation``: a rejected PUT commits nothing,
but it is still a PUT /api/workflow/config, and against a dev app running code without
the server-side refusal it would be accepted and would rewrite the live config.

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


@pytest.mark.agent_config_mutation
class TestSaveIsRefusedServerSide:
    """PUT /api/workflow/config

    The pre-flight endpoint above is advisory: the browser shows a confirm with a "Save
    Anyway" button and swallows its own failures, so a config that loses every extractor
    prompt could still be persisted. These tests pin the server-side refusal, which is
    the only gate a script, a stale tab, or a dismissed dialog cannot walk past.
    """

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_save_that_drops_every_extractor_prompt_is_rejected(self, async_client: httpx.AsyncClient):
        """An explicit null removes a prompt from the merged config -- the shape that wiped them.

        A merely absent key is preserved by ``_merge_agent_prompts``, so removal is the
        only payload that can leave an enabled extractor with nothing to run.
        """
        response = await async_client.put(
            "/api/workflow/config",
            json={
                "agent_prompts": {
                    **{agent: None for agent in EXTRACTORS},
                    "ExtractAgentSettings": {"disabled_agents": []},
                }
            },
        )

        assert response.status_code == 400
        detail = response.json()["detail"]
        assert detail["override_field"] == "allow_prompt_warnings"
        for agent in EXTRACTORS:
            assert any(agent in w for w in detail["warnings"]), f"{agent} not reported"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_save_with_an_empty_prompt_body_is_rejected(self, async_client: httpx.AsyncClient):
        """An empty string is the shape the expanded prompt editor actually persisted."""
        response = await async_client.put(
            "/api/workflow/config",
            json={
                "agent_prompts": {
                    "ExtractAgentSettings": {"disabled_agents": EXTRACTORS},
                    "SigmaAgent": {"prompt": ""},
                }
            },
        )

        assert response.status_code == 400
        warnings = response.json()["detail"]["warnings"]
        assert any("SigmaAgent" in w and "empty" in w for w in warnings)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rejection_does_not_persist_a_new_version(self, async_client: httpx.AsyncClient):
        """A refused Save must leave the active config untouched, not half-applied."""
        before = (await async_client.get("/api/workflow/config")).json()

        rejected = await async_client.put(
            "/api/workflow/config",
            json={
                "agent_prompts": {
                    **{agent: None for agent in EXTRACTORS},
                    "ExtractAgentSettings": {"disabled_agents": []},
                }
            },
        )
        assert rejected.status_code == 400

        after = (await async_client.get("/api/workflow/config")).json()
        assert after["version"] == before["version"]
        assert after["agent_prompts"] == before["agent_prompts"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_settings_only_autosave_is_not_blocked(self, async_client: httpx.AsyncClient):
        """A disabled_agents toggle is not a prompt edit and must not be refused.

        Guards the narrowing: an earlier version of this check rejected the partial
        autosave payload used by the no-active-row recovery path.
        """
        response = await async_client.put(
            "/api/workflow/config",
            json={"agent_prompts": {"ExtractAgentSettings": {"disabled_agents": []}}},
        )

        assert response.status_code != 400, response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_a_disabled_rank_agent_with_no_prompt_does_not_block(self, async_client: httpx.AsyncClient):
        """A switched-off agent never runs, so its empty prompt is not a runtime defect.

        Found on the live config: RankAgent was disabled and carried an empty prompt, which
        would otherwise have refused every prompt-touching save until the operator clicked
        through the override.
        """
        response = await async_client.put(
            "/api/workflow/config",
            json={
                "rank_agent_enabled": False,
                "agent_prompts": {
                    "ExtractAgentSettings": {"disabled_agents": EXTRACTORS},
                    "RankAgent": {"prompt": ""},
                },
            },
        )

        assert response.status_code != 400, response.text
