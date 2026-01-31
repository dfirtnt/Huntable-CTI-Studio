"""
AI-powered article analysis endpoints.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.services.provider_model_catalog import load_catalog, update_provider_models
from src.utils.prompt_loader import format_prompt
from src.web.dependencies import logger

router = APIRouter(prefix="/api/articles", tags=["Articles", "AI"])

# Test API key endpoints (separate router for correct URL paths)
test_router = APIRouter(prefix="/api", tags=["AI", "Testing"])

OPENAI_MODEL_PATTERN = re.compile(
    r"^(gpt|o\d|o[1-9]|o-|o[a-z]|omni|text-davinci|davinci|curie|babbage|ada)",
    re.IGNORECASE,
)


def _filter_openai_models(model_ids: list[str]) -> list[str]:
    filtered = [model_id for model_id in model_ids if OPENAI_MODEL_PATTERN.match(model_id)]
    return sorted(set(filtered))


def _filter_anthropic_models(model_ids: list[str]) -> list[str]:
    return sorted({model_id for model_id in model_ids if model_id.lower().startswith("claude")})


def _filter_gemini_models(model_ids: list[str]) -> list[str]:
    cleaned = []
    for model_id in model_ids:
        if not model_id:
            continue
        normalized = model_id.split("/")[-1]
        if normalized.lower().startswith("gemini"):
            cleaned.append(normalized)
    return sorted(set(cleaned))


async def _fetch_openai_models(api_key: str) -> list[str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.openai.com/v1/models", headers=headers, timeout=20.0)
        if response.status_code != 200:
            logger.warning(f"OpenAI models API returned {response.status_code}: {response.text[:200]}")
            return []
        data = response.json()
        models = [item.get("id", "") for item in data.get("data", []) if item.get("id")]
        return _filter_openai_models(models)
    except httpx.HTTPError as exc:
        logger.warning(f"Failed to fetch OpenAI models: {exc}")
        return []


async def _fetch_anthropic_models(api_key: str) -> list[str]:
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    params = {"limit": 200}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.anthropic.com/v1/models", headers=headers, params=params, timeout=20.0
            )
        if response.status_code != 200:
            logger.warning(f"Anthropic models API returned {response.status_code}: {response.text[:200]}")
            return []
        data = response.json()
        models = []
        payload = data.get("data") or data.get("models") or []
        for item in payload:
            if isinstance(item, dict):
                candidate = item.get("id") or item.get("model") or item.get("name")
                if candidate:
                    models.append(candidate)
        return _filter_anthropic_models(models)
    except httpx.HTTPError as exc:
        logger.warning(f"Failed to fetch Anthropic models: {exc}")
        return []


async def _fetch_gemini_models(api_key: str) -> list[str]:
    params = {"key": api_key}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models", params=params, timeout=20.0
            )
        if response.status_code != 200:
            logger.warning(f"Gemini models API returned {response.status_code}: {response.text[:200]}")
            return []
        data = response.json()
        models = []
        for item in data.get("models", []):
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    models.append(name)
        return _filter_gemini_models(models)
    except httpx.HTTPError as exc:
        logger.warning(f"Failed to fetch Gemini models: {exc}")
        return []


async def _refresh_provider_catalog(provider: str, api_key: str) -> dict[str, list[str]]:
    fetcher_map = {
        "openai": _fetch_openai_models,
        "anthropic": _fetch_anthropic_models,
        "gemini": _fetch_gemini_models,
    }
    fetcher = fetcher_map.get(provider)
    if not fetcher:
        return {}

    models = await fetcher(api_key)
    if not models:
        return {}

    catalog = update_provider_models(provider, models)
    return {"models": models, "catalog": catalog}


async def _call_anthropic_with_retry(
    api_key: str,
    payload: dict[str, Any],
    anthropic_api_url: str = "https://api.anthropic.com/v1/messages",
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout: float = 60.0,
) -> httpx.Response:
    """
    Call Anthropic Claude API with exponential backoff rate limit handling.

    Args:
        api_key: Anthropic API key
        payload: Request payload (model, messages, etc.)
        anthropic_api_url: Anthropic API endpoint URL
        max_retries: Maximum retry attempts
        base_delay: Base delay for exponential backoff (seconds)
        max_delay: Maximum delay cap (seconds)
        timeout: Request timeout in seconds

    Returns:
        Successful httpx.Response (status_code == 200)

    Raises:
        HTTPException: If all retries exhausted or non-retryable error
    """
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }

    def _parse_retry_after(retry_after_header: str | None) -> float:
        """Parse retry-after header (seconds or HTTP date)."""
        if not retry_after_header:
            return 30.0
        try:
            return float(retry_after_header.strip())
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(retry_after_header)
                now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                delta = retry_date - now
                return max(0.0, delta.total_seconds())
            except (ValueError, TypeError):
                logger.warning(f"Could not parse retry-after header: {retry_after_header}, using 30s default")
                return 30.0

    last_exception = None

    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(anthropic_api_url, headers=headers, json=payload, timeout=timeout)

                # Success
                if response.status_code == 200:
                    return response

                # Rate limit (429) - retry with exponential backoff
                if response.status_code == 429:
                    retry_after = _parse_retry_after(response.headers.get("retry-after"))
                    delay = max(retry_after, base_delay * (2**attempt))
                    delay = min(delay, max_delay)

                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Anthropic API rate limited (429). "
                            f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s. "
                            f"Retry-After header: {retry_after}s"
                        )
                        await asyncio.sleep(delay)
                        continue
                    error_detail = response.text
                    logger.error(f"Anthropic API rate limit exceeded after {max_retries} attempts: {error_detail}")
                    raise HTTPException(
                        status_code=429,
                        detail=f"Anthropic API rate limit exceeded: {error_detail}",
                    )

                # Other errors - retry with exponential backoff for 5xx, fail fast for 4xx
                if 500 <= response.status_code < 600:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        error_detail = response.text
                        logger.warning(
                            f"Anthropic API server error ({response.status_code}). "
                            f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {error_detail}"
                        )
                        await asyncio.sleep(delay)
                        continue

                # Client errors (4xx) - don't retry
                error_detail = response.text
                logger.error(f"Anthropic API client error ({response.status_code}): {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Anthropic API error: {error_detail}",
                )

            except httpx.TimeoutException as e:
                delay = min(base_delay * (2**attempt), max_delay)
                if attempt < max_retries - 1:
                    logger.warning(f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                raise HTTPException(
                    status_code=504,
                    detail=f"Anthropic API timeout after {max_retries} attempts",
                ) from e

            except Exception as e:
                delay = min(base_delay * (2**attempt), max_delay)
                if attempt < max_retries - 1:
                    logger.warning(f"Anthropic API error: {e}. Retry {attempt + 1}/{max_retries} after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    last_exception = e
                    continue
                raise HTTPException(
                    status_code=500,
                    detail=f"Anthropic API error after {max_retries} attempts: {str(e)}",
                ) from e

    # Should not reach here, but handle edge case
    if last_exception:
        raise HTTPException(status_code=500, detail=f"Anthropic API failed after {max_retries} attempts")
    raise HTTPException(status_code=500, detail=f"Anthropic API failed after {max_retries} attempts")


def _get_lmstudio_settings() -> dict[str, Any]:
    """
    Get recommended LMStudio settings for deterministic scoring.

    Settings can be overridden via environment variables:
    - LMSTUDIO_TEMPERATURE (default: 0.0 for deterministic scoring)
    - LMSTUDIO_TOP_P (default: 0.9)
    - LMSTUDIO_SEED (default: 42 for deterministic scoring)

    Note: Quantization (Q4_K_M, Q6_K, Q8_0) must be set in LMStudio UI
    when loading the model - cannot be controlled via API.
    """
    return {
        "temperature": float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0")),
        "top_p": float(os.getenv("LMSTUDIO_TOP_P", "0.9")),
        "seed": int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None,
    }


def _lmstudio_url_candidates() -> list[str]:
    """
    Generate ordered LMStudio base URL candidates.
    Ensures compatibility whether LMSTUDIO_API_URL includes /v1 or not.
    """
    raw_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1").strip()
    if not raw_url:
        raw_url = "http://host.docker.internal:1234/v1"

    normalized = raw_url.rstrip("/")
    candidates: list[str] = [normalized]

    if not normalized.lower().endswith("/v1"):
        candidates.append(f"{normalized}/v1")

    # If URL contains localhost, also try host.docker.internal (for Docker containers)
    if "localhost" in normalized.lower() or "127.0.0.1" in normalized:
        docker_url = normalized.replace("localhost", "host.docker.internal").replace(
            "127.0.0.1", "host.docker.internal"
        )
        if docker_url not in candidates:
            candidates.append(docker_url)
        # Also try with /v1 if not already there
        if not docker_url.lower().endswith("/v1"):
            docker_url_v1 = f"{docker_url}/v1"
            if docker_url_v1 not in candidates:
                candidates.append(docker_url_v1)

    # Preserve order while removing duplicates
    seen = set()
    unique_candidates = []
    for candidate in candidates:
        if candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)
    return unique_candidates


async def _post_lmstudio_chat(
    payload: dict,
    *,
    model_name: str,
    timeout: float,
    failure_context: str,
) -> dict:
    """
    Call LMStudio /chat/completions with automatic fallback handling.

    Args:
        payload: JSON payload to send to LMStudio.
        model_name: Name of the LMStudio model (for logging).
        timeout: Request timeout in seconds.
        failure_context: Contextual message for raised HTTPException.

    Returns:
        Parsed JSON response from LMStudio.
    """
    lmstudio_urls = _lmstudio_url_candidates()
    last_error_detail = ""

    async with httpx.AsyncClient() as client:
        for idx, lmstudio_url in enumerate(lmstudio_urls):
            logger.info(
                f"Attempting LMStudio at {lmstudio_url} with model {model_name} "
                f"({failure_context}) attempt {idx + 1}/{len(lmstudio_urls)}"
            )
            try:
                # For LM Studio, read timeout must be long enough to allow prompt processing
                # before any response data is sent.
                read_timeout = 600.0
                response = await client.post(
                    f"{lmstudio_url}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=httpx.Timeout(timeout, connect=30.0, read=read_timeout),
                )
            except httpx.TimeoutException:
                last_error_detail = f"Timeout connecting to {lmstudio_url}"
                if idx == len(lmstudio_urls) - 1:
                    # Last URL, raise timeout error
                    raise HTTPException(
                        status_code=408,
                        detail="LMStudio request timeout - the model may be slow or overloaded",
                    )
                # Try next URL
                logger.warning(f"LMStudio timeout at {lmstudio_url}, trying next URL...")
                continue
            except httpx.ConnectError as e:
                last_error_detail = f"Cannot connect to {lmstudio_url}: {str(e)}"
                if idx == len(lmstudio_urls) - 1:
                    # Last URL, raise connection error
                    raise HTTPException(
                        status_code=503,
                        detail=f"Cannot connect to LMStudio service. Please ensure LMStudio is running and accessible. Tried: {', '.join(lmstudio_urls)}. Last error: {str(e)}",
                    )
                # Try next URL
                logger.warning(f"LMStudio connection failed at {lmstudio_url}, trying next URL...")
                continue
            except Exception as e:  # pragma: no cover - defensive logging
                last_error_detail = f"Error at {lmstudio_url}: {str(e)}"
                logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                if idx == len(lmstudio_urls) - 1:
                    raise HTTPException(
                        status_code=500,
                        detail=f"{failure_context}: {str(e)}",
                    )
                # Try next URL
                continue

            if response.status_code == 200:
                if idx > 0:
                    logger.info(f"LMStudio request succeeded using fallback URL {lmstudio_url}")
                return response.json()

            # Improved error detail extraction
            error_text = response.text
            try:
                error_json = response.json()
                error_message = (
                    error_json.get("error", {}).get("message", error_text)
                    if isinstance(error_json.get("error"), dict)
                    else error_text
                )
            except:
                error_message = error_text

            last_error_detail = f"{response.status_code} - {error_message}"
            logger.error(f"LMStudio API error ({failure_context}) at {lmstudio_url}: {last_error_detail}")
            logger.error(f"Full response body: {error_text}")

            if response.status_code == 404 and idx < len(lmstudio_urls) - 1:
                logger.warning(
                    "LMStudio endpoint returned 404. "
                    "This often means LMSTUDIO_API_URL is missing the '/v1' suffix. "
                    "Retrying with fallback URL."
                )
                continue

            # Check for common errors that indicate LMStudio isn't ready
            error_lower = error_message.lower()
            if response.status_code == 400 and (
                "context length" in error_lower
                or "model" in error_lower
                and "not loaded" in error_lower
                or "no model" in error_lower
            ):
                raise HTTPException(
                    status_code=500,
                    detail="LMStudio is not ready. Please ensure LMStudio is running and a model is loaded.",
                )

            # Include the actual error message in the exception
            raise HTTPException(
                status_code=500,
                detail=f"{failure_context}: {response.status_code} - {error_message[:200]}",
            )

    raise HTTPException(
        status_code=500,
        detail=f"{failure_context}: {last_error_detail or 'Unknown LMStudio error'}",
    )


@test_router.post("/test-openai-key")
async def api_test_openai_key(request: Request):
    """Test OpenAI API key validity."""
    try:
        body = await request.json()
        api_key_raw = body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None

        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")

        # Validate API key format - OpenAI keys start with sk- and should be reasonable length
        if not api_key.startswith("sk-"):
            logger.error(
                f"❌ API key validation failed: does not start with 'sk-' (length: {len(api_key) if api_key else 0})"
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid API key format. OpenAI keys should start with 'sk-'",
            )
        if len(api_key) < 20:
            logger.error(f"❌ API key validation failed: too short (length: {len(api_key)})")
            raise HTTPException(
                status_code=400,
                detail="API key appears to be truncated or invalid (too short)",
            )

        # Log key info for debugging (masked)
        logger.info(
            f"🔑 Testing OpenAI API key: length={len(api_key)}, starts_with={api_key[:8]}..., ends_with=...{api_key[-4:]}"
        )

        # Test the API key with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5,
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                refresh_result = await _refresh_provider_catalog("openai", api_key)
                return {
                    "valid": True,
                    "message": "API key is valid",
                    "models": refresh_result.get("models"),
                    "catalog": refresh_result.get("catalog"),
                }
            if response.status_code == 401:
                # Try to extract more details from the error
                try:
                    error_json = response.json()
                    error_message = error_json.get("error", {}).get("message", "Invalid API key")
                    logger.error(f"❌ OpenAI API key test failed: {error_message}")
                    return {
                        "valid": False,
                        "message": f"Invalid API key: {error_message}",
                    }
                except:
                    logger.error(f"❌ OpenAI API key test failed with 401, response: {response.text}")
                    return {"valid": False, "message": "Invalid API key"}
            else:
                return {"valid": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        logger.error(f"OpenAI API key test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@test_router.post("/test-anthropic-key")
async def api_test_anthropic_key(request: Request):
    """Test Anthropic API key validity."""
    try:
        body = await request.json()
        api_key_raw = body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None

        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")

        # Test the API key with a simple request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": "Hello"}],
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                refresh_result = await _refresh_provider_catalog("anthropic", api_key)
                return {
                    "valid": True,
                    "message": "API key is valid",
                    "models": refresh_result.get("models"),
                    "catalog": refresh_result.get("catalog"),
                }
            if response.status_code == 401:
                return {"valid": False, "message": "Invalid API key"}
            return {"valid": False, "message": f"API error: {response.status_code}"}

    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        logger.error(f"Anthropic API key test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@test_router.post("/test-gemini-key")
async def api_test_gemini_key(request: Request):
    """Test Gemini API key validity by listing available models."""
    try:
        body = await request.json()
        api_key = (body.get("api_key") or "").strip()
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")

        models = await _fetch_gemini_models(api_key)
        if models:
            catalog = update_provider_models("gemini", models)
            return {
                "valid": True,
                "message": f"API key is valid. Retrieved {len(models)} models.",
                "models": models,
                "catalog": catalog,
            }
        raise HTTPException(status_code=400, detail="Unable to fetch Gemini models with provided key")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as exc:
        logger.error(f"Gemini API key test error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def _get_hf_token() -> str | None:
    """Load Hugging Face token from AppSettings or environment."""
    token = None
    try:
        from sqlalchemy import select

        from src.database.models import AppSettingsTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                select(AppSettingsTable).where(AppSettingsTable.key == "HUGGINGFACE_API_TOKEN")
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                token = setting.value.strip() or None
    except Exception as exc:
        logger.warning(f"Unable to load Hugging Face token from AppSettings: {exc}")

    if token:
        return token

    for env_var in ("HUGGINGFACE_API_TOKEN", "HF_API_TOKEN", "HUGGINGFACE_HUB_TOKEN"):
        env_val = os.getenv(env_var)
        if env_val:
            return env_val
    return None


@test_router.post("/test-hf-key")
async def api_test_hf_key(request: Request):
    """Validate a Hugging Face access token (used for gated models like CMDCaliper)."""
    try:
        body = await request.json()
        token_raw = body.get("api_key")
        token = token_raw.strip() if token_raw else None

        if not token:
            raise HTTPException(status_code=400, detail="Hugging Face token is required")

        if not token.startswith("hf_"):
            raise HTTPException(
                status_code=400,
                detail="Hugging Face tokens typically start with 'hf_'",
            )

        masked = f"{token[:6]}...{token[-4:]}" if len(token) > 12 else "***"
        logger.info(f"🔑 Testing Hugging Face token (masked): {masked}")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )

        if response.status_code == 200:
            data = response.json()
            username = data.get("name") or data.get("email") or "Hugging Face user"
            orgs = data.get("orgs") or []
            gated_orgs = [org.get("name") for org in orgs if isinstance(org, dict) and org.get("name")]
            message_parts = [f"Token valid for {username}"]
            if gated_orgs:
                message_parts.append(f"Orgs: {', '.join(gated_orgs)}")
            return {
                "valid": True,
                "message": "; ".join(message_parts),
                "username": username,
                "orgs": gated_orgs,
            }

        if response.status_code in {401, 403}:
            raise HTTPException(
                status_code=response.status_code,
                detail="Unauthorized: token rejected or missing access to the requested repository",
            )

        detail = response.text[:200] if response.text else "Unknown Hugging Face error"
        logger.warning(f"Hugging Face token validation failed: {response.status_code} - {detail}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Hugging Face API returned {response.status_code}: {detail}",
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout when contacting Hugging Face API")
    except httpx.HTTPError as exc:
        logger.error(f"Hugging Face token validation HTTP error: {exc}")
        raise HTTPException(status_code=502, detail="Network error when contacting Hugging Face API")
    except Exception as exc:
        logger.error(f"Unexpected Hugging Face token validation error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to validate Hugging Face token")


async def _get_current_lmstudio_model() -> str:
    """
    Get the currently loaded model from LMStudio API.
    Priority: database setting > env var > LMStudio API query
    """
    # Check database setting first (highest priority - user preference from UI)
    try:
        from sqlalchemy import select

        from src.database.async_manager import async_db_manager
        from src.database.models import AppSettingsTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == "lmstudio_model"))
            setting = result.scalar_one_or_none()

            if setting and setting.value:
                logger.info(f"Using LMSTUDIO_MODEL from database setting: {setting.value}")
                return setting.value
    except Exception as e:
        logger.debug(f"Could not fetch lmstudio_model from database: {e}")

    # Fall back to environment variable (second priority)
    env_model = os.getenv("LMSTUDIO_MODEL")
    if env_model:
        logger.info(f"Using LMSTUDIO_MODEL from environment: {env_model}")
        return env_model

    # Fallback: try to get from API
    try:
        lmstudio_urls = _lmstudio_url_candidates()
        async with httpx.AsyncClient() as client:
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=5.0)
                except httpx.HTTPError as e:
                    logger.debug(f"LMStudio model lookup failed via {lmstudio_url}: {e}")
                    continue

                if response.status_code == 200:
                    models_data = response.json()
                    models = [model["id"] for model in models_data.get("data", [])]
                    if models:
                        # Filter for chat models only (exclude embedding models)
                        # Check for common embedding model patterns
                        def is_embedding_model(model_name: str) -> bool:
                            embedding_indicators = [
                                "embedding",
                                "embed",
                                "e5-base",
                                "bge-",
                                "gte-",
                            ]
                            return any(indicator in model_name.lower() for indicator in embedding_indicators)

                        chat_models = [m for m in models if not is_embedding_model(m)]
                        if chat_models:
                            logger.info(f"LMStudio chat model from API: {chat_models[0]}")
                            return chat_models[0]
                        # If no chat models, return first model
                        logger.warning(f"No chat models found, using first model: {models[0]}")
                        return models[0]
                elif response.status_code == 404 and idx < len(lmstudio_urls) - 1:
                    logger.warning(
                        f"LMStudio /models endpoint not found at {lmstudio_url}; retrying with alternate base URL"
                    )
                    continue
                else:
                    logger.debug(f"LMStudio /models request returned {response.status_code} from {lmstudio_url}")

    except Exception as e:
        logger.warning(f"Could not fetch current LMStudio model: {e}")

    # Final fallback
    return "llama-3.2-1b-instruct"


@test_router.get("/lmstudio-models")
async def api_get_lmstudio_models():
    """Get currently loaded models from LMStudio."""
    try:
        lmstudio_urls = _lmstudio_url_candidates()
        async with httpx.AsyncClient() as client:
            last_error = "Unknown LMStudio error"
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=10.0)
                except httpx.HTTPError as e:
                    last_error = str(e)
                    logger.debug(f"LMStudio models fetch failed via {lmstudio_url}: {e}")
                    continue

                if response.status_code == 200:
                    models_data = response.json()
                    all_models = [model["id"] for model in models_data.get("data", [])]

                    # Filter for chat models only (exclude embedding models)
                    # Check for common embedding model patterns
                    def is_embedding_model(model_name: str) -> bool:
                        embedding_indicators = [
                            "embedding",
                            "embed",
                            "e5-base",
                            "bge-",
                            "gte-",
                        ]
                        return any(indicator in model_name.lower() for indicator in embedding_indicators)

                    chat_models = [m for m in all_models if not is_embedding_model(m)]
                    embedding_models = [m for m in all_models if is_embedding_model(m)]

                    # Return chat models first, then embedding models for reference
                    models = chat_models if chat_models else all_models

                    if idx > 0:
                        logger.info(f"LMStudio models fetched using fallback URL {lmstudio_url}")

                    return {
                        "success": True,
                        "models": models,
                        "all_models": all_models,  # Include all models for debugging
                        "chat_models": chat_models,  # Chat models only
                        "embedding_models": embedding_models,  # Embedding models only
                        "chat_models_count": len(chat_models),
                        "embedding_models_count": len(embedding_models),
                        "message": f"Found {len(chat_models)} chat model(s) and {len(embedding_models)} embedding model(s)",
                    }

                last_error = f"{response.status_code}: {response.text}"
                logger.error(f"LMStudio /models returned {last_error}")

                if response.status_code == 404 and idx < len(lmstudio_urls) - 1:
                    logger.warning("LMStudio /models endpoint returned 404. Retrying with alternate base URL.")
                    continue

            return {
                "success": False,
                "models": [],
                "message": f"LMStudio API error: {last_error}",
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "models": [],
            "message": "Request timeout - LMStudio may be starting up",
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "models": [],
            "chat_models": [],
            "embedding_models": [],
            "message": "Cannot connect to LMStudio service",
        }
    except Exception as e:
        logger.error(f"LMStudio models fetch error: {e}")
        return {
            "success": False,
            "models": [],
            "chat_models": [],
            "embedding_models": [],
            "message": f"Error fetching models: {str(e)}",
        }


@test_router.get("/lmstudio-embedding-models")
async def api_get_lmstudio_embedding_models():
    """Get currently loaded embedding models from LMStudio."""
    try:
        lmstudio_urls = _lmstudio_url_candidates()
        async with httpx.AsyncClient() as client:
            last_error = "Unknown LMStudio error"
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=10.0)
                except httpx.HTTPError as e:
                    last_error = str(e)
                    logger.debug(f"LMStudio models fetch failed via {lmstudio_url}: {e}")
                    continue

                if response.status_code == 200:
                    models_data = response.json()
                    all_models = [model["id"] for model in models_data.get("data", [])]

                    # Filter for embedding models only
                    def is_embedding_model(model_name: str) -> bool:
                        embedding_indicators = [
                            "embedding",
                            "embed",
                            "e5-base",
                            "bge-",
                            "gte-",
                            "text-embedding",
                        ]
                        return any(indicator in model_name.lower() for indicator in embedding_indicators)

                    embedding_models = [m for m in all_models if is_embedding_model(m)]

                    if idx > 0:
                        logger.info(f"LMStudio embedding models fetched using fallback URL {lmstudio_url}")

                    return {
                        "success": True,
                        "models": embedding_models,
                        "count": len(embedding_models),
                        "message": f"Found {len(embedding_models)} embedding model(s)",
                    }

                last_error = f"{response.status_code}: {response.text}"
                logger.error(f"LMStudio /models returned {last_error}")

                if response.status_code == 404 and idx < len(lmstudio_urls) - 1:
                    logger.warning("LMStudio /models endpoint returned 404. Retrying with alternate base URL.")
                    continue

            return {
                "success": False,
                "models": [],
                "count": 0,
                "message": f"LMStudio API error: {last_error}",
            }

    except httpx.TimeoutException:
        return {
            "success": False,
            "models": [],
            "count": 0,
            "message": "Request timeout - LMStudio may be starting up",
        }
    except httpx.ConnectError:
        return {
            "success": False,
            "models": [],
            "count": 0,
            "message": "Cannot connect to LMStudio service",
        }
    except Exception as e:
        logger.error(f"LMStudio embedding models fetch error: {e}")
        return {
            "success": False,
            "models": [],
            "count": 0,
            "message": f"Error fetching embedding models: {str(e)}",
        }


@test_router.get("/provider-model-catalog")
async def api_get_provider_model_catalog():
    """Return cached provider model catalog."""
    return {"catalog": load_catalog()}


@test_router.post("/test-lmstudio-connection")
async def api_test_lmstudio_connection(request: Request):
    """Test LMStudio connection and model availability."""
    try:
        # Get the currently loaded model from LMStudio instead of env var
        # This ensures we test the actual model that's loaded, not what's in .env
        lmstudio_model = await _get_current_lmstudio_model()

        logger.info(f"Testing LMStudio connection with model: {lmstudio_model}")

        payload = {
            "model": lmstudio_model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5,
            "temperature": 0.1,
        }

        result = await _post_lmstudio_chat(
            payload,
            model_name=lmstudio_model,
            timeout=15.0,
            failure_context="LMStudio connection test failed",
        )

        response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "valid": True,
            "message": f"LMStudio connection successful. Model '{lmstudio_model}' responded: '{response_text.strip()}'",
        }

    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout - LMStudio may be starting up")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to LMStudio service")
    except Exception as e:
        logger.error(f"LMStudio connection test error: {e}")
        raise HTTPException(status_code=500, detail=f"LMStudio connection test failed: {str(e)}")


@test_router.post("/load-lmstudio-model")
async def api_load_lmstudio_model(request: Request):
    """Load a model in LMStudio using the CLI."""
    try:
        import shutil
        import subprocess

        body = await request.json()
        model_name = body.get("model_name")
        context_length = body.get("context_length", 16384)

        if not model_name:
            raise HTTPException(status_code=400, detail="model_name is required")

        # Find lms CLI
        lms_cmd = shutil.which("lms")
        if not lms_cmd:
            lms_path = os.path.expanduser("~/.cache/lm-studio/bin/lms")
            if os.path.exists(lms_path):
                lms_cmd = lms_path
            else:
                raise HTTPException(
                    status_code=503,
                    detail="LMStudio CLI not found. Install from https://lmstudio.ai/ or ensure it's in PATH: ~/.cache/lm-studio/bin/lms",
                )

        logger.info(f"Loading model {model_name} with context length {context_length}...")

        # Load model
        try:
            result = subprocess.run(
                [lms_cmd, "load", model_name, "--context-length", str(context_length), "--yes"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                # Wait a moment for model to be ready
                await asyncio.sleep(2)
                return {
                    "success": True,
                    "message": f"Model {model_name} loaded successfully",
                    "model_name": model_name,
                    "context_length": context_length,
                }
            error_output = result.stderr or result.stdout
            logger.error(f"Failed to load model: {error_output}")
            raise HTTPException(status_code=500, detail=f"Failed to load model: {error_output[:500]}")
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=504,
                detail="Timeout loading model (60s). Model may be too large or LMStudio may be unresponsive.",
            )
        except Exception as e:
            logger.error(f"Error loading model: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Error loading model: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Load model endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@test_router.post("/test-langfuse-connection")
async def api_test_langfuse_connection(request: Request):
    """Test Langfuse connection and configuration."""
    try:
        from sqlalchemy import select

        from src.database.models import AppSettingsTable

        async with async_db_manager.get_session() as session:
            # Get Langfuse settings from database (same priority as debug endpoint)
            async def _get_langfuse_setting(key: str, env_key: str, default: str | None = None) -> str | None:
                """Get Langfuse setting from database first, then fall back to environment variable."""
                # Check database setting first
                try:
                    result = await session.execute(select(AppSettingsTable).where(AppSettingsTable.key == key))
                    setting = result.scalar_one_or_none()
                    if setting and setting.value:
                        return setting.value
                except Exception as e:
                    logger.warning(f"Could not fetch {key} from database: {e}")

                # Fall back to environment variable
                env_value = os.getenv(env_key)
                if env_value:
                    return env_value

                return default

            public_key = await _get_langfuse_setting("LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY")
            secret_key = await _get_langfuse_setting("LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY")
            host = await _get_langfuse_setting("LANGFUSE_HOST", "LANGFUSE_HOST", "https://cloud.langfuse.com")
            project_id = await _get_langfuse_setting("LANGFUSE_PROJECT_ID", "LANGFUSE_PROJECT_ID")

            # Validate required settings
            if not public_key:
                return {
                    "valid": False,
                    "message": "Langfuse Public Key is required. Please configure it in Settings.",
                }

            if not secret_key:
                return {
                    "valid": False,
                    "message": "Langfuse Secret Key is required. Please configure it in Settings.",
                }

            # Try to initialize Langfuse client and validate keys with actual API call
            try:
                from langfuse import Langfuse
                from langfuse.api.client import AsyncFernLangfuse
                from langfuse.api.core.api_error import ApiError
                from langfuse.api.resources.commons.errors.access_denied_error import (
                    AccessDeniedError,
                )
                from langfuse.api.resources.commons.errors.unauthorized_error import (
                    UnauthorizedError,
                )
                from langfuse.types import TraceContext

                base_url = host.rstrip("/")

                # Validate the provided credentials against Langfuse's official API.
                # Using the Fern client guarantees we hit the correct endpoint and
                # get structured errors (401/403) instead of ambiguous responses.
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as fern_http_client:
                    fern_client = AsyncFernLangfuse(
                        base_url=base_url,
                        username=public_key,
                        password=secret_key,
                        x_langfuse_public_key=public_key,
                        x_langfuse_sdk_name="cti-scraper",
                        x_langfuse_sdk_version=os.getenv("APP_VERSION", "dev"),
                        httpx_client=fern_http_client,
                    )
                    try:
                        project_response = await fern_client.projects.get()
                    except UnauthorizedError:
                        return {
                            "valid": False,
                            "message": "Invalid Langfuse API keys. Please check your Secret Key and Public Key.",
                        }
                    except AccessDeniedError:
                        return {
                            "valid": False,
                            "message": "Langfuse API keys are not authorized. Please check your keys and permissions.",
                        }
                    except ApiError as api_error:
                        error_detail = getattr(api_error, "body", None) or str(api_error)
                        return {
                            "valid": False,
                            "message": f"Langfuse API error: {error_detail}. Please check your Host URL and keys.",
                        }

                resolved_project_id = project_id or (project_response.data[0].id if project_response.data else None)

                # If auth passed, also test the SDK client can create and flush data
                langfuse_client = Langfuse(
                    public_key=public_key,
                    secret_key=secret_key,
                    host=host,
                    flush_at=1,
                    flush_interval=1.0,
                )

                # Send a test trace/generation using correct Langfuse API
                test_span = langfuse_client.start_span(
                    name="langfuse_connection_test",
                    metadata={"test": True, "timestamp": datetime.now().isoformat()},
                )

                test_generation = langfuse_client.start_generation(
                    name="test_generation",
                    model="test",
                    model_parameters={"temperature": 0.1},
                    trace_context=TraceContext(trace_id=test_span.trace_id),
                )

                # Update generation with output, then end it
                test_generation.update(output="Connection test successful")
                test_generation.end()

                test_span.end()

                # Flush to ensure it's sent and verify it succeeds
                # This will raise an exception if keys are invalid
                langfuse_client.flush()

                return {
                    "valid": True,
                    "message": f"Langfuse connection successful! Host: {host}, Project ID: {resolved_project_id or 'default'}",
                }

            except ImportError as e:
                logger.error(f"Langfuse ImportError: {e}")
                return {
                    "valid": False,
                    "message": f"Langfuse Python package not installed. Install with: pip install langfuse. Error: {str(e)}",
                }
            except Exception as e:
                logger.error(f"Langfuse connection test error: {type(e).__name__}: {e}")
                return {
                    "valid": False,
                    "message": f"Langfuse connection failed: {type(e).__name__}: {str(e)}",
                }

    except Exception as e:
        logger.error(f"Langfuse connection test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/rank-with-gpt4o")
async def api_rank_with_gpt4o(article_id: int, request: Request):
    """API endpoint for SIGMA huntability ranking using Workflow config (prompt and model)."""
    try:
        from src.database.manager import DatabaseManager
        from src.services.llm_service import LLMService
        from src.services.workflow_trigger_service import WorkflowTriggerService

        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        optimization_options = body.get("optimization_options", {})
        use_filtering = body.get("use_filtering", True)  # Enable filtering by default
        min_confidence = body.get("min_confidence", 0.7)  # Confidence threshold
        force_regenerate = body.get("force_regenerate", False)  # Force regeneration

        # Extract API key from request (header preferred, fallback to body)
        api_key_raw = request.headers.get("X-OpenAI-API-Key") or body.get("api_key")
        api_key = api_key_raw.strip() if api_key_raw else None

        # Extract AI model from request
        ai_model = body.get("ai_model", "chatgpt")

        logger.info(
            f"Ranking request for article {article_id}, force_regenerate: {force_regenerate}, ai_model: {ai_model}"
        )

        # Check for existing ranking data (unless force regeneration is requested)
        if not force_regenerate:
            existing_ranking = article.article_metadata.get("gpt4o_ranking") if article.article_metadata else None
            if existing_ranking:
                logger.info(f"Returning existing ranking for article {article_id}")
                return {
                    "success": True,
                    "article_id": article_id,
                    "analysis": existing_ranking.get("analysis", ""),
                    "analyzed_at": existing_ranking.get("analyzed_at", ""),
                    "model_used": existing_ranking.get("model_used", ""),
                    "model_name": existing_ranking.get("model_name", ""),
                    "optimization_options": existing_ranking.get("optimization_options", {}),
                    "content_filtering": existing_ranking.get("content_filtering", {}),
                }

        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")

        # Use content filtering for high-value chunks if enabled
        content_filtering_enabled = os.getenv("CONTENT_FILTERING_ENABLED", "true").lower() == "true"
        optimization_result = {}

        if content_filtering_enabled and use_filtering:
            from src.utils.llm_optimizer import optimize_article_content

            try:
                optimization_result = await optimize_article_content(
                    article.content,
                    min_confidence=min_confidence,
                    article_metadata=article.article_metadata,
                    content_hash=article.content_hash,
                )
                if optimization_result.get("success"):
                    content_to_analyze = optimization_result["filtered_content"]
                    logger.info(
                        f"Content filtered for ranking: {optimization_result.get('tokens_saved', 0):,} tokens saved, "
                        f"{optimization_result.get('cost_reduction_percent', 0):.1f}% cost reduction"
                    )
                else:
                    # Fallback to original content if filtering fails
                    content_to_analyze = article.content
                    logger.warning("Content filtering failed for ranking, using original content")
            except Exception as e:
                logger.error(f"Content filtering error for ranking: {e}, using original content")
                content_to_analyze = article.content
        else:
            # Use original content if filtering is disabled
            content_to_analyze = article.content

        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"

        # Get workflow config for RankAgent prompt and model
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()

            if not config_obj:
                raise HTTPException(
                    status_code=500,
                    detail="No active workflow configuration found. Please configure the workflow first.",
                )

            # Get RankAgent prompt from config
            rank_prompt_template = None
            if config_obj.agent_prompts and "RankAgent" in config_obj.agent_prompts:
                rank_prompt_data = config_obj.agent_prompts["RankAgent"]
                if isinstance(rank_prompt_data.get("prompt"), str):
                    rank_prompt_template = rank_prompt_data["prompt"]
                    logger.info(
                        f"Using RankAgent prompt from workflow config (length: {len(rank_prompt_template)} chars)"
                    )

            if not rank_prompt_template:
                raise HTTPException(
                    status_code=400,
                    detail="RankAgent prompt not configured in workflow. Please configure the RankAgent prompt in Workflow settings.",
                )

            # Get agent models from config
            agent_models = config_obj.agent_models if config_obj and config_obj.agent_models else None

            # Initialize LLMService with config models
            llm_service = LLMService(config_models=agent_models)
            llm_service._current_article_id = article_id

            # Override API keys and provider from request if provided (client-side settings take precedence)
            if api_key:
                if ai_model == "chatgpt":
                    llm_service.openai_api_key = api_key
                    llm_service.workflow_openai_enabled = True
                    # Override provider and model for ranking
                    llm_service.provider_rank = "openai"
                    llm_service.model_rank = llm_service.provider_defaults.get("openai", "gpt-4o-mini")
                    logger.info(
                        f"Using OpenAI API key from request, provider: {llm_service.provider_rank}, model: {llm_service.model_rank}"
                    )
                elif ai_model == "anthropic":
                    # Extract Anthropic key if provided
                    anthropic_key_raw = request.headers.get("X-Anthropic-API-Key") or body.get("api_key")
                    anthropic_key = anthropic_key_raw.strip() if anthropic_key_raw else None
                    if anthropic_key:
                        llm_service.anthropic_api_key = anthropic_key
                        llm_service.workflow_anthropic_enabled = True
                        # Override provider and model for ranking
                        llm_service.provider_rank = "anthropic"
                        llm_service.model_rank = llm_service.provider_defaults.get("anthropic", "claude-sonnet-4-5")
                        logger.info(
                            f"Using Anthropic API key from request, provider: {llm_service.provider_rank}, model: {llm_service.model_rank}"
                        )

            # Validate provider is enabled and has API key
            if llm_service.provider_rank == "openai":
                if not llm_service.workflow_openai_enabled or not llm_service.openai_api_key:
                    raise HTTPException(
                        status_code=400,
                        detail="OpenAI provider is not enabled or API key is missing. Please configure it in Settings.",
                    )
            elif llm_service.provider_rank == "anthropic":
                if not llm_service.workflow_anthropic_enabled or not llm_service.anthropic_api_key:
                    raise HTTPException(
                        status_code=400,
                        detail="Anthropic provider is not enabled or API key is missing. Please configure it in Settings.",
                    )

            # Get ground truth details for logging
            hunt_score = article.article_metadata.get("threat_hunting_score") if article.article_metadata else None
            ml_score = article.article_metadata.get("ml_hunt_score") if article.article_metadata else None
            ground_truth_details = LLMService.compute_rank_ground_truth(hunt_score, ml_score)
            ground_truth_rank = ground_truth_details.get("ground_truth_rank")

            # Call LLMService.rank_article() with workflow config prompt
            ranking_result = await llm_service.rank_article(
                title=article.title,
                content=content_to_analyze,
                source=source_name,
                url=article.canonical_url or "",
                prompt_template=rank_prompt_template,
                article_id=article.id,
                ground_truth_rank=ground_truth_rank,
                ground_truth_details=ground_truth_details,
            )

            # Extract score and reasoning from ranking result
            score = ranking_result.get("score")
            reasoning = ranking_result.get("reasoning", "")
            warnings = ranking_result.get("warnings")

            # Format analysis similar to original endpoint format
            analysis = f"Score: {score}/10\n\nReasoning:\n{reasoning}"

            # Get model name from LLMService
            model_name = llm_service.model_rank or "unknown"
            model_used = "workflow_config"

        finally:
            db_session.close()

        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}

        article.article_metadata["gpt4o_ranking"] = {
            "analysis": analysis,
            "analyzed_at": datetime.now().isoformat(),
            "model_used": model_used,
            "model_name": model_name,
            "optimization_options": optimization_options,
            "content_filtering": {
                "enabled": content_filtering_enabled and use_filtering,
                "min_confidence": min_confidence if content_filtering_enabled and use_filtering else None,
                "tokens_saved": optimization_result.get("tokens_saved", 0)
                if content_filtering_enabled and use_filtering
                else 0,
                "cost_reduction_percent": optimization_result.get("cost_reduction_percent", 0)
                if content_filtering_enabled and use_filtering
                else 0,
            },
        }

        # Update the article
        from src.models.article import ArticleUpdate

        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "analyzed_at": article.article_metadata["gpt4o_ranking"]["analyzed_at"],
            "model_used": model_used,
            "model_name": model_name,
            "optimization_options": optimization_options,
            "content_filtering": article.article_metadata["gpt4o_ranking"]["content_filtering"],
            "warnings": warnings if warnings else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/gpt4o-rank")
async def api_gpt4o_rank(article_id: int, request: Request):
    """API endpoint for GPT4o SIGMA huntability ranking."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        article_url = body.get("url")
        # Try header first (prevents corruption with large payloads), fallback to body for backward compatibility
        api_key_raw = request.headers.get("X-OpenAI-API-Key") or body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None

        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key is required. Please configure it in Settings.",
            )

        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")

        # Use full content (no hardcoded truncation)
        content_to_analyze = article.content

        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"

        # SIGMA-focused prompt
        sigma_prompt = format_prompt(
            "gpt4o_sigma_ranking",
            title=article.title,
            source=source_name,
            url=article.canonical_url or "N/A",
            content=content_to_analyze,
        )

        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze,
        )

        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": full_prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
                timeout=60.0,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")

            result = response.json()
            analysis = result["choices"][0]["message"]["content"]

        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}

        article.article_metadata["gpt4o_ranking"] = {
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
            "model": "gpt-4o",
        }

        # Update the article in the database
        from src.models.article import ArticleUpdate

        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/gpt4o-rank-optimized")
async def api_gpt4o_rank_optimized(article_id: int, request: Request):
    """Enhanced API endpoint for GPT4o SIGMA huntability ranking with content filtering."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        article_url = body.get("url")
        # Try header first (prevents corruption with large payloads), fallback to body for backward compatibility
        api_key_raw = request.headers.get("X-OpenAI-API-Key") or body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None
        # Prefer client-provided model; fallback to local LMStudio by default to avoid unnecessary cloud key prompts
        ai_model = body.get("ai_model") or "lmstudio"
        use_filtering = body.get("use_filtering", True)  # Enable filtering by default
        min_confidence = body.get("min_confidence", 0.7)  # Confidence threshold

        # This endpoint is specifically for GPT-4o optimization
        # Only support chatgpt model
        if ai_model != "chatgpt":
            raise HTTPException(
                status_code=400,
                detail="This endpoint (gpt4o-rank-optimized) only supports ChatGPT. Use the standard rank-with-gpt4o endpoint for other models.",
            )

        # Only require API key for chatgpt
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key is required. Please configure it in Settings.",
            )

        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(status_code=400, detail="Article content is required for analysis")

        # Import the optimizer
        from src.utils.llm_optimizer import optimize_article_content

        # Optimize content if filtering is enabled
        if use_filtering:
            logger.info(f"Optimizing content for article {article_id} with confidence threshold {min_confidence}")
            optimization_result = await optimize_article_content(article.content, min_confidence)

            if optimization_result["success"]:
                content_to_analyze = optimization_result["filtered_content"]
                cost_savings = optimization_result["cost_savings"]
                tokens_saved = optimization_result["tokens_saved"]
                chunks_removed = optimization_result["chunks_removed"]

                logger.info(
                    f"Content optimization completed: "
                    f"{tokens_saved:,} tokens saved, "
                    f"${cost_savings:.4f} cost savings, "
                    f"{chunks_removed} chunks removed"
                )
            else:
                logger.warning("Content optimization failed, using original content")
                content_to_analyze = article.content
                cost_savings = 0.0
                tokens_saved = 0
                chunks_removed = 0
        else:
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0

        # Use full content (no hardcoded truncation)

        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"

        # SIGMA-focused prompt (same as original)
        sigma_prompt = format_prompt(
            "gpt4o_sigma_ranking",
            title=article.title,
            source=source_name,
            url=article.canonical_url or "N/A",
            content=content_to_analyze,
        )

        # Prepare the prompt with the article content
        full_prompt = sigma_prompt.format(
            title=article.title,
            source=source_name,
            url=article.canonical_url,
            content=content_to_analyze,
        )

        # Call OpenAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": full_prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.3,
                },
                timeout=60.0,
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"OpenAI API error: {error_detail}")
                raise HTTPException(status_code=500, detail=f"OpenAI API error: {error_detail}")

            result = response.json()
            analysis = result["choices"][0]["message"]["content"]

        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}

        article.article_metadata["gpt4o_ranking"] = {
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
            "model": "gpt-4o",
            "optimization_enabled": use_filtering,
            "cost_savings": cost_savings,
            "tokens_saved": tokens_saved,
            "chunks_removed": chunks_removed,
            "min_confidence": min_confidence if use_filtering else None,
        }

        # Update the article in the database
        from src.models.article import ArticleUpdate

        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": True,
            "article_id": article_id,
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
            "optimization": {
                "enabled": use_filtering,
                "cost_savings": cost_savings,
                "tokens_saved": tokens_saved,
                "chunks_removed": chunks_removed,
                "min_confidence": min_confidence if use_filtering else None,
            },
            "debug_info": {
                "removed_chunks": optimization_result.get("removed_chunks", [])
                if use_filtering and optimization_result.get("success")
                else [],
                "original_length": len(article.content),
                "filtered_length": len(content_to_analyze),
                "reduction_percent": round(
                    (len(article.content) - len(content_to_analyze)) / max(len(article.content), 1) * 100,
                    1,
                )
                if use_filtering
                else 0,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPT4o ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/extract-observables")
async def api_extract_observables(article_id: int, request: Request):
    """Extract observables (IOCs and behavioral indicators) from an article using Extract Observables model."""
    try:
        from pathlib import Path

        from src.database.manager import DatabaseManager
        from src.services.llm_service import LLMService
        from src.services.workflow_trigger_service import WorkflowTriggerService

        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body to check for optimization options
        body = await request.json()
        optimization_options = body.get("optimization_options", {})
        use_filtering = optimization_options.get("useFiltering", True)
        min_confidence = float(optimization_options.get("minConfidence", 0.8)) if use_filtering else 1.0

        # Get user's QA agent preference (overrides workflow config if set)
        use_qa_agent_user = optimization_options.get("useQAAgent")

        # Get workflow config for agent models and prompts
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj and config_obj.agent_models else {}

            # Check if QA is enabled for ExtractAgent
            # Use user preference if provided, otherwise use workflow config
            qa_enabled = False
            if use_qa_agent_user is not None:
                qa_enabled = use_qa_agent_user
            elif config_obj and config_obj.qa_enabled:
                qa_enabled = config_obj.qa_enabled.get("ExtractAgent", False)

            # Get ExtractAgent prompt from config (use for observables extraction)
            prompt_config_dict = None
            instructions_template_str = None
            if config_obj and config_obj.agent_prompts and "ExtractAgent" in config_obj.agent_prompts:
                agent_prompt_data = config_obj.agent_prompts["ExtractAgent"]
                # Parse prompt JSON
                if isinstance(agent_prompt_data.get("prompt"), str):
                    import json

                    try:
                        prompt_config_dict = json.loads(agent_prompt_data["prompt"])
                        # Handle nested JSON if present
                        if isinstance(prompt_config_dict, dict) and len(prompt_config_dict) == 1:
                            first_value = next(iter(prompt_config_dict.values()))
                            if isinstance(first_value, dict):
                                prompt_config_dict = first_value
                    except json.JSONDecodeError:
                        logger.warning(
                            "Failed to parse ExtractAgent prompt JSON, falling back to ExtractObservables file"
                        )
                elif isinstance(agent_prompt_data.get("prompt"), dict):
                    prompt_config_dict = agent_prompt_data["prompt"]

                instructions_template_str = agent_prompt_data.get("instructions")
        finally:
            db_session.close()

        # Initialize LLM service with workflow config
        llm_service = LLMService(config_models=agent_models)

        # Use ExtractAgent prompt from config if available, otherwise fall back to ExtractObservables file
        use_workflow_prompt = prompt_config_dict is not None and instructions_template_str is not None
        prompt_file = None
        if not use_workflow_prompt:
            prompt_file = Path(__file__).parent.parent.parent / "prompts" / "ExtractObservables"
            if not prompt_file.exists():
                raise HTTPException(
                    status_code=500,
                    detail="ExtractObservables prompt file not found and ExtractAgent prompt not in workflow config",
                )

        # Filter content if filtering is enabled
        from src.utils.content_filter import ContentFilter

        content_filter = ContentFilter()

        if use_filtering:
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=min_confidence,
                hunt_score=article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0,
                article_id=article.id,
            )
        else:
            # No filtering - use original content
            filter_result = type(
                "FilterResult",
                (),
                {
                    "is_huntable": True,
                    "filtered_content": article.content,
                    "removed_chunks": [],
                },
            )()

        # Check if content passed filter (has huntable content)
        if not filter_result.is_huntable:
            raise HTTPException(
                status_code=400,
                detail="Article content did not pass content filter. No huntable content detected.",
            )

        # Check if filtered content is empty or too short
        filtered_content = filter_result.filtered_content or article.content
        if not filtered_content or len(filtered_content.strip()) < 100:
            raise HTTPException(
                status_code=400,
                detail="Article content has insufficient huntable content after filtering.",
            )

        # Create a cancellation event
        cancellation_event = asyncio.Event()

        # Start monitoring client disconnection in background
        async def monitor_disconnection():
            # Only check for disconnection periodically, and be more careful about false positives
            while True:
                await asyncio.sleep(1.0)  # Check every 1 second (less aggressive)
                try:
                    # Check if client disconnected - only use property check, avoid callable check
                    # which can cause false positives
                    if hasattr(request, "is_disconnected"):
                        # Only check the property, not as a callable
                        is_disconnected = request.is_disconnected
                        if isinstance(is_disconnected, bool) and is_disconnected:
                            logger.info(
                                f"Client disconnected, cancelling observables extraction for article {article_id}"
                            )
                            cancellation_event.set()
                            break
                except Exception as e:
                    # Don't cancel on exceptions checking disconnection - just log and continue
                    logger.debug(f"Error checking disconnection status: {e}")
                    # Don't break - continue monitoring

        monitor_task = asyncio.create_task(monitor_disconnection())

        # QA retry loop - get max retries from config
        max_qa_retries = config_obj.qa_max_retries if config_obj and hasattr(config_obj, "qa_max_retries") else 5
        qa_feedback = None
        extraction_result = None
        qa_results = {}

        try:
            # Get agent prompt for QA
            agent_prompt = None
            if use_workflow_prompt:
                import json

                agent_prompt = (
                    json.dumps(prompt_config_dict, indent=2) if prompt_config_dict else instructions_template_str[:5000]
                )

            # QA retry loop
            for qa_attempt in range(max_qa_retries):
                # Extract observables
                if use_workflow_prompt:
                    # Use ExtractAgent prompt from workflow config (via extract_behaviors)
                    extraction_task = asyncio.create_task(
                        llm_service.extract_behaviors(
                            content=filtered_content,
                            title=article.title,
                            url=article.canonical_url or "",
                            prompt_config_dict=prompt_config_dict,
                            instructions_template_str=instructions_template_str,
                            qa_feedback=qa_feedback,
                        )
                    )
                else:
                    # Use ExtractObservables file prompt
                    extraction_task = asyncio.create_task(
                        llm_service.extract_observables(
                            content=filtered_content,
                            title=article.title,
                            url=article.canonical_url or "",
                            prompt_file_path=str(prompt_file),
                            cancellation_event=cancellation_event,
                            qa_feedback=qa_feedback,
                        )
                    )

                # Wait for either completion or cancellation
                done, pending = await asyncio.wait([extraction_task, monitor_task], return_when=asyncio.FIRST_COMPLETED)

                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                # Check if cancellation was requested
                if cancellation_event.is_set():
                    logger.info(f"Observables extraction cancelled for article {article_id}")
                    raise HTTPException(status_code=499, detail="Client cancelled the request")

                # Get the result
                extraction_result = await extraction_task

                # If QA not enabled, break after first attempt
                if not qa_enabled or not use_workflow_prompt:
                    break

                # Run QA check
                from src.services.qa_agent_service import QAAgentService

                qa_service = QAAgentService(llm_service=llm_service)
                qa_result = await qa_service.evaluate_agent_output(
                    article=article,
                    agent_prompt=agent_prompt,
                    agent_output=extraction_result,
                    agent_name="ExtractAgent",
                    config_obj=config_obj,
                )

                # Store QA result
                qa_results[f"attempt_{qa_attempt + 1}"] = qa_result

                # If QA passes, break
                if qa_result.get("verdict") == "pass":
                    break

                # Generate feedback for retry
                qa_feedback = await qa_service.generate_feedback(qa_result, "ExtractAgent")

                # If critical failure on last attempt, log warning but continue
                if qa_result.get("verdict") == "critical_failure" and qa_attempt == max_qa_retries - 1:
                    logger.warning(
                        f"QA critical failure after {max_qa_retries} attempts for observables extraction: {qa_result.get('summary', 'Unknown error')}"
                    )

            # Extract warnings from extraction result
            extraction_warnings = extraction_result.get("warnings")

            return {
                "success": True,
                "article_id": article_id,
                "extraction": extraction_result,
                "metadata": {
                    "atomic_count": extraction_result.get("metadata", {}).get("atomic_count", 0),
                    "behavioral_count": extraction_result.get("metadata", {}).get("behavioral_count", 0),
                    "total_observables": extraction_result.get("metadata", {}).get("observable_count", 0),
                },
                "qa_results": qa_results if qa_results else None,
                "warnings": extraction_warnings if extraction_warnings else None,
            }

        except asyncio.CancelledError:
            logger.info(f"Observables extraction task cancelled for article {article_id}")
            raise HTTPException(status_code=499, detail="Client cancelled the request")
        finally:
            # Clean up monitor task
            if not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting observables: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract observables: {str(e)}")


@router.post("/{article_id}/extract-iocs")
async def api_extract_iocs(article_id: int, request: Request):
    """Extract IOCs (Indicators of Compromise) from an article using AI."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        # Try header first (prevents corruption with large payloads), fallback to body for backward compatibility
        # For Anthropic, check X-Anthropic-API-Key header, for OpenAI check X-OpenAI-API-Key
        api_key_raw = None
        if body.get("ai_model", "chatgpt") == "anthropic":
            api_key_raw = request.headers.get("X-Anthropic-API-Key") or body.get("api_key")
        else:
            api_key_raw = request.headers.get("X-OpenAI-API-Key") or body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None
        ai_model = body.get("ai_model", "chatgpt")
        use_llm_validation = body.get("use_llm_validation", False)
        debug_mode = body.get("debug_mode", False)

        # Only require API key for cloud-based models
        if ai_model in ["chatgpt", "anthropic"] and not api_key:
            key_type = "OpenAI" if ai_model == "chatgpt" else "Anthropic"
            raise HTTPException(
                status_code=400,
                detail=f"{key_type} API key is required. Please configure it in Settings.",
            )

        # Use the IOC extractor
        from src.utils.ioc_extractor import HybridIOCExtractor

        # Enable LLM validation for all models
        effective_llm_validation = use_llm_validation
        if use_llm_validation:
            logger.info(f"LLM validation enabled for {ai_model} model")

        # Apply content filtering only when LLM validation is enabled
        # This reduces costs by filtering out non-huntable content before sending to LLM
        content_to_use = article.content
        filter_metadata = {}
        if use_llm_validation:
            from src.utils.content_filter import ContentFilter

            content_filter = ContentFilter()
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=0.9,  # Use least aggressive filter (similar to Extract Observables)
                hunt_score=article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0,
                article_id=article.id,
            )

            # Use filtered content if available and huntable, otherwise use original
            if filter_result.is_huntable and filter_result.filtered_content:
                content_to_use = filter_result.filtered_content
                filter_metadata = {
                    "content_filtering": {
                        "enabled": True,
                        "cost_savings": filter_result.cost_savings,
                        "chunks_removed": len(filter_result.removed_chunks) if filter_result.removed_chunks else 0,
                        "min_confidence": 0.9,
                    }
                }
                logger.info(
                    f"Content filtering applied: {filter_result.cost_savings:.1%} cost savings, {len(filter_result.removed_chunks) if filter_result.removed_chunks else 0} chunks removed"
                )
            else:
                logger.info("Content filter did not find huntable content, using original content for LLM validation")

        # Create a cancellation event
        cancellation_event = asyncio.Event()

        # Start monitoring client disconnection in background
        async def monitor_disconnection():
            # Only check for disconnection periodically, and be more careful about false positives
            while True:
                await asyncio.sleep(1.0)  # Check every 1 second (less aggressive)
                try:
                    # Check if client disconnected - only use property check, avoid callable check
                    # which can cause false positives
                    if hasattr(request, "is_disconnected"):
                        # Only check the property, not as a callable
                        is_disconnected = request.is_disconnected
                        if isinstance(is_disconnected, bool) and is_disconnected:
                            logger.info(f"Client disconnected, cancelling IOCs extraction for article {article_id}")
                            cancellation_event.set()
                            break
                except Exception as e:
                    # Don't cancel on exceptions checking disconnection - just log and continue
                    logger.debug(f"Error checking disconnection status: {e}")
                    # Don't break - continue monitoring

        monitor_task = asyncio.create_task(monitor_disconnection())

        try:
            extractor = HybridIOCExtractor(use_llm_validation=effective_llm_validation)

            # Extract IOCs from the article content (filtered if LLM validation is enabled)
            extraction_task = asyncio.create_task(
                extractor.extract_iocs(
                    content=content_to_use,
                    api_key=api_key,
                    ai_model=ai_model,  # Pass AI model to extractor
                    cancellation_event=cancellation_event,  # Pass cancellation event
                )
            )

            # Wait for either completion or cancellation
            done, pending = await asyncio.wait([extraction_task, monitor_task], return_when=asyncio.FIRST_COMPLETED)

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check if cancellation was requested
            if cancellation_event.is_set():
                logger.info(f"IOCs extraction cancelled for article {article_id}")
                raise HTTPException(status_code=499, detail="Client cancelled the request")

            # Get the result
            result = await extraction_task

            # Update article metadata with extracted IOCs
            if result.iocs and len(result.iocs) > 0:
                # Get current metadata and merge with new IOCs data
                current_metadata = article.article_metadata or {}
                current_metadata["extracted_iocs"] = {
                    "iocs": result.iocs,
                    "extraction_method": result.extraction_method,
                    "confidence": result.confidence,
                    "extracted_at": datetime.now().isoformat(),
                    "ai_model": ai_model,
                    "use_llm_validation": result.extraction_method == "hybrid",  # Store actual validation status
                    "processing_time": result.processing_time,
                    "raw_count": result.raw_count,
                    "validated_count": result.validated_count,
                    "metadata": result.metadata,  # Store prompt and response
                    **filter_metadata,  # Include content filtering metadata if applied
                }

                # Update the article in the database
                from src.models.article import ArticleUpdate

                update_data = ArticleUpdate(article_metadata=current_metadata)
                await async_db_manager.update_article(article_id, update_data)

            return {
                "success": len(result.iocs) > 0,
                "iocs": result.iocs,
                "method": result.extraction_method,
                "confidence": result.confidence,
                "processing_time": result.processing_time,
                "raw_count": result.raw_count,
                "validated_count": result.validated_count,
                "debug_info": result.metadata if debug_mode else None,
                "llm_prompt": result.metadata.get("prompt") if result.metadata else None,
                "llm_response": result.metadata.get("response") if result.metadata else None,
                "error": None if len(result.iocs) > 0 else "No IOCs found",
            }

        except asyncio.CancelledError:
            logger.info(f"IOCs extraction task cancelled for article {article_id}")
            raise HTTPException(status_code=499, detail="Client cancelled the request")
        finally:
            # Clean up monitor task
            if not monitor_task.done():
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"IOCs extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/extract-iocs-ctibert")
async def api_extract_iocs_ctibert(article_id: int, request: Request):
    """Extract IOCs using CTI-BERT Named Entity Recognition."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Import CTI-BERT extractor
        from src.utils.ctibert_ner_extractor import CTIBERTNERExtractor

        # Initialize extractor
        extractor = CTIBERTNERExtractor()

        # Extract IOCs
        result = extractor.extract_iocs(article.content)

        # Update article metadata with extracted IOCs
        if article.article_metadata:
            update_data = {
                "article_metadata": {
                    **article.article_metadata,
                    "extracted_iocs_ctibert": {
                        "iocs": result.iocs,
                        "extraction_method": result.extraction_method,
                        "confidence": result.confidence,
                        "processing_time": result.processing_time,
                        "raw_count": result.raw_count,
                        "validated_count": result.validated_count,
                        "extracted_at": datetime.now().isoformat(),
                        "metadata": result.metadata,
                    },
                }
            }
        else:
            update_data = {
                "article_metadata": {
                    "extracted_iocs_ctibert": {
                        "iocs": result.iocs,
                        "extraction_method": result.extraction_method,
                        "confidence": result.confidence,
                        "processing_time": result.processing_time,
                        "raw_count": result.raw_count,
                        "validated_count": result.validated_count,
                        "extracted_at": datetime.now().isoformat(),
                        "metadata": result.metadata,
                    }
                }
            }

        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": result.validated_count > 0,
            "iocs": result.iocs,
            "method": result.extraction_method,
            "confidence": result.confidence,
            "processing_time": result.processing_time,
            "raw_count": result.raw_count,
            "validated_count": result.validated_count,
            "metadata": result.metadata,
            "error": None if result.validated_count > 0 else "No IOCs found",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CTI-BERT IOC extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/detect-os")
async def api_detect_os(article_id: int, request: Request):
    """Detect operating system from article content using CTI-BERT + classifier (with Mistral-7B fallback)."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        use_classifier = body.get("use_classifier", True)
        use_fallback = body.get("use_fallback", True)
        use_junk_filter = body.get("use_junk_filter", True)  # Enable junk filter by default
        junk_filter_threshold = body.get("junk_filter_threshold", 0.8)  # Default threshold

        # Import OS detection service and content filter
        from src.database.manager import DatabaseManager
        from src.services.os_detection_service import OSDetectionService
        from src.services.workflow_trigger_service import WorkflowTriggerService
        from src.utils.content_filter import ContentFilter

        # Get OS detection config from workflow config
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        try:
            trigger_service = WorkflowTriggerService(db_session)
            config_obj = trigger_service.get_active_config()
            agent_models = config_obj.agent_models if config_obj and config_obj.agent_models else {}
            embedding_model = agent_models.get("OSDetectionAgent_embedding", "ibm-research/CTI-BERT")
            fallback_model = agent_models.get("OSDetectionAgent_fallback")

            # Get junk filter threshold from config if not provided in request
            if config_obj and not body.get("junk_filter_threshold"):
                junk_filter_threshold = (
                    config_obj.junk_filter_threshold
                    if hasattr(config_obj, "junk_filter_threshold") and config_obj.junk_filter_threshold
                    else 0.8
                )
        finally:
            db_session.close()

        # Apply junk filter if enabled
        content_to_analyze = article.content
        filtering_metadata = None
        if use_junk_filter:
            content_filter = ContentFilter()
            hunt_score = article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=junk_filter_threshold,
                hunt_score=hunt_score,
                article_id=article.id,
            )
            content_to_analyze = filter_result.filtered_content or article.content
            filtering_metadata = {
                "enabled": True,
                "threshold": junk_filter_threshold,
                "original_length": len(article.content),
                "filtered_length": len(content_to_analyze),
                "reduction_percent": ((len(article.content) - len(content_to_analyze)) / len(article.content) * 100)
                if len(article.content) > 0
                else 0,
                "chunks_removed": filter_result.chunks_removed if hasattr(filter_result, "chunks_removed") else None,
                "chunks_kept": filter_result.chunks_kept if hasattr(filter_result, "chunks_kept") else None,
            }
        else:
            filtering_metadata = {"enabled": False}

        # Initialize service with configured embedding model
        service = OSDetectionService(model_name=embedding_model)

        # Detect OS with configured fallback model using filtered content
        result = await service.detect_os(
            content=content_to_analyze,
            use_classifier=use_classifier,
            use_fallback=use_fallback,
            fallback_model=fallback_model,
        )

        # Update article metadata with OS detection result
        if article.article_metadata:
            update_data = {
                "article_metadata": {
                    **article.article_metadata,
                    "os_detection": {
                        "operating_system": result.get("operating_system"),
                        "method": result.get("method"),
                        "confidence": result.get("confidence"),
                        "detected_at": datetime.now().isoformat(),
                        "similarities": result.get("similarities"),
                        "max_similarity": result.get("max_similarity"),
                        "probabilities": result.get("probabilities"),
                        "content_filtering": filtering_metadata,
                    },
                }
            }
        else:
            update_data = {
                "article_metadata": {
                    "os_detection": {
                        "operating_system": result.get("operating_system"),
                        "method": result.get("method"),
                        "confidence": result.get("confidence"),
                        "detected_at": datetime.now().isoformat(),
                        "similarities": result.get("similarities"),
                        "max_similarity": result.get("max_similarity"),
                        "probabilities": result.get("probabilities"),
                        "content_filtering": filtering_metadata,
                    }
                }
            }

        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": True,
            "operating_system": result.get("operating_system"),
            "method": result.get("method"),
            "confidence": result.get("confidence"),
            "similarities": result.get("similarities"),
            "max_similarity": result.get("max_similarity"),
            "probabilities": result.get("probabilities"),
            "raw_response": result.get("raw_response"),
            "content_filtering": filtering_metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OS detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{article_id}/generate-sigma")
async def api_generate_sigma(article_id: int, request: Request):
    """Generate SIGMA detection rules from an article using AI."""
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()

        # Try header first (prevents corruption with large payloads), fallback to body for backward compatibility
        # Support both OpenAI and Anthropic headers
        api_key_raw = (
            request.headers.get("X-OpenAI-API-Key") or request.headers.get("X-Anthropic-API-Key") or body.get("api_key")
        )

        # DEBUG: Log raw key before any processing
        if api_key_raw:
            api_key_source = (
                "header (OpenAI)"
                if request.headers.get("X-OpenAI-API-Key")
                else "header (Anthropic)"
                if request.headers.get("X-Anthropic-API-Key")
                else "body"
            )
            logger.info(
                f"🔍 DEBUG SIGMA: api_key source: {api_key_source}, type: {type(api_key_raw)}, length: {len(api_key_raw) if isinstance(api_key_raw, str) else 'N/A'}, ends_with: ...{api_key_raw[-4:] if isinstance(api_key_raw, str) and len(api_key_raw) >= 4 else 'N/A'}"
            )

        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None

        # DEBUG: Log after stripping
        if api_key:
            logger.info(f"🔍 DEBUG SIGMA: After strip - length: {len(api_key)}, ends_with: ...{api_key[-4:]}")

        ai_model = body.get("ai_model", "chatgpt")
        author_name = body.get("author_name", "Huntable CTI Studio User")
        force_regenerate = body.get("force_regenerate", False)
        skip_matching = body.get("skip_matching", False)  # Option to skip matching phase

        # Log the received AI model for debugging (mask API key for security)
        api_key_preview = f"{api_key[:8]}...{api_key[-4:]}" if api_key and len(api_key) > 12 else "None"
        logger.info(
            f"🤖 SIGMA generation requested with ai_model='{ai_model}', api_key provided: {bool(api_key)}, api_key preview: {api_key_preview}"
        )

        # Only require API key for ChatGPT
        if ai_model == "chatgpt" and not api_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key is required for ChatGPT. Please configure it in Settings.",
            )

        # === NEW: Match-First Logic ===
        # Phase 1: Match article to existing Sigma rules (unless skipped)
        matched_rules = []
        coverage_summary = {"covered": 0, "extend": 0, "new": 0, "total": 0}

        if not skip_matching:
            try:
                from src.database.manager import DatabaseManager
                from src.database.models import SigmaRuleTable
                from src.services.sigma_coverage_service import SigmaCoverageService
                from src.services.sigma_matching_service import SigmaMatchingService

                logger.info(f"Matching article {article_id} to existing Sigma rules...")

                db_manager = DatabaseManager()
                db_session = db_manager.get_session()

                matching_service = SigmaMatchingService(db_session)
                coverage_service = SigmaCoverageService(db_session)

                # Match at article level (no threshold - return all sorted by similarity)
                article_matches = matching_service.match_article_to_rules(article_id, threshold=0.0, limit=10)

                # Process matches and classify coverage
                for match in article_matches:
                    rule = db_session.query(SigmaRuleTable).filter_by(rule_id=match["rule_id"]).first()
                    if rule:
                        classification = coverage_service.classify_match(article_id, rule, match["similarity"])

                        # Store match in database
                        matching_service.store_match(
                            article_id=article_id,
                            sigma_rule_id=rule.id,
                            similarity_score=match["similarity"],
                            match_level="article",
                            coverage_status=classification["coverage_status"],
                            coverage_confidence=classification["coverage_confidence"],
                            coverage_reasoning=classification["coverage_reasoning"],
                            matched_discriminators=classification["matched_discriminators"],
                            matched_lolbas=classification["matched_lolbas"],
                            matched_intelligence=classification["matched_intelligence"],
                        )

                        matched_rules.append(
                            {
                                "rule_id": match["rule_id"],
                                "title": match["title"],
                                "description": match["description"],
                                "similarity": match["similarity"],
                                "level": match.get("level"),
                                "status": match.get("status"),
                                "coverage_status": classification["coverage_status"],
                                "coverage_confidence": classification["coverage_confidence"],
                                "matched_behaviors": classification["matched_discriminators"][:5],
                            }
                        )

                        # Update coverage summary
                        status = classification["coverage_status"]
                        if status in coverage_summary:
                            coverage_summary[status] += 1

                coverage_summary["total"] = len(matched_rules)
                db_session.close()

                logger.info(
                    f"Found {len(matched_rules)} matching rules: "
                    f"{coverage_summary['covered']} covered, "
                    f"{coverage_summary['extend']} extend, "
                    f"{coverage_summary['new']} new"
                )

                # Phase 2: Decision - skip generation if well covered
                if coverage_summary["covered"] >= 2 and not force_regenerate:
                    logger.info("Article is well covered by existing Sigma rules, skipping generation")
                    return {
                        "success": True,
                        "matched_rules": matched_rules,
                        "coverage_summary": coverage_summary,
                        "generated_rules": [],
                        "recommendation": f"Article behaviors are covered by {coverage_summary['covered']} existing Sigma rule(s). No new rules needed.",
                        "skipped_generation": True,
                        "error": None,
                    }

            except Exception as e:
                logger.warning(f"Error during Sigma matching: {e}. Proceeding with generation.")
                # Continue to generation phase even if matching fails

        # Check for existing SIGMA rules (unless force regeneration is requested)
        if not force_regenerate and article.article_metadata and article.article_metadata.get("sigma_rules"):
            existing_rules = article.article_metadata.get("sigma_rules")
            return {
                "success": True,
                "rules": existing_rules.get("rules", []),
                "metadata": existing_rules.get("metadata", {}),
                "matched_rules": matched_rules,
                "coverage_summary": coverage_summary,
                "cached": True,
                "error": None,
            }

        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(
                status_code=400,
                detail="Article content is required for SIGMA rule generation",
            )

        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"

        # Load active workflow config to use SigmaAgent settings
        from src.database.manager import DatabaseManager
        from src.database.models import AgenticWorkflowConfigTable

        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            config = (
                db_session.query(AgenticWorkflowConfigTable)
                .filter(AgenticWorkflowConfigTable.is_active == True)
                .order_by(AgenticWorkflowConfigTable.version.desc())
                .first()
            )

            if not config:
                logger.warning("No active workflow configuration found, using defaults")
                config = None
        except Exception as e:
            logger.warning(f"Error loading workflow config: {e}, using defaults")
            config = None

        # Get SigmaAgent prompt from config if available
        sigma_prompt_template = None
        sigma_system_prompt = None
        if config and config.agent_prompts and "SigmaAgent" in config.agent_prompts:
            sigma_prompt_data = config.agent_prompts["SigmaAgent"]
            if isinstance(sigma_prompt_data.get("prompt"), str):
                sigma_prompt_template = sigma_prompt_data["prompt"]
                logger.info(f"Using SigmaAgent prompt from workflow config (len={len(sigma_prompt_template)} chars)")
            if isinstance(sigma_prompt_data.get("system_prompt"), str):
                sigma_system_prompt = sigma_prompt_data["system_prompt"]
                logger.info(
                    f"Using SigmaAgent system prompt from workflow config (len={len(sigma_system_prompt)} chars)"
                )
            if not isinstance(sigma_prompt_data.get("prompt"), str):
                logger.warning("SigmaAgent prompt in config is not a string, using default")
        else:
            logger.info("No SigmaAgent prompt in workflow config, using default prompt")

        # Get agent models from config
        agent_models = config.agent_models if config and config.agent_models else {}

        # Apply content filtering to optimize for SIGMA generation
        from src.utils.llm_optimizer import optimize_article_content

        # Use content filtering with high confidence threshold for SIGMA generation
        min_confidence = 0.7
        logger.info(f"Optimizing content for SIGMA generation with confidence threshold {min_confidence}")
        optimization_result = await optimize_article_content(article.content, min_confidence)

        if optimization_result["success"]:
            content_to_analyze = optimization_result["filtered_content"]
            cost_savings = optimization_result["cost_savings"]
            tokens_saved = optimization_result["tokens_saved"]
            chunks_removed = optimization_result["chunks_removed"]

            logger.info(
                f"Content optimization completed for SIGMA generation: "
                f"{tokens_saved:,} tokens saved, "
                f"${cost_savings:.4f} cost savings, "
                f"{chunks_removed} chunks removed"
            )
        else:
            logger.warning("Content optimization failed for SIGMA generation, using original content")
            content_to_analyze = article.content
            cost_savings = 0.0
            tokens_saved = 0
            chunks_removed = 0

        # Use SigmaGenerationService with workflow config (same as test_sigma_agent_task)
        from src.services.sigma_generation_service import SigmaGenerationService

        # Determine provider from config or fallback to ai_model parameter
        sigma_provider = agent_models.get("SigmaAgent_provider") if agent_models else None
        if not sigma_provider:
            # Fallback: use ai_model parameter (lmstudio or chatgpt)
            sigma_provider = "lmstudio" if ai_model == "lmstudio" else "openai"

        logger.info(
            f"Using SigmaGenerationService with provider={sigma_provider}, config_models={'present' if agent_models else 'default'}"
        )

        # Initialize service with config
        sigma_service = SigmaGenerationService(config_models=agent_models)

        # Generate SIGMA rules using service
        generation_result = await sigma_service.generate_sigma_rules(
            article_title=article.title,
            article_content=content_to_analyze,
            source_name=source_name,
            url=article.canonical_url or "",
            ai_model=sigma_provider,  # Use provider from config
            api_key=api_key if sigma_provider == "openai" else None,
            max_attempts=3,
            min_confidence=min_confidence,
            execution_id=None,  # Not part of workflow execution
            article_id=article_id,
            qa_feedback=None,
            sigma_prompt_template=sigma_prompt_template,  # Use prompt from config if available
            sigma_system_prompt=sigma_system_prompt,  # Use system prompt from config if available
        )

        # Extract results from service
        rules = generation_result.get("rules", []) if generation_result else []
        sigma_errors = generation_result.get("errors")
        sigma_metadata = generation_result.get("metadata", {}) if generation_result else {}
        validation_results = sigma_metadata.get("validation_results", [])
        conversation_log = sigma_metadata.get("conversation_log", [])

        # Track truncation warnings
        sigma_content_truncation_warning = None
        sigma_prompt_truncation_warning = None
        sigma_response_truncation_warning = None

        # Close DB session
        if db_session:
            db_session.close()

        # Legacy compatibility: Convert rules to old format if needed
        # (SigmaGenerationService already returns proper format, but ensure compatibility)
        formatted_rules = []
        for rule in rules:
            if isinstance(rule, dict):
                formatted_rules.append(rule)
            else:
                # Fallback: create dict from rule content
                formatted_rules.append(
                    {"content": str(rule), "title": "Generated Rule", "level": "medium", "validated": True}
                )

        rules = formatted_rules

        # Define helper function for API calls based on ai_model (kept for backward compatibility, not used)
        async def call_llm_api(prompt_text: str) -> str:
            """Call the appropriate LLM API based on ai_model setting."""
            nonlocal sigma_response_truncation_warning
            logger.info(
                f"🔧 call_llm_api: ai_model='{ai_model}', will use {'LMStudio' if ai_model == 'lmstudio' else 'OpenAI (GPT-4o-mini)'}"
            )
            if ai_model == "lmstudio":
                # Use LMStudio API
                lmstudio_model = await _get_current_lmstudio_model()

                lmstudio_settings = _get_lmstudio_settings()

                # For reasoning models like Deepseek-R1, need more tokens for reasoning + output
                is_reasoning_model = "r1" in lmstudio_model.lower() or "reasoning" in lmstudio_model.lower()
                max_tokens = 2000 if is_reasoning_model else 800

                payload = {
                    "model": lmstudio_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries. No markdown, no explanations.",
                        },
                        {"role": "user", "content": prompt_text},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": lmstudio_settings["temperature"],
                    "top_p": lmstudio_settings["top_p"],
                }
                if lmstudio_settings["seed"] is not None:
                    payload["seed"] = lmstudio_settings["seed"]

                result = await _post_lmstudio_chat(
                    payload,
                    model_name=lmstudio_model,
                    timeout=300.0,
                    failure_context="Failed to generate SIGMA rules from LMStudio",
                )

                # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
                message = result["choices"][0]["message"]
                content_text = message.get("content", "")
                reasoning_text = message.get("reasoning_content", "")

                # For Deepseek-R1: prefer content if it exists and looks like YAML
                # Otherwise, try to extract YAML from reasoning_content
                if content_text and (content_text.strip().startswith("title:") or "title:" in content_text[:100]):
                    output = content_text
                    logger.debug("Using 'content' field for SIGMA generation (contains YAML)")
                elif reasoning_text:
                    # Try to extract YAML from reasoning_content
                    import re

                    yaml_match = re.search(
                        r"(?:^|\n)title:\s*[^\n]+\n(?:[^\n]+\n)*",
                        reasoning_text,
                        re.MULTILINE,
                    )
                    if yaml_match:
                        yaml_start = yaml_match.start()
                        yaml_block = reasoning_text[yaml_start:]
                        output = yaml_block
                        logger.debug("Extracted YAML from 'reasoning_content' field")
                    else:
                        # No YAML found in reasoning, use reasoning as-is
                        output = reasoning_text
                        logger.debug("Using 'reasoning_content' field for SIGMA generation (no YAML pattern found)")
                else:
                    output = content_text or reasoning_text or ""

                # Check if response was truncated
                finish_reason = result["choices"][0].get("finish_reason", "")
                if finish_reason == "length":
                    sigma_response_truncation_warning = (
                        f"Response truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. "
                        f"max_tokens={max_tokens} may need to be increased."
                    )
                    logger.warning(
                        f"SIGMA generation response was truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. max_tokens={max_tokens} may need to be increased."
                    )

                if not output or len(output.strip()) == 0:
                    logger.error("LLM returned empty response for SIGMA generation")
                    raise ValueError(
                        "LLM returned empty response for SIGMA generation. Check LMStudio is responding correctly."
                    )

                return output
            # Use OpenAI API (chatgpt)
            # Verify API key is valid before making request
            if not api_key:
                error_detail = "OpenAI API key is missing. Please configure it in Settings."
                logger.error("❌ OpenAI API key is None or empty when calling API")
                raise HTTPException(status_code=400, detail=error_detail)

            # Validate API key format before making request
            if not api_key.startswith("sk-"):
                error_detail = "Invalid API key format. OpenAI keys should start with 'sk-'. Please check your API key in Settings."
                logger.error(f"❌ API key validation failed: does not start with 'sk-' (length: {len(api_key)})")
                raise HTTPException(status_code=400, detail=error_detail)
            if len(api_key) < 20:
                error_detail = (
                    "API key appears to be truncated or invalid (too short). Please check your API key in Settings."
                )
                logger.error(f"❌ API key validation failed: too short (length: {len(api_key)})")
                raise HTTPException(status_code=400, detail=error_detail)
            # OpenAI API keys are typically 51 chars (sk-) or 100+ chars (sk-proj-)
            # If key is suspiciously short for a proj key, warn
            if api_key.startswith("sk-proj-") and len(api_key) < 100:
                logger.warning(
                    f"⚠️ API key appears truncated: sk-proj- key with length {len(api_key)} (expected 100+ chars)"
                )

            # Log API key info (masked) for debugging
            api_key_len = len(api_key) if api_key else 0
            api_key_start = api_key[:8] if api_key and len(api_key) >= 8 else "N/A"
            api_key_end = api_key[-4:] if api_key and len(api_key) >= 4 else "N/A"
            logger.info(
                f"🔑 Making OpenAI API call with api_key length: {api_key_len}, starts_with: {api_key_start}..., ends_with: ...{api_key_end}"
            )

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a SIGMA rule creation expert. Output ONLY valid YAML starting with 'title:'. Use exact 2-space indentation. logsource and detection must be nested dictionaries with proper structure. No markdown, no explanations, no code blocks.",
                                },
                                {"role": "user", "content": prompt_text},
                            ],
                            "max_tokens": 4000,
                            "temperature": 0.2,
                        },
                        timeout=120.0,
                    )

                    if response.status_code == 429:
                        error_detail = "OpenAI API rate limit exceeded. Please wait a few minutes and try again, or check your API usage limits."
                        logger.warning(f"OpenAI rate limit hit: {response.text}")
                        raise HTTPException(status_code=429, detail=error_detail)
                    if response.status_code != 200:
                        error_detail = f"OpenAI API error: {response.status_code}"
                        if response.status_code == 401:
                            # Try to get more details from the response
                            try:
                                error_json = response.json()
                                error_message = error_json.get("error", {}).get("message", "Unknown error")
                                logger.error(
                                    f"❌ OpenAI 401 error details: {error_message}, full response: {response.text}"
                                )
                                error_detail = f"OpenAI API key is invalid or expired. Error: {error_message}. Please check your API key in Settings."
                            except:
                                logger.error(f"❌ OpenAI 401 error, response text: {response.text}")
                                error_detail = (
                                    "OpenAI API key is invalid or expired. Please check your API key in Settings."
                                )
                        elif response.status_code == 402:
                            error_detail = "OpenAI API billing issue. Please check your account billing."
                        else:
                            logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                        raise HTTPException(status_code=500, detail=error_detail)
                except httpx.HTTPError as e:
                    logger.error(f"❌ HTTP error calling OpenAI API: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Network error calling OpenAI API: {str(e)}",
                    )
                except Exception as e:
                    logger.error(f"❌ Unexpected error calling OpenAI API: {e}")
                    raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

                result = response.json()
                return result["choices"][0]["message"]["content"]

        # Log final results
        if validation_results and all(result.get("is_valid", False) for result in validation_results):
            logger.info(f"SIGMA generation completed successfully after {len(conversation_log)} attempts")
        else:
            logger.warning(f"SIGMA generation completed with errors after {len(conversation_log)} attempts")

        # Get model name for metadata from config or fallback
        if agent_models and agent_models.get("SigmaAgent"):
            model_name = agent_models.get("SigmaAgent")
        elif sigma_provider == "lmstudio":
            model_name = agent_models.get("SigmaAgent") if agent_models else "lmstudio"
        else:
            model_name = "gpt-4o-mini"

        # Update article metadata with generated SIGMA rules
        current_metadata = article.article_metadata or {}

        # Get temperature and top_p from config if available
        sigma_temperature = agent_models.get("SigmaAgent_temperature", 0.0) if agent_models else 0.0
        sigma_top_p = agent_models.get("SigmaAgent_top_p", 0.9) if agent_models else 0.9

        current_metadata["sigma_rules"] = {
            "rules": rules,
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "ai_model": sigma_provider,  # Use provider from config
                "model_name": model_name,
                "author": author_name,
                "temperature": float(sigma_temperature),
                "top_p": float(sigma_top_p),
                "total_rules": len(rules),
                "valid_rules": len([r for r in rules if r.get("validated", False)]),
                "validation_results": validation_results,
                "conversation": conversation_log,
                "attempts": len(conversation_log) if conversation_log else 0,
                "successful": len(rules) > 0 and all(r.get("validated", False) for r in rules),
                "optimization": {
                    "enabled": True,
                    "cost_savings": cost_savings,
                    "tokens_saved": tokens_saved,
                    "chunks_removed": chunks_removed,
                    "min_confidence": min_confidence,
                },
                "errors": sigma_errors,
            },
        }

        # Update the article in the database
        from src.models.article import ArticleUpdate

        update_data = ArticleUpdate(article_metadata=current_metadata)
        await async_db_manager.update_article(article_id, update_data)

        # Compare generated rules to existing SigmaHQ rules
        from src.database.manager import DatabaseManager
        from src.services.sigma_matching_service import SigmaMatchingService

        similar_rules_by_generated = []
        try:
            db_manager = DatabaseManager()
            sync_session = db_manager.get_session()
            matching_service = SigmaMatchingService(sync_session)

            # For each generated rule, find similar existing Sigma rules
            for rule in rules:
                similar_matches = matching_service.compare_proposed_rule_to_embeddings(
                    proposed_rule=rule, threshold=0.0
                )
                if similar_matches:
                    similar_rules_by_generated.append(
                        {
                            "generated_rule": {
                                "title": rule.get("title"),
                                "description": rule.get("description"),
                            },
                            "similar_existing_rules": similar_matches[:5],  # Top 5 matches
                        }
                    )

            sync_session.close()
        except Exception as e:
            logger.warning(f"Failed to compare generated rules to SigmaHQ: {e}")

        # Collect all truncation warnings
        sigma_warnings = []
        if sigma_content_truncation_warning:
            sigma_warnings.append(sigma_content_truncation_warning)
        if sigma_prompt_truncation_warning:
            sigma_warnings.append(sigma_prompt_truncation_warning)
        if sigma_response_truncation_warning:
            sigma_warnings.append(sigma_response_truncation_warning)

        return {
            "success": len(rules) > 0,
            "rules": rules,
            "metadata": current_metadata["sigma_rules"]["metadata"],
            "matched_rules": matched_rules,
            "coverage_summary": coverage_summary,
            "similar_rules": similar_rules_by_generated,  # Similarity results for each generated rule
            "cached": False,
            "error": None if len(rules) > 0 else "No valid SIGMA rules could be generated",
            "warnings": sigma_warnings if sigma_warnings else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SIGMA rules generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def calculate_semantic_overlap(generated_rule: dict, sigmahq_rule: dict) -> dict[str, Any]:
    """
    Calculate semantic overlap between two SIGMA rules by comparing actual detection values.

    Args:
        generated_rule: The generated rule dictionary
        sigmahq_rule: The SigmaHQ rule dictionary to compare against

    Returns:
        Dictionary with overlap metrics
    """

    def extract_values_from_detection(detection: dict, field_name: str) -> Set[str]:
        """Extract all values for a specific field from detection logic."""
        values = set()
        if not isinstance(detection, dict):
            return values

        for key, value in detection.items():
            # Skip condition and timeframe keys
            if key in ["condition", "timeframe"]:
                continue

            if isinstance(value, dict):
                # Recursively search nested structures
                nested_values = extract_values_from_detection(value, field_name)
                values.update(nested_values)

                # Check if this dict has the field we're looking for
                for field_key, field_value in value.items():
                    if field_name.lower() in field_key.lower():
                        if isinstance(field_value, list):
                            values.update(str(v).lower() for v in field_value)
                        elif isinstance(field_value, str):
                            values.add(field_value.lower())

        return values

    def normalize_path(path: str) -> str:
        """Normalize file paths for comparison."""
        return path.lower().replace("\\\\", "\\").replace("/", "\\").strip()

    try:
        gen_detection = generated_rule.get("detection", {})
        sig_detection = sigmahq_rule.get("detection", {})

        # Extract process/image names
        gen_processes = extract_values_from_detection(gen_detection, "image")
        gen_processes.update(extract_values_from_detection(gen_detection, "initiatingprocess"))
        gen_processes.update(extract_values_from_detection(gen_detection, "parentimage"))

        sig_processes = extract_values_from_detection(sig_detection, "image")
        sig_processes.update(extract_values_from_detection(sig_detection, "initiatingprocess"))
        sig_processes.update(extract_values_from_detection(sig_detection, "parentimage"))

        # Extract file paths
        gen_paths = extract_values_from_detection(gen_detection, "path")
        gen_paths.update(extract_values_from_detection(gen_detection, "folderpath"))
        gen_paths.update(extract_values_from_detection(gen_detection, "targetfilename"))
        gen_paths = {normalize_path(p) for p in gen_paths}

        sig_paths = extract_values_from_detection(sig_detection, "path")
        sig_paths.update(extract_values_from_detection(sig_detection, "folderpath"))
        sig_paths.update(extract_values_from_detection(sig_detection, "targetfilename"))
        sig_paths = {normalize_path(p) for p in sig_paths}

        # Extract command line keywords
        gen_cmdline = extract_values_from_detection(gen_detection, "commandline")
        sig_cmdline = extract_values_from_detection(sig_detection, "commandline")

        # Calculate overlaps
        process_overlap = len(gen_processes & sig_processes) if gen_processes and sig_processes else 0
        path_overlap = len(gen_paths & sig_paths) if gen_paths and sig_paths else 0
        cmdline_overlap = len(gen_cmdline & sig_cmdline) if gen_cmdline and sig_cmdline else 0

        # Calculate ratios
        total_gen_indicators = len(gen_processes) + len(gen_paths) + len(gen_cmdline)
        total_sig_indicators = len(sig_processes) + len(sig_paths) + len(sig_cmdline)
        total_overlaps = process_overlap + path_overlap + cmdline_overlap

        # Overall semantic overlap ratio
        if total_gen_indicators == 0 or total_sig_indicators == 0:
            semantic_overlap_ratio = 0.0
        else:
            # Use average of indicators from both rules as denominator
            avg_indicators = (total_gen_indicators + total_sig_indicators) / 2
            semantic_overlap_ratio = total_overlaps / avg_indicators if avg_indicators > 0 else 0.0

        return {
            "semantic_overlap_ratio": min(1.0, semantic_overlap_ratio),
            "process_overlap": process_overlap,
            "path_overlap": path_overlap,
            "cmdline_overlap": cmdline_overlap,
            "gen_processes": list(gen_processes),
            "sig_processes": list(sig_processes),
            "gen_paths": list(gen_paths),
            "sig_paths": list(sig_paths),
            "gen_cmdline": list(gen_cmdline),
            "sig_cmdline": list(sig_cmdline),
        }

    except Exception as e:
        logger.warning(f"Error calculating semantic overlap: {e}")
        return {
            "semantic_overlap_ratio": 0.0,
            "process_overlap": 0,
            "path_overlap": 0,
            "cmdline_overlap": 0,
            "gen_processes": [],
            "sig_processes": [],
            "gen_paths": [],
            "sig_paths": [],
            "gen_cmdline": [],
            "sig_cmdline": [],
        }


@router.get("/{article_id}/sigma-matches")
async def api_get_sigma_matches(article_id: int, force: bool = False):
    """
    Get Sigma rule matches by comparing generated SIGMA rules to embedded SigmaHQ rules
    using behavioral novelty assessment.

    Uses behavioral novelty assessment (per build spec):
    - Canonicalization of detection logic
    - Atomic predicate extraction (field+operator+value)
    - Structural similarity metrics (AST comparison)
    - Weighted similarity: 0.70 × atom_jaccard + 0.30 × logic_shape

    No LLM reranking - purely algorithmic as per specification.
    """
    try:
        from src.database.async_manager import AsyncDatabaseManager
        from src.database.manager import DatabaseManager
        from src.services.sigma_matching_service import SigmaMatchingService

        # Get article with generated rules
        async_db_manager = AsyncDatabaseManager()
        article = await async_db_manager.get_article(article_id)

        if not article:
            raise HTTPException(status_code=404, detail=f"Article {article_id} not found")

        # OPTIONAL CACHE: If not forcing, return cached matches from article metadata when available
        # Only use cache if it's from the new novelty assessment system with proper classification (version 2.1+)
        if not force and article.article_metadata and article.article_metadata.get("sigma_similar_cache"):
            cached = article.article_metadata.get("sigma_similar_cache")
            cache_version = cached.get("cache_version", "1.0")  # Old caches don't have version

            # Invalidate old caches (version < 2.1) - need to regenerate with proper novelty_label classification
            if cache_version < "2.1":
                logger.info(
                    f"Invalidating old cache (version {cache_version}), regenerating with novelty_label classification"
                )
            else:
                return {
                    "success": True,
                    "matches": cached.get("matches", []),
                    "coverage_summary": cached.get(
                        "coverage_summary",
                        {"covered": 0, "extend": 0, "new": 0, "total": 0},
                    ),
                    "cached": True,
                }

        # Get generated SIGMA rules from article metadata
        generated_rules = []
        if article.article_metadata and article.article_metadata.get("sigma_rules"):
            generated_rules = article.article_metadata.get("sigma_rules", {}).get("rules", [])

        if not generated_rules:
            return {
                "success": True,
                "matches": [],
                "coverage_summary": {"covered": 0, "extend": 0, "new": 0, "total": 0},
                "message": "No generated SIGMA rules found. Please generate rules first.",
            }

        # Compare each generated rule to existing embedded SigmaHQ rules
        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            matching_service = SigmaMatchingService(session)

            # Collect all matches across all generated rules
            all_matches = {}

            for generated_rule in generated_rules:
                try:
                    # Normalize rule structure - ensure all required fields exist
                    normalized_rule = {
                        "title": generated_rule.get("title", ""),
                        "description": generated_rule.get("description", ""),
                        "tags": generated_rule.get("tags", []),
                        "logsource": generated_rule.get("logsource", {}),
                        "detection": generated_rule.get("detection", {}),
                        "level": generated_rule.get("level"),
                        "status": generated_rule.get("status"),
                    }

                    # Skip if essential fields are missing
                    if not normalized_rule["title"] or not normalized_rule["detection"]:
                        logger.warning(
                            f"Skipping rule with missing essential fields: {normalized_rule.get('title', 'Unknown')}"
                        )
                        continue

                    # Behavioral novelty assessment (per build spec)
                    # Uses canonicalization, atomic predicates, and structural similarity metrics
                    # No LLM reranking - purely algorithmic as per specification
                    similar_matches = matching_service.compare_proposed_rule_to_embeddings(
                        proposed_rule=normalized_rule,
                        threshold=0.0,  # No threshold - get top matches
                    )

                    logger.debug(
                        f"Rule '{normalized_rule['title']}' found {len(similar_matches)} similar rules via behavioral novelty assessment"
                    )

                    # Deduplicate by rule_id, keeping highest similarity score
                    # Also store reference to generated rule for semantic analysis
                    for match in similar_matches:
                        rule_id = match.get("rule_id")
                        if rule_id not in all_matches or match.get("similarity", 0) > all_matches[rule_id].get(
                            "similarity", 0
                        ):
                            match["_generated_rule"] = normalized_rule  # Store for semantic overlap calculation
                            all_matches[rule_id] = match
                except Exception as e:
                    logger.error(f"Error comparing rule '{generated_rule.get('title', 'Unknown')}': {e}")
                    import traceback

                    logger.error(traceback.format_exc())
                    continue

            # Sort by similarity (descending) and return top matches
            matches = sorted(all_matches.values(), key=lambda x: x.get("similarity", 0), reverse=True)[:20]

            # Classify each match using behavioral novelty assessment (per spec)
            # Use novelty_label directly from behavioral metrics
            for match in matches:
                # Get behavioral metrics from novelty assessment
                behavioral_similarity = match.get("similarity", 0)
                atom_jaccard = match.get("atom_jaccard", 0.0)
                logic_shape_raw = match.get("logic_shape_similarity")
                # Handle None (early exit case) - treat as perfect match for classification
                logic_shape = 1.0 if logic_shape_raw is None else logic_shape_raw

                # Debug logging
                logic_shape_display = "N/A" if match.get("logic_shape_similarity") is None else f"{logic_shape:.3f}"
                logger.debug(
                    f"Classifying match '{match.get('rule_id', 'unknown')}': "
                    f"atom_jaccard={atom_jaccard:.3f}, logic_shape={logic_shape_display}"
                )

                # Check for exact hash match (duplicate)
                is_exact_match = match.get("exact_hash_match", False)

                # Classify using behavioral novelty thresholds (per spec)
                # DUPLICATE: atom_jaccard > 0.95 AND logic_similarity > 0.95
                # SIMILAR: atom_jaccard > 0.80
                # NOVEL: Everything else
                if is_exact_match:
                    novelty_label = "DUPLICATE"
                    logger.debug(f"Match '{match.get('rule_id')}' classified as DUPLICATE (exact hash match)")
                elif atom_jaccard > 0.95 and logic_shape > 0.95:
                    novelty_label = "DUPLICATE"
                    logger.debug(
                        f"Match '{match.get('rule_id')}' classified as DUPLICATE (atom_jaccard={atom_jaccard:.3f}, logic_shape={logic_shape_display})"
                    )
                elif atom_jaccard > 0.80:
                    novelty_label = "SIMILAR"
                    logger.debug(
                        f"Match '{match.get('rule_id')}' classified as SIMILAR (atom_jaccard={atom_jaccard:.3f})"
                    )
                else:
                    novelty_label = "NOVEL"
                    logger.debug(
                        f"Match '{match.get('rule_id')}' classified as NOVEL (atom_jaccard={atom_jaccard:.3f}, logic_shape={logic_shape_display})"
                    )

                # Store novelty classification
                match["novelty_label"] = novelty_label

                # Map novelty_label to coverage_status for UI display
                # DUPLICATE → covered, SIMILAR → extend, NOVEL → new
                if novelty_label == "DUPLICATE":
                    match["coverage_status"] = "covered"
                elif novelty_label == "SIMILAR":
                    match["coverage_status"] = "extend"
                else:  # NOVEL
                    match["coverage_status"] = "new"

                # Clean up internal fields before returning
                if "_generated_rule" in match:
                    del match["_generated_rule"]
                # Remove coverage_reasoning if present (removed from UI)
                if "coverage_reasoning" in match:
                    del match["coverage_reasoning"]

            # Prepare response
            # Prepare response
            # Note: Using pure behavioral novelty assessment (no LLM reranking per spec)
            result = {
                "success": True,
                "matches": matches,
                "coverage_summary": {
                    "covered": len([m for m in matches if m.get("coverage_status") == "covered"]),
                    "extend": len([m for m in matches if m.get("coverage_status") == "extend"]),
                    "new": len([m for m in matches if m.get("coverage_status") == "new"]),
                    "total": len(matches),
                },
                "assessment_method": "behavioral_novelty",
            }

            # Save cache to article metadata (server-side) for subsequent fast displays
            try:
                current_metadata = article.article_metadata or {}
                current_metadata["sigma_similar_cache"] = {
                    "matches": result["matches"],
                    "coverage_summary": result["coverage_summary"],
                    "cached_at": datetime.now().isoformat(),
                    "cache_version": "2.1",  # Mark as novelty_label-based classification cache
                    "assessment_method": "behavioral_novelty",
                }
                from src.models.article import ArticleUpdate

                update_data = ArticleUpdate(article_metadata=current_metadata)
                await async_db_manager.update_article(article_id, update_data)
            except Exception as cache_err:
                logger.debug(f"Sigma similar cache save skipped: {cache_err}")

            return result
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Sigma matches for article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sigma-rules-yaml/{rule_id}")
async def api_get_sigma_rule_yaml(rule_id: str):
    """Get the YAML file contents for a specific Sigma rule (reconstructed from database)."""
    try:
        import yaml

        from src.database.manager import DatabaseManager
        from src.database.models import SigmaRuleTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            # Query the rule by rule_id
            rule = session.query(SigmaRuleTable).filter_by(rule_id=rule_id).first()

            if not rule:
                raise HTTPException(status_code=404, detail=f"Sigma rule '{rule_id}' not found")

            # Reconstruct YAML from database fields (using regular dict, not OrderedDict)
            rule_dict = {}
            rule_dict["title"] = rule.title
            rule_dict["id"] = rule.rule_id

            if rule.status:
                rule_dict["status"] = rule.status

            if rule.description:
                rule_dict["description"] = rule.description

            if rule.rule_references:
                rule_dict["references"] = list(rule.rule_references)

            if rule.author:
                rule_dict["author"] = rule.author

            if rule.date:
                rule_dict["date"] = rule.date.strftime("%Y/%m/%d")

            if rule.tags:
                rule_dict["tags"] = list(rule.tags)

            if rule.logsource:
                rule_dict["logsource"] = dict(rule.logsource)

            if rule.detection:
                rule_dict["detection"] = dict(rule.detection)

            if rule.fields:
                rule_dict["fields"] = list(rule.fields)

            if rule.false_positives:
                rule_dict["falsepositives"] = list(rule.false_positives)

            if rule.level:
                rule_dict["level"] = rule.level

            # Convert to YAML string with safe_dump to avoid Python object tags
            yaml_content = yaml.safe_dump(
                rule_dict,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=1000,
            )

            return {
                "success": True,
                "rule_id": rule.rule_id,
                "title": rule.title,
                "file_path": rule.file_path or "N/A",
                "yaml_content": yaml_content,
            }
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting YAML for rule_id '{rule_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sigma-rules/{rule_id}")
async def api_get_sigma_rule_details(rule_id: str):
    """Get full details of a specific Sigma rule by its rule_id."""
    try:
        from src.database.manager import DatabaseManager
        from src.database.models import SigmaRuleTable

        db_manager = DatabaseManager()
        session = db_manager.get_session()

        try:
            # Query the rule by rule_id
            rule = session.query(SigmaRuleTable).filter_by(rule_id=rule_id).first()

            if not rule:
                raise HTTPException(status_code=404, detail=f"Sigma rule '{rule_id}' not found")

            # Convert to dictionary with proper JSON serialization

            def convert_value(value):
                if value is None:
                    return None
                if isinstance(value, (dict, list)):
                    return value
                if isinstance(value, (tuple, set)):
                    return list(value)
                return value

            rule_data = {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "description": rule.description,
                "logsource": convert_value(rule.logsource),
                "detection": convert_value(rule.detection),
                "tags": list(rule.tags) if rule.tags else [],
                "level": rule.level,
                "status": rule.status,
                "author": rule.author,
                "date": rule.date.isoformat() if rule.date else None,
                "rule_references": list(rule.rule_references) if rule.rule_references else [],
                "false_positives": list(rule.false_positives) if rule.false_positives else [],
                "fields": list(rule.fields) if rule.fields else [],
                "file_path": rule.file_path,
                "repo_commit_sha": rule.repo_commit_sha,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            }

            return {"success": True, "rule": rule_data}
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Sigma rule details for rule_id '{rule_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DEPRECATED: Custom prompt endpoint removed (AI/ML Assistant modal deprecated)
"""
@router.post("/{article_id}/custom-prompt")
async def api_custom_prompt(article_id: int, request: Request):
    \"\"\"Process a custom AI prompt for an article.\"\"\"
    try:
        # Get the article
        article = await async_db_manager.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Get request body
        body = await request.json()
        prompt = body.get("prompt")
        # Try header first (prevents corruption with large payloads), fallback to body for backward compatibility
        # For Anthropic, check X-Anthropic-API-Key header, for OpenAI check X-OpenAI-API-Key
        api_key_raw = None
        if body.get("ai_model", "chatgpt") == "anthropic":
            api_key_raw = request.headers.get("X-Anthropic-API-Key") or body.get(
                "api_key"
            )
        else:
            api_key_raw = request.headers.get("X-OpenAI-API-Key") or body.get("api_key")
        # Strip whitespace from API key (common issue when copying/pasting)
        api_key = api_key_raw.strip() if api_key_raw else None
        ai_model = body.get("ai_model", "chatgpt")

        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        # Only require API key for cloud-based models
        if ai_model in ["chatgpt", "anthropic"] and not api_key:
            key_type = "OpenAI" if ai_model == "chatgpt" else "Anthropic"
            raise HTTPException(
                status_code=400,
                detail=f"{key_type} API key is required. Please configure it in Settings.",
            )

        # Prepare the article content for analysis
        if not article.content:
            raise HTTPException(
                status_code=400, detail="Article content is required for analysis"
            )

        # Get the source name from source_id
        source = await async_db_manager.get_source(article.source_id)
        source_name = source.name if source else f"Source {article.source_id}"

        # Create the full prompt with article context
        full_prompt = f\"\"\"Article Title: {article.title}
Source: {source_name}
URL: {article.canonical_url or "N/A"}

Article Content:
{article.content}

User Request: {prompt}

Please provide a detailed analysis based on the article content and the user's request.\"\"\"

        # Call the appropriate AI API
        if ai_model == "anthropic":
            # Use Anthropic API with rate limit handling
            anthropic_api_url = os.getenv(
                "ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages"
            )

            payload = {
                "model": "claude-sonnet-4-5",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": full_prompt}],
            }

            response = await _call_anthropic_with_retry(
                api_key=api_key,
                payload=payload,
                anthropic_api_url=anthropic_api_url,
                timeout=60.0,
            )

            result = response.json()
            analysis = result["content"][0]["text"]
            model_used = "anthropic"
            model_name = "claude-sonnet-4-5"
        elif ai_model == "ollama":
            # Use Ollama API
            ollama_url = os.getenv("LLM_API_URL", "http://cti_ollama:11434")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": "llama3.2:1b",
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 2000},
                    },
                    timeout=300.0,
                )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Ollama API error: {error_detail}")
                    raise HTTPException(
                        status_code=500, detail=f"Ollama API error: {error_detail}"
                    )

                result = response.json()
                analysis = result["response"]
                model_used = "ollama"
                model_name = "llama3.2:1b"
        elif ai_model == "tinyllama":
            # Use Ollama API with TinyLlama
            ollama_url = os.getenv("LLM_API_URL", "http://cti_ollama:11434")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": "tinyllama",
                        "prompt": full_prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 2000},
                    },
                    timeout=300.0,
                )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Ollama API error: {error_detail}")
                    raise HTTPException(
                        status_code=500, detail=f"Ollama API error: {error_detail}"
                    )

                result = response.json()
                analysis = result["response"]
                model_used = "tinyllama"
                model_name = "tinyllama"
        elif ai_model == "lmstudio":
            # Use LMStudio API
            lmstudio_model = await _get_current_lmstudio_model()

            lmstudio_settings = _get_lmstudio_settings()
            payload = {
                "model": lmstudio_model,
                "messages": [{"role": "user", "content": full_prompt}],
                "max_tokens": 2000,
                "temperature": lmstudio_settings["temperature"],
                "top_p": lmstudio_settings["top_p"],
            }
            if lmstudio_settings["seed"] is not None:
                payload["seed"] = lmstudio_settings["seed"]

            result = await _post_lmstudio_chat(
                payload,
                model_name=lmstudio_model,
                timeout=300.0,
                failure_context="LMStudio API error",
            )

            analysis = result["choices"][0]["message"]["content"]
            model_used = "lmstudio"
            model_name = lmstudio_model
        else:
            # Use OpenAI API (default)
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": full_prompt}],
                        "max_tokens": 2000,
                        "temperature": 0.3,
                    },
                    timeout=60.0,
                )

                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"OpenAI API error: {error_detail}")
                    raise HTTPException(
                        status_code=500, detail=f"OpenAI API error: {error_detail}"
                    )

                result = response.json()
                analysis = result["choices"][0]["message"]["content"]
                model_used = "openai"
                model_name = "gpt-4o"

        # Save the analysis to the article's metadata
        if article.article_metadata is None:
            article.article_metadata = {}

        article.article_metadata["custom_prompt"] = {
            "prompt": prompt,
            "response": analysis,
            "analyzed_at": datetime.now().isoformat(),
            "model_used": model_used,
            "model_name": model_name,
        }

        # Update the article in the database
        from src.models.article import ArticleUpdate

        update_data = ArticleUpdate(article_metadata=article.article_metadata)
        await async_db_manager.update_article(article_id, update_data)

        return {
            "success": True,
            "article_id": article_id,
            "response": analysis,
            "analyzed_at": article.article_metadata["custom_prompt"]["analyzed_at"],
            "model_used": model_used,
            "model_name": model_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom prompt error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""
