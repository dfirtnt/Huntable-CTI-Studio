"""
API endpoints for managing application settings.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.database.async_manager import async_db_manager
from src.database.models import AppSettingsTable
from src.services.audit_service import (
    ACTION_SETTINGS_SECRET_UPDATED,
    ACTION_SETTINGS_UPDATED,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
    build_actor_context,
    is_sensitive_audit_key,
    redacted_secret_change,
)
from src.services.codex_app_server_client import CodexAppServerClient, CodexAppServerError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Whoever runs this deployment is its administrator, so the failure messages carry
# the command instead of telling the operator to go find someone. --device-auth is
# the flag that matters: plain `codex login` waits on a browser callback bound
# inside the container, which the host browser cannot reach.
CODEX_LOGIN_COMMAND = "docker compose exec workflow_worker codex login --device-auth"
CODEX_NOT_LOGGED_IN_MESSAGE = f"Codex is not logged in. Run: {CODEX_LOGIN_COMMAND}"
CODEX_WRONG_AUTH_MESSAGE = f"Codex is logged in, but not with a ChatGPT subscription. Run: {CODEX_LOGIN_COMMAND}"
CODEX_UNREACHABLE_MESSAGE = f"Codex app-server could not be reached. If it is not logged in, run: {CODEX_LOGIN_COMMAND}"


@router.post("/codex/test")
async def test_codex_subscription():
    """Test the deployment-managed Codex login without invoking a workflow model."""
    try:
        result = await CodexAppServerClient(timeout=15.0).read_account()
    except CodexAppServerError as exc:
        logger.warning("Codex subscription test failed: %s", exc)
        return {
            "valid": False,
            "message": CODEX_UNREACHABLE_MESSAGE,
        }

    account = result.get("account") if isinstance(result, dict) else None
    if not isinstance(account, dict):
        # A logged-out app-server answers {"account": null, "requiresOpenaiAuth": true},
        # so a missing account means "not logged in" and must not fall through to the
        # wrong-auth branch. Older shapes put the account fields at the top level, which
        # is only assumed when one of those fields is actually present.
        account = result if isinstance(result, dict) and ("type" in result or "authMode" in result) else None
    if account is None:
        return {
            "valid": False,
            "message": CODEX_NOT_LOGGED_IN_MESSAGE,
        }

    auth_mode = account.get("type") or account.get("authMode")
    plan_type = account.get("planType")
    if auth_mode != "chatgpt":
        return {
            "valid": False,
            "message": CODEX_WRONG_AUTH_MESSAGE,
        }
    message = "Codex subscription is ready"
    if isinstance(plan_type, str) and plan_type:
        message += f" ({plan_type})"
    return {"valid": True, "message": message, "plan_type": plan_type}


class GitHubConnectionTest(BaseModel):
    """Optional overrides so a freshly typed token can be tested before it is saved."""

    token: str | None = None
    repo: str | None = None


@router.post("/github/test")
async def test_github_connection(body: GitHubConnectionTest | None = None):
    """Test the stored GitHub PAT against the configured repo, server-side.

    The browser used to call api.github.com directly with the PAT read back out of
    GET /api/settings/GITHUB_TOKEN. That read no longer returns the token (and the
    cross-origin call is a standing connect-src violation), so the request is made
    here instead. The token never has to reach the page to be verified.
    """
    import httpx

    overrides = body or GitHubConnectionTest()
    token = (overrides.token or "").strip() or await _read_setting_value("GITHUB_TOKEN")
    repo = (overrides.repo or "").strip() or await _read_setting_value("GITHUB_REPO")

    if not token:
        return {"valid": False, "message": "No GitHub token is configured. Enter one and save first."}
    if not repo or "/" not in repo:
        return {"valid": False, "message": "Set the repository as owner/repo first."}

    owner, _, repo_name = repo.partition("/")
    try:
        # follow_redirects stays off explicitly: this request carries the PAT in an
        # Authorization header, and a followed redirect would carry it to whatever
        # host the response named. httpx defaults to False, but a token-bearing
        # request should not depend on a library default staying put.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            )
    except Exception as exc:
        logger.warning("GitHub connection test failed to reach api.github.com: %s", exc)
        return {"valid": False, "message": "Could not reach GitHub -- try again."}

    if response.status_code == 200:
        return {"valid": True, "message": "Connected"}
    if response.status_code == 401:
        return {"valid": False, "message": "Token is invalid or lacks repo access"}
    if response.status_code == 404:
        return {"valid": False, "message": "Repository not found, or the token cannot see it"}
    return {"valid": False, "message": f"GitHub returned {response.status_code}"}


class SettingUpdate(BaseModel):
    """Request model for updating a setting."""

    key: str
    value: str | None = None


class SettingsBulkUpdate(BaseModel):
    """Request model for bulk update."""

    settings: dict[str, str | None]


# Env keys merged into GET /api/settings so start.sh "proceed without LMStudio" is visible to UI
_SETTINGS_ENV_OVERRIDE_KEYS = ("WORKFLOW_LMSTUDIO_ENABLED", "PROCEED_WITHOUT_LMSTUDIO")
# Optional LM Studio LLM URL: merged from env so Settings can override .env.
_LMSTUDIO_URL_KEYS = ("LMSTUDIO_API_URL",)
# Langfuse credential keys: changing any of these must reset the in-memory client singleton
_LANGFUSE_KEYS = frozenset({"LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"})
_SENSITIVE_KEYS = frozenset(
    {
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "HUGGINGFACE_API_TOKEN",
        "WORKFLOW_OPENAI_API_KEY",
        "WORKFLOW_ANTHROPIC_API_KEY",
        "LANGFUSE_SECRET_KEY",
    }
)


def _is_sensitive_setting(key: str) -> bool:
    # Delegates to audit_service's broader definition (covers PASSWORD/CREDENTIAL/etc,
    # not just TOKEN/SECRET/API_KEY) so this module can't silently under-redact a
    # setting key that audit_service itself would treat as sensitive.
    normalized = key.upper()
    return normalized in _SENSITIVE_KEYS or is_sensitive_audit_key(key)


def _secret_hint(value: str | None) -> str | None:
    """Short "is this the credential I think it is" marker -- never the credential.

    Same shape the audit path already logs, so a hint in an API response and a hint
    in the audit trail are comparable by eye.
    """
    if not value:
        return None
    return f"{value[:8]}...({len(value)} chars)"


def _safe_log_value(key: str, value: str | None) -> str | None:
    """Value rendered for logs: hinted when the key is sensitive, verbatim otherwise."""
    if _is_sensitive_setting(key) and value:
        return _secret_hint(value)
    return value


def _sensitive_read_meta(key: str, value: str | None) -> dict[str, Any]:
    """The only thing a client is told about a stored secret: whether one is set.

    Reading a secret back is never required in order to replace it, so no read
    route returns `value` for a sensitive key -- it returns None, and the caller
    decides what to render from `configured`/`hint`. None (rather than the hint
    string) matters: callers that pass `settings[key]` straight to a provider
    must fail their own truthiness check, not ship eight characters of a key.
    """
    return {"configured": bool(value), "hint": _secret_hint(value)}


async def _read_setting_value(key: str) -> str | None:
    """Resolve a stored setting server-side, falling back to the environment.

    Server-side resolution is what lets the read routes stop handing secrets to the
    browser: anything that needs a credential in order to *do* something now reads
    it here instead of receiving it from the page.
    """
    from sqlalchemy import select

    try:
        async with async_db_manager.get_session() as session:
            result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == key))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return setting.value
    except Exception as exc:
        logger.warning("Could not read setting %s from the database: %s", key, exc)
    return os.environ.get(key) or None


def _redact_settings_map(raw: dict[str, str | None]) -> tuple[dict[str, str | None], dict[str, Any]]:
    """Split a key->value map into a client-safe map plus per-secret metadata."""
    safe: dict[str, str | None] = {}
    sensitive: dict[str, Any] = {}
    for key, value in raw.items():
        if _is_sensitive_setting(key):
            safe[key] = None
            sensitive[key] = _sensitive_read_meta(key, value)
        else:
            safe[key] = value
    return safe, sensitive


def _setting_audit_event(
    *,
    request: Request | None,
    key: str,
    old_value: str | None,
    new_value: str | None,
    deleted: bool = False,
) -> AuditEvent:
    sensitive = _is_sensitive_setting(key)
    action = ACTION_SETTINGS_SECRET_UPDATED if sensitive else ACTION_SETTINGS_UPDATED
    metadata = (
        redacted_secret_change(key, old_value=old_value, new_value=new_value)
        if sensitive
        else {
            "key": key,
            "old_value": old_value,
            "new_value": new_value,
            "deleted": deleted,
        }
    )
    verb = "Deleted" if deleted else "Updated"
    return AuditEvent(
        action=action,
        target_type="setting",
        target_id=key,
        status=STATUS_SUCCESS,
        summary=f"{verb} setting {key}",
        actor=build_actor_context(getattr(request.state, "identity", None) if request else None, request),
        metadata=metadata,
    )


@router.get("")
async def get_all_settings():
    """Get all application settings. Merges allowlisted env vars (e.g. from start.sh) over DB."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select

            result = await session.execute(select(AppSettingsTable))
            settings = result.scalars().all()
            out = {setting.key: setting.value for setting in settings}
            for key in _SETTINGS_ENV_OVERRIDE_KEYS:
                val = os.environ.get(key)
                if val is not None:
                    out[key] = val
            for key in _LMSTUDIO_URL_KEYS:
                if key not in out:
                    val = os.environ.get(key)
                    if val is not None:
                        out[key] = val
            safe, sensitive = _redact_settings_map(out)
            return JSONResponse(
                content={"success": True, "settings": safe, "sensitive": sensitive},
                headers={"Cache-Control": "no-store"},
            )

    except Exception as e:
        logger.error(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{key}")
async def get_setting(key: str):
    """Get a specific setting by key."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import select

            result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == key))
            setting = result.scalar_one_or_none()

            sensitive = _is_sensitive_setting(key)

            if not setting:
                payload: dict[str, Any] = {
                    "success": True,
                    "key": key,
                    "value": None,
                    "exists": False,
                    "sensitive": sensitive,
                    "configured": False,
                    "hint": None,
                }
            else:
                payload = {
                    "success": True,
                    "key": setting.key,
                    # A sensitive value is never returned; `configured`/`hint` carry the
                    # only information a client legitimately needs about it.
                    "value": None if sensitive else setting.value,
                    "description": setting.description,
                    "category": setting.category,
                    "exists": True,
                    "sensitive": sensitive,
                    "configured": bool(setting.value),
                    "hint": _secret_hint(setting.value) if sensitive else None,
                }

            # Matches the sibling list route: this is the route individual secrets are
            # read through, so its responses must not sit in any cache.
            return JSONResponse(content=payload, headers={"Cache-Control": "no-store"})

    except Exception as e:
        logger.error(f"Error fetching setting {key}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("")
async def update_setting(update: SettingUpdate, request: Request):
    """Update or create a setting."""
    try:
        async with async_db_manager.get_session() as session:
            from datetime import datetime

            from sqlalchemy import select

            # Check if setting exists
            result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == update.key))
            setting = result.scalar_one_or_none()

            old_value = setting.value if setting else None
            if setting:
                # Update existing setting
                setting.value = update.value
                setting.updated_at = datetime.now()
                logger.info(f"Updated setting: {update.key} = {_safe_log_value(update.key, update.value)}")
            else:
                # Create new setting
                setting = AppSettingsTable(
                    key=update.key,
                    value=update.value,
                    category="user",  # User-created settings
                )
                session.add(setting)
                logger.info(f"Created new setting: {update.key} = {_safe_log_value(update.key, update.value)}")

            await AsyncAuditService.record_mandatory(
                session,
                _setting_audit_event(
                    request=request,
                    key=update.key,
                    old_value=old_value,
                    new_value=update.value,
                ),
            )
            await session.commit()

            if update.key in _LMSTUDIO_URL_KEYS and update.value:
                os.environ[update.key] = update.value
            elif update.key in _LMSTUDIO_URL_KEYS and not update.value:
                os.environ.pop(update.key, None)

            if update.key in _LANGFUSE_KEYS:
                from src.utils.langfuse_client import reset_langfuse_client

                reset_langfuse_client()
                logger.info("Langfuse client reset after %s update", update.key)

            # Echoing the value back would re-open the read path this module just closed.
            return {
                "success": True,
                "key": update.key,
                "value": None if _is_sensitive_setting(update.key) else update.value,
                "sensitive": _is_sensitive_setting(update.key),
                "configured": bool(update.value),
                "message": "Setting updated successfully",
            }

    except Exception as e:
        logger.error(f"Error updating setting {update.key}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/bulk")
async def update_settings_bulk(update: SettingsBulkUpdate, request: Request):
    """Update multiple settings at once."""
    try:
        async with async_db_manager.get_session() as session:
            from datetime import datetime

            from sqlalchemy import select

            updated_keys = []
            errors = []

            for key, value in update.settings.items():
                try:
                    # Check if setting exists
                    result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == key))
                    setting = result.scalar_one_or_none()
                    old_value = setting.value if setting else None

                    if setting:
                        # Update existing
                        setting.value = value
                        setting.updated_at = datetime.now()
                    else:
                        # Create new
                        setting = AppSettingsTable(key=key, value=value, category="user")
                        session.add(setting)

                    updated_keys.append(key)
                    await AsyncAuditService.record_mandatory(
                        session,
                        _setting_audit_event(
                            request=request,
                            key=key,
                            old_value=old_value,
                            new_value=value,
                        ),
                    )

                except Exception as e:
                    logger.error(f"Error updating setting {key}: {e}")
                    errors.append(f"{key}: {str(e)}")

            await session.commit()

            for key in _LMSTUDIO_URL_KEYS:
                val = update.settings.get(key)
                if val:
                    os.environ[key] = val
                elif key in update.settings:
                    os.environ.pop(key, None)

            if _LANGFUSE_KEYS & set(updated_keys):
                from src.utils.langfuse_client import reset_langfuse_client

                reset_langfuse_client()
                logger.info("Langfuse client reset after bulk settings update")

            logger.info(f"Bulk update completed: {len(updated_keys)} settings updated")

            return {
                "success": len(errors) == 0,
                "updated_keys": updated_keys,
                "errors": errors,
                "message": f"Updated {len(updated_keys)} settings",
            }

    except Exception as e:
        logger.error(f"Error in bulk update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/{key}")
async def delete_setting(key: str, request: Request):
    """Delete a setting (revert to environment variable)."""
    try:
        async with async_db_manager.get_session() as session:
            from sqlalchemy import delete, select

            # Check if setting exists
            result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == key))
            setting = result.scalar_one_or_none()

            if not setting:
                raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

            old_value = setting.value
            # Delete the setting
            await session.execute(delete(AppSettingsTable).where(AppSettingsTable.key == key))
            await AsyncAuditService.record_mandatory(
                session,
                _setting_audit_event(
                    request=request,
                    key=key,
                    old_value=old_value,
                    new_value=None,
                    deleted=True,
                ),
            )
            await session.commit()

            logger.info(f"Deleted setting: {key}")

            return {
                "success": True,
                "key": key,
                "message": "Setting deleted successfully (will revert to environment variable)",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting setting {key}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e
