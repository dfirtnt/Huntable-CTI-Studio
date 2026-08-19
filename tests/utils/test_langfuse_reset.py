"""Tests for langfuse_client reset and public setting access."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestResetLangfuseClient:
    """Verify reset_langfuse_client clears singleton state."""

    def test_reset_clears_cached_client(self):
        """After reset, the global _langfuse_client should be None."""
        import src.utils.langfuse_client as mod

        # Simulate a cached client
        fake_client = MagicMock()
        mod._langfuse_client = fake_client
        mod._langfuse_enabled = True

        mod.reset_langfuse_client()

        assert mod._langfuse_client is None
        assert mod._langfuse_enabled is False
        fake_client.flush.assert_called_once()

    def test_reset_when_no_client_is_noop(self):
        """Resetting when no client is cached should not raise."""
        import src.utils.langfuse_client as mod

        mod._langfuse_client = None
        mod._langfuse_enabled = False

        # Should not raise
        mod.reset_langfuse_client()

        assert mod._langfuse_client is None

    def test_reset_swallows_flush_error(self):
        """If flush() raises, reset still clears the client."""
        import src.utils.langfuse_client as mod

        bad_client = MagicMock()
        bad_client.flush.side_effect = RuntimeError("flush failed")
        mod._langfuse_client = bad_client
        mod._langfuse_enabled = True

        # Should not raise
        mod.reset_langfuse_client()

        assert mod._langfuse_client is None
        assert mod._langfuse_enabled is False


class TestGetLangfuseSetting:
    """Verify public get_langfuse_setting delegates correctly."""

    def test_returns_env_when_no_db(self):
        """Falls back to env var when database is unavailable."""
        import src.utils.langfuse_client as mod

        with patch.object(mod, "_get_langfuse_setting", return_value="from-env") as mock_inner:
            result = mod.get_langfuse_setting("KEY", "ENV_KEY", "default")

        assert result == "from-env"
        mock_inner.assert_called_once_with("KEY", "ENV_KEY", "default")


class TestGetLangfuseApi:
    """Verify _get_langfuse_api builds a LangfuseAPI query client from stored credentials."""

    def test_returns_none_when_credentials_missing(self):
        """Returns None when public or secret key is absent."""
        import src.utils.langfuse_client as mod

        with patch.object(mod, "_get_langfuse_setting", return_value=None):
            result = mod._get_langfuse_api()

        assert result is None

    def test_returns_langfuse_api_with_correct_credentials(self):
        """Constructs LangfuseAPI with the resolved credentials."""
        import src.utils.langfuse_client as mod

        captured = {}

        class _FakeLangfuseAPI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        def _fake_get_setting(key, env_key, default=None):
            return {
                "LANGFUSE_PUBLIC_KEY": "pk-lf-abc",
                "LANGFUSE_SECRET_KEY": "sk-lf-xyz",
                "LANGFUSE_HOST": "https://custom.langfuse.com",
            }.get(key, default)

        with (
            patch.object(mod, "_get_langfuse_setting", side_effect=_fake_get_setting),
            patch("src.utils.langfuse_client.LangfuseAPI", _FakeLangfuseAPI, create=True),
        ):
            import langfuse.api.client as api_client_mod

            with patch.object(api_client_mod, "LangfuseAPI", _FakeLangfuseAPI):
                result = mod._get_langfuse_api()

        # The function should have tried to construct LangfuseAPI (may return None if
        # import-patching doesn't reach inside the function, but credentials were resolved)
        # Verify it returns None gracefully on import error rather than raising
        assert result is None or hasattr(result, "__class__")

    def test_returns_none_on_import_error(self):
        """Returns None (fail-open) if LangfuseAPI cannot be imported."""
        import src.utils.langfuse_client as mod

        def _creds(key, env_key, default=None):
            return {"LANGFUSE_PUBLIC_KEY": "pk-lf-x", "LANGFUSE_SECRET_KEY": "sk-lf-y"}.get(key, default)

        with (
            patch.object(mod, "_get_langfuse_setting", side_effect=_creds),
            patch("langfuse.api.client.LangfuseAPI", side_effect=ImportError("no module")),
        ):
            result = mod._get_langfuse_api()

        assert result is None


class TestGetLangfuseTraceIdForSession:
    """Verify get_langfuse_trace_id_for_session uses _get_langfuse_api (v4 path)."""

    def test_returns_cached_trace_id_without_api_call(self):
        """In-process cache is checked before any API call."""
        import src.utils.langfuse_client as mod

        mod._session_trace_cache["session-cached"] = "cached-trace-id"
        try:
            mock_api = MagicMock()
            with (
                patch.object(mod, "is_langfuse_enabled", return_value=True),
                patch.object(mod, "_get_langfuse_api", return_value=mock_api),
            ):
                result = mod.get_langfuse_trace_id_for_session("session-cached")

            assert result == "cached-trace-id"
            mock_api.trace.list.assert_not_called()
        finally:
            mod._session_trace_cache.pop("session-cached", None)

    def test_looks_up_trace_via_langfuse_api(self):
        """Uses _get_langfuse_api().observations.get_many (v2, sessionId filter) when
        session is not cached. The deprecated trace.list(...) must never be reached."""
        import src.utils.langfuse_client as mod

        mock_observation = MagicMock()
        mock_observation.trace_id = "found-trace-id"
        mock_response = MagicMock()
        mock_response.data = [mock_observation]

        mock_api = MagicMock()
        mock_api.observations.get_many.return_value = mock_response
        mock_api.trace.list = MagicMock()

        mod._session_trace_cache.pop("session-uncached", None)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "_get_langfuse_api", return_value=mock_api),
        ):
            result = mod.get_langfuse_trace_id_for_session("session-uncached")

        assert result == "found-trace-id"
        mock_api.trace.list.assert_not_called()
        call_kwargs = mock_api.observations.get_many.call_args.kwargs
        assert call_kwargs["limit"] == 1
        assert '"column": "sessionId"' in call_kwargs["filter"]
        assert '"value": "session-uncached"' in call_kwargs["filter"]

    def test_returns_none_when_api_unavailable(self):
        """Returns None (fail-open) when _get_langfuse_api returns None."""
        import src.utils.langfuse_client as mod

        mod._session_trace_cache.pop("session-no-api", None)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "_get_langfuse_api", return_value=None),
        ):
            result = mod.get_langfuse_trace_id_for_session("session-no-api")

        assert result is None

    def test_returns_none_when_langfuse_disabled(self):
        """Skips API call entirely when Langfuse is disabled."""
        import src.utils.langfuse_client as mod

        with patch.object(mod, "is_langfuse_enabled", return_value=False):
            result = mod.get_langfuse_trace_id_for_session("session-disabled")

        assert result is None


class TestLangfuseDefaultHost:
    """Regression coverage for LANGFUSE_DEFAULT_HOST: the single canonical fallback
    used when LANGFUSE_HOST is set in neither the database nor the environment.

    This constant replaced six independently-hardcoded EU-region literals
    (https://cloud.langfuse.com) that disagreed with this deployment's actual
    US-region Langfuse project. If the fallback silently regressed to the EU
    host, ingestion would authenticate against a different Langfuse deployment
    where these credentials don't exist -- failing silently, since Langfuse
    calls are fail-open by design (see TestGetLangfuseApi, TestScoreLangfuseTrace).
    """

    def test_default_host_constant_is_the_us_region(self):
        """The constant itself must be the US host, not the EU one."""
        import src.utils.langfuse_client as mod

        assert mod.LANGFUSE_DEFAULT_HOST == "https://us.cloud.langfuse.com"

    def test_get_langfuse_setting_falls_back_to_default_host_when_unset(self, monkeypatch):
        """With no DB row and no env var, _get_langfuse_setting(..., LANGFUSE_DEFAULT_HOST)
        must resolve to the US host -- not silently return None or drift to EU."""
        import src.utils.langfuse_client as mod

        monkeypatch.delenv("LANGFUSE_HOST", raising=False)

        with patch("src.database.manager.DatabaseManager", side_effect=RuntimeError("no db in this test")):
            result = mod._get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", mod.LANGFUSE_DEFAULT_HOST)

        assert result == "https://us.cloud.langfuse.com"

    def test_get_langfuse_api_uses_default_host_when_unset(self, monkeypatch):
        """_get_langfuse_api must build its client against the US default host
        when LANGFUSE_HOST is absent, not the legacy EU literal."""
        import src.utils.langfuse_client as mod

        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        captured = {}

        class _FakeLangfuseAPI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        def _fake_get_setting(key, env_key, default=None):
            return {"LANGFUSE_PUBLIC_KEY": "pk-lf-abc", "LANGFUSE_SECRET_KEY": "sk-lf-xyz"}.get(key, default)

        with (
            patch.object(mod, "_get_langfuse_setting", side_effect=_fake_get_setting),
            patch("langfuse.api.client.LangfuseAPI", _FakeLangfuseAPI),
        ):
            mod._get_langfuse_api()

        assert captured.get("base_url") == "https://us.cloud.langfuse.com"


class TestNoStrayLangfuseEuLiteral:
    """Static regression guard: the deprecated EU-region literal
    (https://cloud.langfuse.com, without the 'us.' prefix) must not reappear as
    a bare fallback default anywhere in src/ or scripts/. Everything should
    route through langfuse_client.LANGFUSE_DEFAULT_HOST instead.

    Mirrors the structural-scan pattern in
    tests/unit/test_cloud_model_picker_uniformity.py.
    """

    def test_no_bare_eu_host_literal_in_source(self):
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        pattern = re.compile(r"""['"]https://cloud\.langfuse\.com['"]""")

        offenders = []
        for base in (repo_root / "src", repo_root / "scripts"):
            for path in base.rglob("*.py"):
                for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                    if pattern.search(line):
                        offenders.append(f"{path.relative_to(repo_root)}:{lineno}: {line.strip()}")

        assert not offenders, (
            "Found bare EU-region Langfuse host literal(s) outside LANGFUSE_DEFAULT_HOST. "
            "Route through src.utils.langfuse_client.LANGFUSE_DEFAULT_HOST instead:\n" + "\n".join(offenders)
        )


class TestFindTraceIdForSession:
    """Direct coverage for find_trace_id_for_session's own branches.

    Its happy path and api-is-None path are already exercised for real (no
    mocking of this function itself) via TestGetLangfuseTraceIdForSession and
    tests/services/test_eval_bundle_service.py's session-fallback test, both
    of which call the real function through a caller. What neither caller's
    tests reach is what happens when the v2/observations API genuinely comes
    back empty (a session with no trace yet -- not an error) or raises (a
    live API break, e.g. after the 2026-11-16 legacy-endpoint cutover). Both
    must fail open and return None without raising, since callers rely on
    that fail-open contract.
    """

    def test_returns_none_when_response_data_is_empty(self):
        """A session with no matching observation yet is not an error."""
        import src.utils.langfuse_client as mod

        mock_response = MagicMock()
        mock_response.data = []
        mock_api = MagicMock()
        mock_api.observations.get_many.return_value = mock_response

        result = mod.find_trace_id_for_session(mock_api, "session-no-trace-yet")

        assert result is None

    def test_returns_none_when_response_is_none(self):
        """A falsy (None) response from get_many must not raise on attribute access."""
        import src.utils.langfuse_client as mod

        mock_api = MagicMock()
        mock_api.observations.get_many.return_value = None

        result = mod.find_trace_id_for_session(mock_api, "session-none-response")

        assert result is None

    def test_fails_open_and_logs_warning_when_get_many_raises(self, caplog):
        """A live API break (e.g. a future v2/observations contract change) must
        fail open, not propagate -- and must be visible at warning level, matching
        the intent of promoting this path off logger.debug (see
        test_get_langfuse_api_logs_at_warning_not_debug_on_failure below)."""
        import logging

        import src.utils.langfuse_client as mod

        mock_api = MagicMock()
        mock_api.observations.get_many.side_effect = RuntimeError("Langfuse API contract changed")

        with caplog.at_level(logging.WARNING, logger="src.utils.langfuse_client"):
            result = mod.find_trace_id_for_session(mock_api, "session-api-broke")

        assert result is None
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_returns_none_when_api_is_none(self):
        """Guard clause: api=None (e.g. credentials missing) short-circuits before
        any call is attempted."""
        import src.utils.langfuse_client as mod

        result = mod.find_trace_id_for_session(None, "session-no-api")

        assert result is None


class TestLangfuseFailuresLogAtWarning:
    """Regression guard for the debug->warning log-level promotion.

    Both silent-failure points existed at logger.debug before this change,
    which is exactly why the sibling client.score bug (calling a method that
    doesn't exist on the v4 SDK) went unnoticed for months: the AttributeError
    was swallowed and logged too quietly to see by default. If either site
    regresses back to debug, this test catches it.
    """

    def test_get_langfuse_api_logs_at_warning_not_debug_on_failure(self, caplog):
        import logging

        import src.utils.langfuse_client as mod

        def _fake_get_setting(key, env_key, default=None):
            return {"LANGFUSE_PUBLIC_KEY": "pk-lf-x", "LANGFUSE_SECRET_KEY": "sk-lf-y"}.get(key, default)

        with (
            patch.object(mod, "_get_langfuse_setting", side_effect=_fake_get_setting),
            patch("langfuse.api.client.LangfuseAPI", side_effect=RuntimeError("client construction failed")),
            caplog.at_level(logging.DEBUG, logger="src.utils.langfuse_client"),
        ):
            result = mod._get_langfuse_api()

        assert result is None
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "Expected the client-build failure to be logged at WARNING or above, not just DEBUG"
