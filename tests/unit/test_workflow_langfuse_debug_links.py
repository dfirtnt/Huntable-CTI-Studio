from src.web.routes.workflow_executions import _build_langfuse_debug_urls


def test_langfuse_debug_url_prefers_direct_trace_when_trace_id_resolved():
    urls = _build_langfuse_debug_urls(
        "https://us.cloud.langfuse.com",
        "project_123",
        "workflow_exec_3533",
        "abcdef1234567890abcdef1234567890",
    )

    assert (
        urls["agent_chat_url"]
        == "https://us.cloud.langfuse.com/project/project_123/traces/abcdef1234567890abcdef1234567890"
    )
    assert urls["session_url"] == "https://us.cloud.langfuse.com/project/project_123/sessions/workflow_exec_3533"
    assert urls["search_url"] == "https://us.cloud.langfuse.com/project/project_123/traces?search=workflow_exec_3533"


def test_langfuse_debug_url_uses_trace_search_without_trace_id():
    urls = _build_langfuse_debug_urls(
        "https://us.cloud.langfuse.com",
        "project_123",
        "workflow_exec_3533",
        None,
    )

    assert (
        urls["agent_chat_url"] == "https://us.cloud.langfuse.com/project/project_123/traces?search=workflow_exec_3533"
    )
    assert urls["session_url"] == "https://us.cloud.langfuse.com/project/project_123/sessions/workflow_exec_3533"
    assert urls["search_url"] == "https://us.cloud.langfuse.com/project/project_123/traces?search=workflow_exec_3533"


def test_langfuse_debug_url_uses_global_search_without_project_id():
    urls = _build_langfuse_debug_urls(
        "https://us.cloud.langfuse.com",
        None,
        "workflow_exec_3533",
        "abcdef1234567890abcdef1234567890",
    )

    assert urls["agent_chat_url"] == "https://us.cloud.langfuse.com/traces?search=workflow_exec_3533"
    assert urls["session_url"] is None
    assert urls["search_url"] == "https://us.cloud.langfuse.com/traces?search=workflow_exec_3533"
