"""API tests for the eval metrics endpoints used by the SYS.04 trend chart
and the model filter on the v1 eval page (agent_evals.html SYS.03).

Covers:
- /subagent-eval-aggregate response shape (precision/recall/F1/scored_articles fields)
- ?model=... query param shape (filter is accepted; result is well-formed)
- /subagent-eval-models response shape
- /config-versions-models agent_models key structure (used by the JS model filter)
"""

import httpx
import pytest


@pytest.mark.api
@pytest.mark.asyncio
async def test_aggregate_response_includes_item_level_fields(async_client: httpx.AsyncClient):
    """Every aggregate row must expose the four new item-level fields, regardless
    of whether item-level scoring data exists for that config version (null is allowed)."""
    response = await async_client.get("/api/evaluations/subagent-eval-aggregate?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    assert data.get("subagent") == "cmdline"
    assert isinstance(data.get("aggregates"), list)

    new_fields = {"mean_precision", "mean_recall", "mean_f1", "scored_articles"}
    for agg in data["aggregates"]:
        missing = new_fields - set(agg.keys())
        assert not missing, f"Aggregate row missing fields: {missing}"
        # scored_articles is always an int (0 when no annotated articles).
        assert isinstance(agg["scored_articles"], int)
        # P/R/F1 are floats in [0, 1] when populated, or null when no scoring.
        for key in ("mean_precision", "mean_recall", "mean_f1"):
            v = agg[key]
            assert v is None or (isinstance(v, (int, float)) and 0.0 <= v <= 1.0)


@pytest.mark.api
@pytest.mark.asyncio
async def test_aggregate_exposes_eval_set_total(async_client: httpx.AsyncClient):
    """eval_set_total is the canonical count of articles in config/eval_articles.yaml
    for the subagent. The MAE chart (agent_evals.html renderMAEChart) compares it to
    per-version total_articles to flag versions where the user ran a subset.

    Contract: present, non-negative int. Present even when the model-filter early-return
    triggers and aggregates is empty, since the canonical count doesn't depend on data.
    """
    response = await async_client.get("/api/evaluations/subagent-eval-aggregate?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    assert "eval_set_total" in data, "Aggregate response missing eval_set_total"
    assert isinstance(data["eval_set_total"], int)
    assert data["eval_set_total"] >= 0

    # Also present on the unknown-model early-return path
    empty = await async_client.get(
        "/api/evaluations/subagent-eval-aggregate?subagent=cmdline&model=this-model-does-not-exist-anywhere"
    )
    assert empty.status_code == 200
    empty_data = empty.json()
    assert "eval_set_total" in empty_data
    assert isinstance(empty_data["eval_set_total"], int)


@pytest.mark.api
@pytest.mark.asyncio
async def test_aggregate_accepts_model_filter(async_client: httpx.AsyncClient):
    """The ?model= filter is accepted without 4xx and returns the same response
    shape (filtered to versions where the subagent used that model)."""
    response = await async_client.get("/api/evaluations/subagent-eval-aggregate?subagent=cmdline&model=gpt-4o-mini")
    assert response.status_code == 200
    data = response.json()
    assert data.get("subagent") == "cmdline"
    assert isinstance(data.get("aggregates"), list)


@pytest.mark.api
@pytest.mark.asyncio
async def test_aggregate_unknown_model_returns_empty(async_client: httpx.AsyncClient):
    """Unknown model shouldn't error -- it should return an empty aggregates list
    so the chart can render an empty state."""
    response = await async_client.get(
        "/api/evaluations/subagent-eval-aggregate?subagent=cmdline&model=this-model-does-not-exist-anywhere"
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("aggregates") == []
    assert data.get("total_config_versions") == 0


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_models_response_shape(async_client: httpx.AsyncClient):
    """/subagent-eval-models returns {subagent, models: [{name, config_count}]}."""
    response = await async_client.get("/api/evaluations/subagent-eval-models?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    assert data.get("subagent") == "cmdline"
    assert isinstance(data.get("models"), list)
    for entry in data["models"]:
        assert "name" in entry
        assert "config_count" in entry
        assert isinstance(entry["name"], str)
        assert isinstance(entry["config_count"], int)
        assert entry["config_count"] >= 1


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_models_requires_subagent(async_client: httpx.AsyncClient):
    """Missing subagent param should be a 422 (FastAPI Query validation)."""
    response = await async_client.get("/api/evaluations/subagent-eval-models")
    assert response.status_code == 422


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_models_unknown_subagent_returns_empty(
    async_client: httpx.AsyncClient,
):
    """Unknown subagent (not in _SUBAGENT_TO_BUNDLE_AGENT) should return empty
    models list rather than erroring -- matches discover-on-failure UX."""
    response = await async_client.get("/api/evaluations/subagent-eval-models?subagent=not_a_real_subagent")
    assert response.status_code == 200
    data = response.json()
    assert data.get("models") == []


# ---------------------------------------------------------------------------
# config-versions-models -- contract for the v1 model filter
# ---------------------------------------------------------------------------
# The JS model filter in agent_evals.html reads:
#   modelsByVersion[version].agent_models["{AgentName}_model"]
# to decide which config versions used a given model.
# These tests verify the response structure stays stable so the filter
# doesn't silently break if the endpoint changes.

_AGENT_MODEL_KEYS = {
    "cmdline": "CmdlineExtract_model",
    "process_lineage": "ProcTreeExtract_model",
    "hunt_queries": "HuntQueriesExtract_model",
    "registry_artifacts": "RegistryExtract_model",
    "windows_services": "ServicesExtract_model",
    "scheduled_tasks": "ScheduledTasksExtract_model",
}


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_versions_models_response_shape(async_client: httpx.AsyncClient):
    """models_by_version maps version -> {agent_models, display_text}."""
    # Use version 1 which always exists (may have empty agent_models for old configs)
    response = await async_client.get("/api/evaluations/config-versions-models?config_versions=1")
    assert response.status_code == 200
    data = response.json()
    assert "models_by_version" in data
    mbv = data["models_by_version"]
    assert isinstance(mbv, dict)
    for version_key, payload in mbv.items():
        assert "agent_models" in payload, f"version {version_key} missing agent_models"
        assert "display_text" in payload, f"version {version_key} missing display_text"
        assert isinstance(payload["agent_models"], dict)


@pytest.mark.api
@pytest.mark.asyncio
async def test_config_versions_models_agent_model_keys_for_recent_version(
    async_client: httpx.AsyncClient,
):
    """For any version that has model config, agent_models must contain the
    {AgentName}_model keys that the JS filter uses to match selected models.

    We fetch all versions from the subagent-eval-models list and sample the
    most recent one -- it should have a populated agent_models dict.
    """
    # Get a version that definitely has eval data and model config
    models_resp = await async_client.get("/api/evaluations/subagent-eval-models?subagent=cmdline")
    assert models_resp.status_code == 200
    models_data = models_resp.json()
    if not models_data.get("models"):
        pytest.skip("No eval model data in DB -- cannot validate agent_models key shape")

    # Fetch a recent aggregate to get a real config version
    agg_resp = await async_client.get("/api/evaluations/subagent-eval-aggregate?subagent=cmdline")
    assert agg_resp.status_code == 200
    aggregates = agg_resp.json().get("aggregates", [])
    if not aggregates:
        pytest.skip("No aggregate data -- cannot resolve a config version to inspect")

    recent_version = max(
        (a["config_version"] for a in aggregates if a.get("config_version")),
        default=None,
    )
    if recent_version is None:
        pytest.skip("No config_version found in aggregates")

    versions_resp = await async_client.get(f"/api/evaluations/config-versions-models?config_versions={recent_version}")
    assert versions_resp.status_code == 200
    mbv = versions_resp.json().get("models_by_version", {})

    # The version key may be a string in JSON even if we passed an int
    payload = mbv.get(str(recent_version)) or mbv.get(recent_version)
    assert payload is not None, f"Version {recent_version} not in models_by_version response"
    agent_models = payload.get("agent_models", {})
    # At least one {AgentName}_model key must be present for the filter to work
    model_keys_present = [k for k in agent_models if k.endswith("_model")]
    assert model_keys_present, (
        f"Version {recent_version} agent_models has no '*_model' keys -- "
        f"JS filter will always produce an empty result set. Keys found: {list(agent_models)}"
    )
    # Specifically the cmdline key must be present (we queried cmdline subagent)
    expected_key = _AGENT_MODEL_KEYS["cmdline"]
    assert expected_key in agent_models, (
        f"Version {recent_version} agent_models missing '{expected_key}'. Keys present: {list(agent_models)}"
    )
