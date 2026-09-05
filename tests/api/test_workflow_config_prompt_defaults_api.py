"""GET /api/workflow/config/prompts/defaults/{agent_name} serves the code-owned user template.

The Workflow Config "effective prompt" preview used to embed a hand-copied JS mirror of
sigma_generate_multi.txt, which drifted from the file the backend formats. The preview now
fetches the file through this endpoint, so the response must be byte-identical to the file.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "prompts"


@pytest.mark.api
class TestPromptDefaultsEndpoint:
    @pytest.mark.asyncio
    async def test_sigma_agent_default_matches_prompt_file(self, async_client: httpx.AsyncClient):
        response = await async_client.get("/api/workflow/config/prompts/defaults/SigmaAgent")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["agent_name"] == "SigmaAgent"
        assert data["prompt_name"] == "sigma_generate_multi"
        assert data["source_file"] == "src/prompts/sigma_generate_multi.txt"
        # PromptLoader strips surrounding whitespace before the runtime formats the template.
        assert data["user_template"] == (PROMPTS_DIR / "sigma_generate_multi.txt").read_text(encoding="utf-8").strip()
        assert "{observables_section}" in data["user_template"]
        from src.services.sigma_generation_service import DEFAULT_SIGMA_SYSTEM_PROMPT

        assert data["system_default"] == DEFAULT_SIGMA_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_agent_without_code_owned_template_is_404(self, async_client: httpx.AsyncClient):
        response = await async_client.get("/api/workflow/config/prompts/defaults/CmdlineExtract")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_defaults_path_is_not_shadowed_by_per_agent_route(self, async_client: httpx.AsyncClient):
        # /config/prompts/{agent_name} must not swallow "defaults" as an agent name.
        response = await async_client.get("/api/workflow/config/prompts/defaults/SigmaAgent")
        assert response.status_code == 200
        assert "workflow_config_version" not in response.json()
