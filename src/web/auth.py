"""
Authentication utilities for securing sensitive API endpoints.

Provides API key authentication for administrative operations.
"""

import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_admin_api_key() -> str:
    """
    Get the admin API key from environment.

    Returns:
        Admin API key

    Raises:
        RuntimeError: If API key is not configured
    """
    api_key = os.getenv("ADMIN_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ADMIN_API_KEY environment variable not set. "
            "Set it to secure administrative endpoints. "
            "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    return api_key


async def verify_admin_api_key(api_key: Annotated[str | None, Security(api_key_header)]) -> str:
    """
    Verify admin API key for administrative operations.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        Verified API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    try:
        expected_key = get_admin_api_key()
    except RuntimeError as e:
        # Server misconfiguration - API key not set
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication not configured",
        ) from e

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key


# Dependency for routes that require admin authentication
RequireAdminAuth = Depends(verify_admin_api_key)
