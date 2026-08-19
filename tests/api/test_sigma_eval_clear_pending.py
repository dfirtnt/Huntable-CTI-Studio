"""Regression coverage for clearing pending Sigma evaluation records."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from starlette.requests import Request

from src.web.routes import evaluation_api

pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_clear_pending_sigma_eval_records_deletes_pending_rows_and_audits():
    pending_records = [
        SimpleNamespace(id=11, status="pending"),
        SimpleNamespace(id=12, status="pending"),
    ]
    query = MagicMock()
    query.filter.return_value.all.return_value = pending_records
    session = MagicMock()
    session.query.return_value = query

    request = MagicMock(spec=Request)
    with (
        patch.object(evaluation_api, "DatabaseManager") as database_manager,
        patch.object(evaluation_api, "_audit_eval") as audit_eval,
    ):
        database_manager.return_value.get_session.return_value = session

        result = await evaluation_api.clear_pending_sigma_eval_records(request)

    assert result == {
        "success": True,
        "deleted_count": 2,
        "message": "Deleted 2 pending Sigma eval record(s)",
    }
    session.query.assert_called_once_with(evaluation_api.SigmaEvaluationTable)
    query.filter.assert_called_once()
    session.delete.assert_has_calls([call(record) for record in pending_records])
    session.commit.assert_called_once()
    session.close.assert_called_once()
    audit_eval.assert_called_once()
    assert audit_eval.call_args.args[2] == evaluation_api.ACTION_EVAL_RECORDS_CLEARED
    assert audit_eval.call_args.args[3] == "sigma"
    assert audit_eval.call_args.kwargs["mandatory"] is True
