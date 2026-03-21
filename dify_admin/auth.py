"""Dify authentication handling.

Manages login flow with Base64 password encoding,
cookie-based session tokens, and CSRF token extraction.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class DifySession:
    """Active Dify console session with tokens."""

    access_token: str
    refresh_token: str
    csrf_token: str

    def cookies(self) -> dict[str, str]:
        """Return cookies dict for requests."""
        return {
            "access_token": self.access_token,
            "csrf_token": self.csrf_token,
        }

    def headers(self) -> dict[str, str]:
        """Return headers dict with CSRF token."""
        return {
            "X-CSRF-Token": self.csrf_token,
        }


def login(
    base_url: str,
    email: str,
    password: str,
    http_client: Optional[httpx.Client] = None,
) -> DifySession:
    """Login to Dify Console API.

    Dify v1.13+ expects the password to be Base64-encoded (not RSA).
    Tokens are returned via Set-Cookie headers.

    Args:
        base_url: Dify API base URL (e.g. http://localhost:5001)
        email: Account email
        password: Plaintext password (will be Base64-encoded)
        http_client: Optional httpx.Client for connection reuse

    Returns:
        DifySession with access, refresh, and CSRF tokens

    Raises:
        AuthenticationError: If login fails
    """
    password_b64 = base64.b64encode(password.encode("utf-8")).decode("utf-8")

    client = http_client or httpx.Client()
    try:
        response = client.post(
            f"{base_url}/console/api/login",
            json={"email": email, "password": password_b64},
        )
    finally:
        if http_client is None:
            client.close()

    if response.status_code != 200:
        try:
            detail = response.json().get("message", "Unknown error")
        except Exception:
            detail = response.text[:200] or f"HTTP {response.status_code}"
        raise AuthenticationError(f"Login failed: {detail}")

    access_token = _extract_cookie(response, "access_token")
    refresh_token = _extract_cookie(response, "refresh_token")
    csrf_token = _extract_cookie(response, "csrf_token")

    if not access_token or not csrf_token:
        raise AuthenticationError("Login succeeded but tokens not found in response cookies")

    return DifySession(
        access_token=access_token,
        refresh_token=refresh_token or "",
        csrf_token=csrf_token,
    )


def _extract_cookie(response: httpx.Response, name: str) -> str:
    """Extract a cookie value from response Set-Cookie headers."""
    for header_value in response.headers.get_list("set-cookie"):
        if header_value.startswith(f"{name}="):
            return header_value.split("=", 1)[1].split(";")[0]
    return ""


class AuthenticationError(Exception):
    """Raised when Dify authentication fails."""
