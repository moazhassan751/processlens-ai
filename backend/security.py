"""
ProcessLens — Security & API Key Authentication
=================================================
Lightweight shared-secret protection for mutating write endpoints (Phase H6).
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Optional

from fastapi import Header, HTTPException, status
from backend.config import API_KEY

logger = logging.getLogger("processlens.security")


def get_configured_api_key() -> Optional[str]:
    """
    Return the configured shared secret API key, or None if authentication is disabled.
    Checks os.environ dynamically first to allow runtime/test environment variable
    adjustments, falling back to backend.config.API_KEY.
    """
    env_key = os.environ.get("API_KEY", "").strip()
    if env_key:
        return env_key
    if API_KEY and API_KEY.strip():
        return API_KEY.strip()
    return None


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> bool:
    """
    FastAPI dependency to protect mutating/write endpoints with a shared secret.

    Behavior:
      1. If API_KEY is unset or empty:
         - Allows the request without authentication (backward-compatible demo mode).
      2. If API_KEY is configured:
         - Validates the incoming X-API-Key header against the configured secret.
         - Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
         - Raises HTTP 401 Unauthorized with detail: 'Invalid or missing API key'
           if the header is missing or incorrect.
         - Never logs or exposes the configured secret.
    """
    expected_key = get_configured_api_key()
    if not expected_key:
        # Auth disabled
        return True

    # If header is missing or empty, reject with 401
    if not x_api_key or not x_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    # Constant-time comparison
    if not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    return True
