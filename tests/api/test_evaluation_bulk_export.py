"""Focused tests for evaluation bulk bundle export behavior."""

from unittest.mock import MagicMock, patch

import pytest

from src.web.routes.evaluation_api import export_bundles_by_config_version

pytestmark = [pytest.mark.api]


class _QueryResult:
    def __init__(self, records):
        self.records = records

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.records


@pytest.mark.asyncio
async def test_bulk_bundle_export_skips_langfuse_by_default():
    record = MagicMock()
    record.workflow_execution_id = 101
    record.article_id = 55
    record.id = 7

    session = MagicMock()
    session.query.return_value = _QueryResult([record])
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {
        "schema_version": "eval_bundle_v1",
        "bundle_id": "bundle-1",
        "integrity": {"bundle_sha256": "already-computed", "warnings": []},
    }

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api.EvalBundleService", return_value=bundle_service),
    ):
        response = await export_bundles_by_config_version(
            request=MagicMock(),
            config_version=42,
            subagent="cmdline",
        )

    assert response.status_code == 200
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=101,
        agent_name="CmdlineExtract",
        attempt=None,
        fetch_langfuse=False,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_bundle_export_can_include_langfuse_when_requested():
    record = MagicMock()
    record.workflow_execution_id = 102
    record.article_id = 56
    record.id = 8

    session = MagicMock()
    session.query.return_value = _QueryResult([record])
    db_manager = MagicMock()
    db_manager.get_session.return_value = session

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {
        "schema_version": "eval_bundle_v1",
        "bundle_id": "bundle-2",
        "integrity": {"bundle_sha256": "already-computed", "warnings": []},
    }

    with (
        patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.evaluation_api.EvalBundleService", return_value=bundle_service),
    ):
        response = await export_bundles_by_config_version(
            request=MagicMock(),
            config_version=42,
            subagent="cmdline",
            include_langfuse=True,
        )

    assert response.status_code == 200
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=102,
        agent_name="CmdlineExtract",
        attempt=None,
        fetch_langfuse=True,
    )
    session.close.assert_called_once()
