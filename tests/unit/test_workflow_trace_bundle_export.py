from unittest.mock import MagicMock, patch

from src.web.routes.workflow_executions import (
    _build_workflow_trace_bundle,
    _detect_eval_bundle_agents,
    export_workflow_execution_trace_bundle,
)


class _Detail:
    def __init__(self, payload):
        self.payload = payload

    def dict(self):
        return self.payload


def test_detect_eval_bundle_agents_from_error_log():
    error_log = {
        "rank_article": {"conversation_log": [{"attempt": 1}]},
        "os_detection_result": {"detected_os": "linux"},
        "extract_agent": {
            "conversation_log": [
                {"agent": "CmdlineExtract"},
                {"agent": "ProcTreeExtract"},
                {"agent": "CmdlineExtract"},
                {"agent": "RemovedLegacyAgent"},
            ]
        },
        "generate_sigma": {"conversation_log": [{"event_type": "generation_call"}]},
    }

    assert _detect_eval_bundle_agents(error_log) == [
        "rank_article",
        "generate_sigma",
        "CmdlineExtract",
        "ProcTreeExtract",
    ]


def test_build_workflow_trace_bundle_reuses_detail_and_embeds_eval_bundles():
    detail = _Detail(
        {
            "id": 3534,
            "article_id": 7,
            "status": "failed",
            "error_log": {
                "rank_article": {"conversation_log": [{"attempt": 1}]},
                "extract_agent": {"conversation_log": [{"agent": "CmdlineExtract"}]},
            },
        }
    )

    bundle_service = MagicMock()
    bundle_service.generate_bundle.side_effect = [
        {"schema_version": "eval_bundle_v1", "bundle_id": "rank"},
        {"schema_version": "eval_bundle_v1", "bundle_id": "cmd"},
    ]

    with (
        patch("src.web.routes.workflow_executions._build_execution_detail_response", return_value=detail),
        patch("src.web.routes.workflow_executions.EvalBundleService", return_value=bundle_service),
    ):
        bundle = _build_workflow_trace_bundle(MagicMock(), 3534, include_eval_bundles=True, slim=True)

    assert bundle["schema_version"] == "workflow_execution_trace_v1"
    assert bundle["execution_id"] == 3534
    assert bundle["execution"]["status"] == "failed"
    assert set(bundle["eval_bundles"]) == {"rank_article", "CmdlineExtract"}
    assert bundle["integrity"]["bundle_sha256"]
    assert bundle_service.generate_bundle.call_args_list[0].kwargs == {
        "execution_id": 3534,
        "agent_name": "rank_article",
        "attempt": None,
        "fetch_langfuse": False,
        "slim": True,
    }


def test_build_workflow_trace_bundle_can_skip_eval_bundles():
    detail = _Detail(
        {
            "id": 3534,
            "article_id": 7,
            "status": "failed",
            "error_log": {"rank_article": {"conversation_log": [{"attempt": 1}]}},
        }
    )

    with (
        patch("src.web.routes.workflow_executions._build_execution_detail_response", return_value=detail),
        patch("src.web.routes.workflow_executions.EvalBundleService") as bundle_service_cls,
    ):
        bundle = _build_workflow_trace_bundle(MagicMock(), 3534, include_eval_bundles=False)

    assert bundle["eval_bundles"] == {}
    assert bundle["eval_bundle_errors"] == {}
    bundle_service_cls.assert_not_called()


def test_export_workflow_execution_trace_bundle_returns_download_response():
    session = MagicMock()
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    bundle = {
        "schema_version": "workflow_execution_trace_v1",
        "execution_id": 3534,
        "execution": {"status": "failed"},
        "eval_bundles": {},
        "eval_bundle_errors": {},
        "integrity": {"bundle_sha256": "abc", "warnings": []},
    }

    with (
        patch("src.web.routes.workflow_executions.get_db_manager", return_value=db_manager),
        patch("src.web.routes.workflow_executions._build_workflow_trace_bundle", return_value=bundle),
    ):
        response = export_workflow_execution_trace_bundle(
            MagicMock(),
            3534,
            include_eval_bundles=True,
            include_langfuse=False,
            slim=False,
        )

    assert response.status_code == 200
    assert response.media_type == "application/json"
    assert response.headers["content-disposition"] == "attachment; filename=workflow_execution_trace_3534.json"
    session.close.assert_called_once()
