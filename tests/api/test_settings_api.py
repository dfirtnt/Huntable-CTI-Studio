"""API tests for Settings endpoints: GET merge, bulk update, and Langfuse singleton reset."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.codex_app_server_client import CodexAppServerError


def _fake_request():
    return SimpleNamespace(
        state=SimpleNamespace(request_id="test-request"),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )


@pytest.mark.api
class TestSettingsAPILMStudioURL:
    """Test that Settings synchronizes the optional LM Studio LLM URL."""

    @pytest.mark.asyncio
    async def test_get_settings_includes_lmstudio_url_from_env(self, monkeypatch):
        """GET /api/settings merges LMSTUDIO_API_URL from env when absent from the DB."""
        monkeypatch.setenv("LMSTUDIO_API_URL", "http://192.168.1.65:1234/v1")

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            from src.web.routes.settings import get_all_settings

            result = await get_all_settings()

        # JSONResponse lets us set Cache-Control: no-store so browsers don't serve stale settings after a save.
        assert result.headers.get("cache-control") == "no-store"

        payload = json.loads(result.body)
        assert payload["success"] is True
        settings = payload.get("settings") or {}
        assert settings.get("LMSTUDIO_API_URL") == "http://192.168.1.65:1234/v1"

    @pytest.mark.asyncio
    async def test_bulk_update_lmstudio_url_syncs_env(self, monkeypatch):
        """Bulk update of LMSTUDIO_API_URL updates os.environ for provider clients."""
        import os

        settings_dict = {"LMSTUDIO_API_URL": "http://localhost:1234/v1"}
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        try:
            with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
                mock_mgr.get_session.return_value = Ctx()
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                result = await update_settings_bulk(SettingsBulkUpdate(settings=settings_dict), _fake_request())

            assert result["success"] is True
            assert "LMSTUDIO_API_URL" in result["updated_keys"]
            assert os.environ.get("LMSTUDIO_API_URL") == "http://localhost:1234/v1"
        finally:
            os.environ.pop("LMSTUDIO_API_URL", None)


@pytest.mark.api
class TestSettingsCodexSubscription:
    @pytest.mark.asyncio
    async def test_codex_subscription_test_reports_chatgpt_plan(self):
        with patch("src.web.routes.settings.CodexAppServerClient") as client_cls:
            client_cls.return_value.read_account = AsyncMock(
                return_value={"account": {"type": "chatgpt", "planType": "plus"}}
            )
            from src.web.routes.settings import test_codex_subscription

            result = await test_codex_subscription()

        assert result == {"valid": True, "message": "Codex subscription is ready (plus)", "plan_type": "plus"}

    @pytest.mark.asyncio
    async def test_codex_subscription_test_reports_login_error(self):
        with patch("src.web.routes.settings.CodexAppServerClient") as client_cls:
            client_cls.return_value.read_account = AsyncMock(side_effect=CodexAppServerError("Login required"))
            from src.web.routes.settings import test_codex_subscription

            result = await test_codex_subscription()

        assert result == {
            "valid": False,
            "message": "Codex subscription is not connected. Ask an administrator to connect it.",
        }

    @pytest.mark.asyncio
    async def test_codex_subscription_test_rejects_non_chatgpt_auth(self):
        with patch("src.web.routes.settings.CodexAppServerClient") as client_cls:
            client_cls.return_value.read_account = AsyncMock(return_value={"account": {"type": "apiKey"}})
            from src.web.routes.settings import test_codex_subscription

            result = await test_codex_subscription()

        assert result["valid"] is False
        assert result["message"] == "Codex subscription is not connected. Ask an administrator to connect it."


def _make_settings_db_ctx(existing_value=None):
    """Build a mock async DB context that simulates a single-setting lookup."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    if existing_value is not None:
        existing = MagicMock()
        existing.value = existing_value
        mock_result.scalar_one_or_none.return_value = existing
    else:
        mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    class Ctx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *a):
            pass

    return Ctx()


@pytest.mark.api
class TestSettingsLangfuseReset:
    """Saving a Langfuse credential key must reset the in-memory client singleton."""

    @pytest.mark.asyncio
    async def test_update_langfuse_public_key_resets_singleton(self):
        """update_setting for LANGFUSE_PUBLIC_KEY calls reset_langfuse_client()."""
        reset_calls = []

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = _make_settings_db_ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingUpdate, update_setting

                await update_setting(SettingUpdate(key="LANGFUSE_PUBLIC_KEY", value="pk-lf-new"), _fake_request())

        assert len(reset_calls) == 1

    @pytest.mark.asyncio
    async def test_update_non_langfuse_key_does_not_reset_singleton(self):
        """update_setting for an unrelated key must NOT call reset_langfuse_client()."""
        reset_calls = []

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = _make_settings_db_ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingUpdate, update_setting

                await update_setting(SettingUpdate(key="SOME_OTHER_KEY", value="value"), _fake_request())

        assert len(reset_calls) == 0


@pytest.mark.api
class TestSettingsAudit:
    """Settings mutations must share the mutation and mandatory audit transaction."""

    @pytest.mark.asyncio
    async def test_update_setting_does_not_commit_when_mandatory_audit_fails(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            with patch(
                "src.web.routes.settings.AsyncAuditService.record_mandatory",
                AsyncMock(side_effect=RuntimeError("audit write failed")),
            ):
                from src.web.routes.settings import SettingUpdate, update_setting

                with pytest.raises(HTTPException) as exc_info:
                    await update_setting(
                        SettingUpdate(key="WORKFLOW_OPENAI_API_KEY", value="sk-test"),
                        _fake_request(),
                    )

        assert exc_info.value.status_code == 500
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_with_langfuse_key_resets_singleton(self):
        """Bulk update containing LANGFUSE_SECRET_KEY calls reset_langfuse_client()."""
        reset_calls = []

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                await update_settings_bulk(
                    SettingsBulkUpdate(settings={"LANGFUSE_SECRET_KEY": "sk-lf-new", "OTHER": "val"}),
                    _fake_request(),
                )

        assert len(reset_calls) == 1

    @pytest.mark.asyncio
    async def test_bulk_update_without_langfuse_keys_does_not_reset_singleton(self):
        """Bulk update with no Langfuse keys must NOT call reset_langfuse_client()."""
        reset_calls = []

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                await update_settings_bulk(SettingsBulkUpdate(settings={"UNRELATED_KEY": "val"}), _fake_request())

        assert len(reset_calls) == 0


@pytest.mark.api
class TestSettingsSecretMasking:
    """No settings read route may return a stored credential value.

    The Settings page loaded these into the live DOM, where `type="password"` hides
    them from view but not from devtools, an extension, or a DOM dump. The UI only
    ever needed "is one set", so the routes return `configured`/`hint` instead.
    """

    # Long enough that a partial leak of the first 8 characters is still detectable
    # as a substring miss rather than an accidental equality.
    SECRET = "cti-fixture-secret-value-that-must-never-leave-0123456789"

    @staticmethod
    def _all_settings_ctx(rows: dict[str, str]):
        mock_session = MagicMock()
        mock_result = MagicMock()
        scalars = []
        for key, value in rows.items():
            row = MagicMock()
            row.key = key
            row.value = value
            scalars.append(row)
        mock_result.scalars.return_value.all.return_value = scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        return Ctx()

    @staticmethod
    def _single_setting_ctx(key: str, value: str | None):
        """One-row lookup with JSON-serializable metadata, as the real column types are."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        if value is None:
            mock_result.scalar_one_or_none.return_value = None
        else:
            row = SimpleNamespace(key=key, value=value, description="desc", category="user")
            mock_result.scalar_one_or_none.return_value = row
        mock_session.execute = AsyncMock(return_value=mock_result)

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        return Ctx()

    @pytest.mark.asyncio
    async def test_get_all_settings_never_returns_a_secret_value(self):
        rows = {"GITHUB_TOKEN": self.SECRET, "GITHUB_REPO": "owner/repo"}

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = self._all_settings_ctx(rows)
            from src.web.routes.settings import get_all_settings

            result = await get_all_settings()

        body = result.body.decode()
        assert self.SECRET not in body
        payload = json.loads(body)
        assert payload["settings"]["GITHUB_TOKEN"] is None
        # A non-sensitive setting still round-trips, or the page loses real fields.
        assert payload["settings"]["GITHUB_REPO"] == "owner/repo"
        assert payload["sensitive"]["GITHUB_TOKEN"]["configured"] is True
        assert "GITHUB_REPO" not in payload["sensitive"]

    @pytest.mark.asyncio
    async def test_get_setting_never_returns_a_secret_value(self):
        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = self._single_setting_ctx("GITHUB_TOKEN", self.SECRET)
            from src.web.routes.settings import get_setting

            result = await get_setting("GITHUB_TOKEN")

        body = result.body.decode()
        assert self.SECRET not in body
        payload = json.loads(body)
        assert payload["value"] is None
        assert payload["sensitive"] is True
        assert payload["configured"] is True
        assert payload["exists"] is True

    @pytest.mark.asyncio
    async def test_get_setting_returns_non_sensitive_values_verbatim(self):
        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = self._single_setting_ctx("GITHUB_REPO", "owner/repo")
            from src.web.routes.settings import get_setting

            result = await get_setting("GITHUB_REPO")

        payload = json.loads(result.body)
        assert payload["value"] == "owner/repo"
        assert payload["sensitive"] is False

    @pytest.mark.asyncio
    async def test_get_setting_sets_no_store(self):
        """Individual secret-bearing responses must not be cacheable."""
        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = self._single_setting_ctx("GITHUB_TOKEN", self.SECRET)
            from src.web.routes.settings import get_setting

            result = await get_setting("GITHUB_TOKEN")

        assert result.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_missing_setting_still_reports_sensitivity(self):
        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = self._single_setting_ctx("LANGFUSE_SECRET_KEY", None)
            from src.web.routes.settings import get_setting

            result = await get_setting("LANGFUSE_SECRET_KEY")

        payload = json.loads(result.body)
        assert payload["exists"] is False
        assert payload["configured"] is False
        assert payload["sensitive"] is True

    @pytest.mark.asyncio
    async def test_update_setting_does_not_echo_the_secret_back(self):
        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = _make_settings_db_ctx()
            from src.web.routes.settings import SettingUpdate, update_setting

            result = await update_setting(
                SettingUpdate(key="WORKFLOW_OPENAI_API_KEY", value=self.SECRET),
                _fake_request(),
            )

        assert result["value"] is None
        assert result["configured"] is True
        assert self.SECRET not in json.dumps(result)

    def test_every_credential_the_settings_page_manages_is_classified_sensitive(self):
        """Guards the masking set against a renamed or newly added credential key."""
        from src.web.routes.settings import _is_sensitive_setting

        for key in (
            "GITHUB_TOKEN",
            "LANGFUSE_SECRET_KEY",
            "WORKFLOW_OPENAI_API_KEY",
            "WORKFLOW_ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "HUGGINGFACE_API_TOKEN",
        ):
            assert _is_sensitive_setting(key) is True, key

        # These must keep round-tripping: the page shows their real values.
        for key in ("GITHUB_REPO", "GIT_NAME", "GIT_EMAIL", "SIGMA_REPO_PATH", "LANGFUSE_HOST", "LANGFUSE_PROJECT_ID"):
            assert _is_sensitive_setting(key) is False, key


def _github_test_body(**kwargs):
    """Build the route's optional override model without importing it at module scope."""
    from src.web.routes.settings import GitHubConnectionTest

    return GitHubConnectionTest(**kwargs)


@pytest.mark.api
class TestGitHubConnectionTest:
    """POST /api/settings/github/test replaced a browser-side call to api.github.com.

    That call carried the PAT into the page and out to a third-party origin (a
    standing connect-src violation). Now the request is made server-side against
    the stored credential, which means this route is the only thing that still
    touches the token -- so its branches, and the fact that it never echoes the
    token back, are worth pinning.
    """

    TOKEN = "cti-fixture-pat-never-echo-this-back-to-the-caller-0123456789"

    @staticmethod
    def _response(status_code: int):
        return SimpleNamespace(status_code=status_code)

    async def _call(self, body=None, *, stored=None, response=None, transport_error=None):
        """Drive the route with the settings lookup and the HTTP call both stubbed."""
        from src.web.routes import settings as settings_module

        stored = stored or {}

        async def fake_read(key: str):
            return stored.get(key)

        class FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                FakeClient.last_url = url
                FakeClient.last_headers = headers
                if transport_error:
                    raise transport_error
                return response

        with patch.object(settings_module, "_read_setting_value", side_effect=fake_read):
            with patch("httpx.AsyncClient", FakeClient):
                result = await settings_module.test_github_connection(body)
        return result, FakeClient

    @pytest.mark.asyncio
    async def test_reports_not_configured_when_no_token_is_stored(self):
        result, _ = await self._call(stored={"GITHUB_REPO": "owner/repo"})

        assert result["valid"] is False
        assert "no github token" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_rejects_a_repo_that_is_not_owner_slash_repo(self):
        result, _ = await self._call(stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "justarepo"})

        assert result["valid"] is False
        assert "owner/repo" in result["message"]

    @pytest.mark.asyncio
    async def test_uses_the_stored_token_without_returning_it(self):
        """The whole point of moving this server-side: the token stays here."""
        result, client = await self._call(
            stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"},
            response=self._response(200),
        )

        assert result == {"valid": True, "message": "Connected"}
        assert self.TOKEN not in json.dumps(result)
        # The stored token is what was actually sent upstream.
        assert client.last_headers["Authorization"] == f"token {self.TOKEN}"
        assert client.last_url.endswith("/repos/owner/repo")

    @pytest.mark.asyncio
    async def test_an_inline_token_is_preferred_over_the_stored_one(self):
        """Lets an operator verify a freshly pasted PAT before saving it."""
        _, client = await self._call(
            body=_github_test_body(token="cti-fixture-typed-but-not-yet-saved"),
            stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"},
            response=self._response(200),
        )

        assert client.last_headers["Authorization"] == "token cti-fixture-typed-but-not-yet-saved"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status_code,fragment",
        [
            (401, "invalid"),
            (404, "not found"),
            (500, "500"),
        ],
    )
    async def test_maps_github_status_codes_to_actionable_messages(self, status_code, fragment):
        result, _ = await self._call(
            stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"},
            response=self._response(status_code),
        )

        assert result["valid"] is False
        assert fragment in result["message"].lower()

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_reported_not_raised(self):
        """A dead network must not surface as a 500 from a connection test."""
        result, _ = await self._call(
            stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"},
            response=None,
            transport_error=OSError("name resolution failed"),
        )

        assert result["valid"] is False
        assert "could not reach github" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_no_branch_leaks_the_token(self):
        """Sweep every outcome: none of them may put credential material in the body."""
        cases = [
            dict(stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"}, response=self._response(200)),
            dict(stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"}, response=self._response(401)),
            dict(stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"}, response=self._response(404)),
            dict(stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "bad"}, response=None),
            dict(
                stored={"GITHUB_TOKEN": self.TOKEN, "GITHUB_REPO": "owner/repo"},
                response=None,
                transport_error=OSError("boom"),
            ),
        ]
        for case in cases:
            result, _ = await self._call(**case)
            assert self.TOKEN not in json.dumps(result), case
