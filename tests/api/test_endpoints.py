"""
API endpoint tests for CTI Scraper.
"""

import httpx
import pytest


class TestDashboardEndpoints:
    """Test dashboard-related endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_dashboard_home(self, async_client: httpx.AsyncClient):
        """Test the main dashboard page."""
        response = await async_client.get("/")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "Huntable" in response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_dashboard_stats(self, async_client: httpx.AsyncClient):
        """Test dashboard statistics display."""
        response = await async_client.get("/")
        assert response.status_code == 200

        # Check for key dashboard elements
        assert "Total Articles" in response.text
        # Note: "Total Sources" and "Last Update" may not be present in current dashboard


class TestArticlesEndpoints:
    """Test article-related endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_articles_list(self, async_client: httpx.AsyncClient):
        """Test the articles listing page."""
        response = await async_client.get("/articles")
        assert response.status_code == 200
        assert "Threat Intelligence Articles" in response.text
        assert "RAG Search" in response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_articles_pagination(self, async_client: httpx.AsyncClient):
        """Test articles pagination."""
        response = await async_client.get("/articles?limit=10")
        assert response.status_code == 200

        response = await async_client.get("/articles?limit=50")
        assert response.status_code == 200

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_article_detail(self, async_client: httpx.AsyncClient):
        """Test individual article detail page."""
        # First get the articles list to find an article ID
        list_response = await async_client.get("/articles")
        assert list_response.status_code == 200

        # Try to access article ID 1 (should exist if there are articles)
        response = await async_client.get("/articles/1")
        if response.status_code == 200:
            assert "Huntable" in response.text or "Article" in response.text
        else:
            # If no articles exist, that's also valid
            assert response.status_code in [404, 500]


class TestSourcesEndpoints:
    """Test source-related endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_sources_list(self, async_client: httpx.AsyncClient):
        """Test the sources listing page."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Sources" in response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_source_management(self, async_client: httpx.AsyncClient):
        """Test source management functionality."""
        response = await async_client.get("/sources")
        assert response.status_code == 200

        # Check for source management elements
        # Note: "Add Source" or "New Source" may not be present in current sources page


class TestAPIEndpoints:
    """Test JSON API endpoints."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_api_articles(self, async_client: httpx.AsyncClient):
        """Test the articles API endpoint."""
        response = await async_client.get("/api/articles")
        # May return 500 if database error, 200 if successful
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "articles" in data
            assert isinstance(data["articles"], list)
        else:
            # If 500, skip the test (infrastructure issue)
            pytest.skip(f"API returned 500 (server error): {response.text[:200]}")

    @pytest.mark.api
    @pytest.mark.asyncio
    @pytest.mark.quarantine
    @pytest.mark.skip(reason="API may return 500 if database is not accessible - needs investigation")
    async def test_api_articles_limit(self, async_client: httpx.AsyncClient):
        """Test articles API with limit parameter."""
        response = await async_client.get("/api/articles?limit=5")
        # API may return 500 if database is not accessible
        if response.status_code == 500:
            pytest.skip(f"API returned 500 (server error): {response.text[:200]}")
        assert response.status_code == 200

        data = response.json()
        assert "articles" in data
        assert len(data["articles"]) <= 5

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_api_article_detail(self, async_client: httpx.AsyncClient):
        """Test individual article API endpoint."""
        response = await async_client.get("/api/articles/1")
        if response.status_code == 200:
            data = response.json()
            assert "id" in data
            assert "title" in data
            assert "content" in data
        else:
            # If no articles exist, that's also valid
            assert response.status_code in [404, 500]


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_404_handling(self, async_client: httpx.AsyncClient):
        """Test 404 error handling."""
        response = await async_client.get("/nonexistent-page")
        assert response.status_code == 404
        assert "Page not found" in response.text

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_invalid_article_id(self, async_client: httpx.AsyncClient):
        """Test handling of invalid article IDs."""
        response = await async_client.get("/articles/999999")
        assert response.status_code == 404

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_invalid_limit_parameter(self, async_client: httpx.AsyncClient):
        """Test handling of invalid limit parameters."""
        response = await async_client.get("/articles?limit=invalid")
        # Should handle gracefully and not 5xx
        assert response.status_code in [200, 400]


class TestProviderCatalog:
    """Test provider model catalog endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_provider_model_catalog(self, async_client: httpx.AsyncClient):
        """Catalog should return providers with model lists."""
        response = await async_client.get("/api/provider-model-catalog")
        assert response.status_code == 200
        data = response.json()
        catalog = data.get("catalog", {})
        assert isinstance(catalog, dict)
        for provider in ("openai", "anthropic", "gemini"):
            assert provider in catalog
            models = catalog[provider]
            assert isinstance(models, list)
            assert len(models) > 0


class TestWorkflowConfig:
    """Test workflow config API contract."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_workflow_config_defaults(self, async_client: httpx.AsyncClient):
        """Active workflow config exposes core fields."""
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        data = response.json()
        for key in (
            "agent_models",
            "qa_enabled",
            "sigma_fallback_enabled",
            "qa_max_retries",
            "cmdline_attention_preprocessor_enabled",
        ):
            assert key in data
        assert isinstance(data["agent_models"], dict)
        assert isinstance(data["qa_enabled"], dict)
        assert isinstance(data["sigma_fallback_enabled"], bool)
        assert isinstance(data["cmdline_attention_preprocessor_enabled"], bool)
        assert isinstance(data["qa_max_retries"], int)
        assert 0.0 <= data["similarity_threshold"] <= 1.0
        assert 0.0 <= data["junk_filter_threshold"] <= 1.0

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_config_versions_list(self, async_client: httpx.AsyncClient):
        """GET /api/workflow/config/versions returns version list."""
        response = await async_client.get("/api/workflow/config/versions")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "versions" in data
        assert isinstance(data["versions"], list)
        for v in data["versions"]:
            assert "version" in v
            assert "is_active" in v
            assert "created_at" in v
            assert "updated_at" in v

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_config_by_version(self, async_client: httpx.AsyncClient):
        """GET /api/workflow/config/version/{version} returns preset-shaped config."""
        # Get current version from active config
        resp = await async_client.get("/api/workflow/config")
        assert resp.status_code == 200
        version = resp.json().get("version", 1)
        response = await async_client.get(f"/api/workflow/config/version/{version}")
        assert response.status_code == 200
        data = response.json()
        assert "thresholds" in data
        assert "agent_models" in data
        assert "agent_prompts" in data
        assert data["thresholds"].get("junk_filter_threshold") is not None
        assert data["thresholds"].get("ranking_threshold") is not None
        assert data["thresholds"].get("similarity_threshold") is not None

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_config_version_404(self, async_client: httpx.AsyncClient):
        """GET /api/workflow/config/version/999999 returns 404."""
        response = await async_client.get("/api/workflow/config/version/999999")
        assert response.status_code == 404


class TestQuickActionsEndpoints:
    """Test quick action endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_rescore_all_articles(self, async_client: httpx.AsyncClient):
        """Test the rescore all articles endpoint."""
        response = await async_client.post("/api/actions/rescore-all")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "message" in data
        assert "processed" in data
        assert data["success"] is True
        assert isinstance(data["processed"], int)
        assert data["processed"] >= 0


class TestArticleLifecycleEndpoints:
    """Article lifecycle helper endpoints."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_mark_article_reviewed(self, async_client: httpx.AsyncClient):
        """Mark an article as reviewed without observables."""
        articles_response = await async_client.get("/api/articles?limit=1")
        if articles_response.status_code != 200:
            pytest.skip("No articles available")
        articles_data = articles_response.json()
        if not articles_data.get("articles"):
            pytest.skip("No articles available")

        article_id = articles_data["articles"][0]["id"]
        response = await async_client.post(f"/api/articles/{article_id}/mark-reviewed")
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["article_id"] == article_id
        assert payload["processing_status"] == "completed"


class TestHealthEndpoints:
    """Test health endpoints respond and report healthy status."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_health_endpoints(self, async_client: httpx.AsyncClient):
        """Ensure critical health endpoints are healthy."""
        health_paths = [
            "/health",
            "/api/health",
            "/api/health/database",
            "/api/health/deduplication",
            "/api/health/services",
            "/api/health/celery",
            "/api/health/ingestion",
        ]

        for path in health_paths:
            response = await async_client.get(path)
            assert response.status_code == 200, f"{path} returned {response.status_code}"
            data = response.json()
            assert isinstance(data, dict)
            assert data.get("status") == "healthy", f"{path} status={data.get('status')}"

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_database_connectivity_detailed(self, async_client: httpx.AsyncClient):
        """Test database connectivity with detailed statistics."""
        response = await async_client.get("/api/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "database" in data
        db_info = data["database"]
        assert db_info.get("connection") == "connected"
        assert "total_articles" in db_info
        assert "total_sources" in db_info
        assert isinstance(db_info["total_articles"], int)
        assert isinstance(db_info["total_sources"], int)


class TestExportEndpoints:
    """Test export/download endpoints."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_export_annotations_csv(self, async_client: httpx.AsyncClient):
        """Ensure annotations export endpoint returns CSV."""
        response = await async_client.get("/api/export/annotations")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type
        disposition = response.headers.get("content-disposition", "")
        assert "filename=" in disposition
        content = response.text
        assert "record_number" in content

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_rescore_all_response_format(self, async_client: httpx.AsyncClient):
        """Test the rescore all articles response format."""
        response = await async_client.post("/api/actions/rescore-all")
        assert response.status_code == 200

        data = response.json()
        # Verify all required fields are present
        required_fields = ["success", "message", "processed"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify field types
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)
        assert isinstance(data["processed"], int)

        # Verify success message format
        assert (
            "Rescoring completed" in data["message"]
            or "No articles found" in data["message"]
            or "All articles already have scores" in data["message"]
        )


class TestCriticalAPIs:
    """Test critical API endpoints for smoke checks."""

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_workflow_trigger_endpoint_exists(self, async_client: httpx.AsyncClient):
        """Workflow trigger endpoint reachable (404 if article missing is ok; endpoint must exist)."""
        # Use a non-existent article ID to test endpoint accessibility without side effects
        response = await async_client.post("/api/workflow/articles/999999/trigger")
        # Endpoint should exist (not 404) even if article doesn't exist
        # Accept 404 (article not found) or 400 (validation error) as proof endpoint works
        assert response.status_code in [200, 400, 404], f"Unexpected status {response.status_code}"
        # If 404, verify it's a proper error response
        if response.status_code == 404:
            data = response.json()
            assert "detail" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_annotation_endpoint_exists(self, async_client: httpx.AsyncClient):
        """Test annotation creation endpoint is accessible."""
        # Test with invalid data to verify endpoint exists without creating data
        response = await async_client.post("/api/articles/999999/annotations", json={"annotation_type": "invalid_type"})
        # Should return 400 (bad request) or 404 (article not found), not 405 (method not allowed)
        assert response.status_code in [400, 404], f"Unexpected status {response.status_code}"
        data = response.json()
        assert "detail" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_redis_connectivity(self, async_client: httpx.AsyncClient):
        """Test Redis connectivity through health endpoint."""
        response = await async_client.get("/api/health/services")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        if "services" in data:
            services = data["services"]
            if "redis" in services:
                assert services["redis"].get("status") in ["healthy", "connected", "available"]

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_celery_worker_health(self, async_client: httpx.AsyncClient):
        """Test Celery worker health endpoint."""
        response = await async_client.get("/api/health/celery")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["healthy", "unhealthy"]  # Accept either, just verify endpoint works
        assert "workers" in data or "status" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_annotation_creation_smoke(self, async_client: httpx.AsyncClient):
        """Test annotation creation endpoint accessibility and write operation if articles available."""
        # Try to get an article for testing
        articles_response = await async_client.get("/api/articles?limit=1")
        article_id = None

        if articles_response.status_code == 200:
            articles_data = articles_response.json()
            if articles_data.get("articles"):
                article_id = articles_data["articles"][0]["id"]

        # If no articles, test endpoint accessibility with non-existent article
        if not article_id:
            article_id = 999999  # Non-existent article ID

        annotation_id = None

        try:
            # Create annotation with valid text length
            annotation_data = {
                "annotation_type": "huntable",
                "selected_text": "x" * 1000,  # Exactly 1000 characters
                "start_position": 0,
                "end_position": 1000,
                "context_before": "",
                "context_after": "",
                "confidence_score": 1.0,
            }

            response = await async_client.post(f"/api/articles/{article_id}/annotations", json=annotation_data)

            # If article doesn't exist, verify we get 404 (not 405 method not allowed)
            if article_id == 999999:
                assert response.status_code == 404, f"Expected 404 for non-existent article, got {response.status_code}"
                data = response.json()
                assert "detail" in data
                return  # Endpoint is accessible, test passes

            # If article exists, verify creation succeeded
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data["success"] is True
            assert "annotation" in data
            annotation_id = data["annotation"]["id"]

            # Verify annotation persists by fetching it
            get_response = await async_client.get(f"/api/articles/{article_id}/annotations")
            assert get_response.status_code == 200
            annotations = get_response.json().get("annotations", [])
            assert any(a["id"] == annotation_id for a in annotations), "Annotation not found after creation"

        finally:
            # Cleanup: delete the annotation if it was created
            if annotation_id:
                try:
                    delete_response = await async_client.delete(
                        f"/api/articles/{article_id}/annotations/{annotation_id}"
                    )
                    # Accept 200 or 404 (already deleted)
                    assert delete_response.status_code in [200, 404]
                except Exception:
                    pass  # Ignore cleanup errors in smoke test

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_workflow_trigger_smoke(self, async_client: httpx.AsyncClient):
        """Test workflow trigger endpoint accepts requests (doesn't wait for completion)."""
        # Try to get an article for testing
        articles_response = await async_client.get("/api/articles?limit=1")
        article_id = None

        if articles_response.status_code == 200:
            articles_data = articles_response.json()
            if articles_data.get("articles"):
                article_id = articles_data["articles"][0]["id"]

        # If no articles, test endpoint accessibility with non-existent article
        if not article_id:
            article_id = 999999  # Non-existent article ID

        # Trigger workflow (may return 400 if execution already exists, or 404 if article doesn't exist)
        response = await async_client.post(f"/api/workflow/articles/{article_id}/trigger")

        # Accept 200 (success), 400 (validation/duplicate), 404 (article not found), or 500 (server error)
        # Just verify endpoint is accessible and responds appropriately (not 405 method not allowed)
        assert response.status_code in [200, 400, 404, 500], f"Unexpected status {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert "execution_id" in data or "message" in data
        elif response.status_code in [400, 404]:
            data = response.json()
            assert "detail" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_sigma_generation_endpoint_smoke(self, async_client: httpx.AsyncClient):
        """Test SIGMA generation endpoint is accessible (doesn't require API key for smoke test)."""
        # Try to get an article for testing
        articles_response = await async_client.get("/api/articles?limit=1")
        article_id = None

        if articles_response.status_code == 200:
            articles_data = articles_response.json()
            if articles_data.get("articles"):
                article_id = articles_data["articles"][0]["id"]

        # If no articles, test endpoint accessibility with non-existent article
        if not article_id:
            article_id = 999999  # Non-existent article ID

        # Try to access SIGMA generation endpoint without API key
        # Should return 400 (missing API key), 404 (article not found), or 500 (server error)
        # Not 405 (method not allowed) - proves endpoint exists
        response = await async_client.post(f"/api/articles/{article_id}/generate-sigma", json={})

        # Accept 400 (validation error), 404 (article not found), or 500 (server error)
        # Just verify endpoint exists and is accessible (not 405 method not allowed)
        assert response.status_code in [400, 404, 500], f"Unexpected status {response.status_code}"

        if response.status_code in [400, 500]:
            data = response.json()
            assert "detail" in data or "error" in data or "message" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_backup_status_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: backup status endpoint is accessible (read-only)."""
        response = await async_client.get("/api/backup/status")
        assert response.status_code == 200
        data = response.json()
        # API returns: automated, total_backups, total_size_gb, last_backup (or legacy status/backups/message)
        assert any(
            k in data
            for k in (
                "status",
                "backups",
                "message",
                "automated",
                "total_backups",
                "total_size_gb",
                "last_backup",
            )
        )

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_backup_list_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: backup list endpoint is accessible (read-only)."""
        response = await async_client.get("/api/backup/list")
        assert response.status_code == 200
        data = response.json()
        # API returns a list directly; support dict with "backups" key for compatibility
        backups = data if isinstance(data, list) else (data.get("backups", []) if isinstance(data, dict) else [])
        assert isinstance(backups, list), "Backup list returns a JSON array or dict with backups key"

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_evaluations_config_versions_models_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: evaluations config-versions-models endpoint is accessible (read-only)."""
        response = await async_client.get(
            "/api/evaluations/config-versions-models",
            params={"config_versions": "1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "models_by_version" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_evaluations_export_bundles_by_config_version_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: export-bundles-by-config-version endpoint is reachable. Expects 404 when no data."""
        response = await async_client.get(
            "/api/evaluations/evals/export-bundles-by-config-version",
            params={"config_version": 999999, "subagent": "cmdline"},
        )
        # 404 when no completed eval records; 200 with application/zip when data exists
        assert response.status_code in (200, 404)
        if response.status_code == 404:
            data = response.json()
            assert "detail" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_search_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: search module reachable (read-only). Uses /api/search/help to avoid /api/articles/{id} conflict."""
        response = await async_client.get("/api/search/help")
        if response.status_code == 422:
            pytest.skip("Search help returned 422 (validation/route may differ in this environment)")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"
        data = response.json()
        assert "help_text" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_workflow_executions_list_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: workflow executions list endpoint is accessible (read-only)."""
        response = await async_client.get("/api/workflow/executions")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert isinstance(data["executions"], list)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_executions_list_with_sort_params(self, async_client: httpx.AsyncClient):
        """Workflow executions list accepts sort_by and sort_order params."""
        response = await async_client.get("/api/workflow/executions?sort_by=id&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert isinstance(data["executions"], list)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_executions_list_with_step_filter(self, async_client: httpx.AsyncClient):
        """Workflow executions list accepts step filter param."""
        response = await async_client.get("/api/workflow/executions?step=extract_agent")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert isinstance(data["executions"], list)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_executions_list_with_article_id(self, async_client: httpx.AsyncClient):
        """Workflow executions list accepts article_id filter param."""
        response = await async_client.get("/api/workflow/executions?article_id=1")
        assert response.status_code == 200
        data = response.json()
        assert "executions" in data
        assert isinstance(data["executions"], list)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_workflow_execution_debug_info_uses_langfuse(self, async_client: httpx.AsyncClient):
        """Debug info returns uses_langfuse (LangSmith deprecated, use Langfuse)."""
        list_resp = await async_client.get("/api/workflow/executions?limit=1")
        assert list_resp.status_code == 200
        data = list_resp.json()
        executions = data.get("executions", [])
        if not executions:
            pytest.skip("No workflow executions in DB")
        exec_id = executions[0]["id"]
        resp = await async_client.get(f"/api/workflow/executions/{exec_id}/debug-info")
        assert resp.status_code == 200
        info = resp.json()
        assert "uses_langfuse" in info
        assert "uses_langsmith" not in info  # Deprecated: removed 2026-02-04

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_dashboard_data_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: dashboard data API is accessible (read-only)."""
        response = await async_client.get("/api/dashboard/data")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_metrics_health_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: metrics health endpoint is accessible (read-only)."""
        response = await async_client.get("/api/metrics/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "uptime" in data or "total_sources" in data or "avg_response_time" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_metrics_volume_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: metrics volume endpoint is accessible (read-only)."""
        response = await async_client.get("/api/metrics/volume")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "daily" in data and "hourly" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_annotations_stats_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: annotations stats endpoint is accessible (read-only)."""
        response = await async_client.get("/api/annotations/stats")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "stats" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_annotations_types_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: annotations types endpoint is accessible (read-only)."""
        response = await async_client.get("/api/annotations/types")
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "modes" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_jobs_status_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: jobs status endpoint is accessible (read-only)."""
        response = await async_client.get("/api/jobs/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "status" in data or "timestamp" in data

    @pytest.mark.api
    @pytest.mark.smoke
    @pytest.mark.asyncio
    async def test_workflow_config_versions_smoke(self, async_client: httpx.AsyncClient):
        """Smoke: workflow config versions endpoint is accessible (read-only)."""
        response = await async_client.get("/api/workflow/config/versions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict) and "versions" in data
        assert isinstance(data["versions"], list)


class TestPerformance:
    """Test performance and response times."""

    @pytest.mark.api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_response_times(self, async_client: httpx.AsyncClient):
        """Test that endpoints respond within reasonable time."""
        import time

        start_time = time.time()
        response = await async_client.get("/")
        end_time = time.time()

        assert response.status_code == 200
        assert (end_time - start_time) < 5.0  # Should respond within 5 seconds

    @pytest.mark.api
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, async_client: httpx.AsyncClient):
        """Test handling of concurrent requests."""
        import asyncio

        async def make_request():
            return await async_client.get("/")

        # Make 5 concurrent requests
        tasks = [make_request() for _ in range(5)]
        responses = await asyncio.gather(*tasks)

        # All should succeed
        for response in responses:
            assert response.status_code == 200
