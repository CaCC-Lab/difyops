"""Diagnostic checks for dify-admin.

Verifies connectivity, authentication, and API availability.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from dify_admin.client import DifyClient


def run_checks(
    url: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> list[dict[str, Any]]:
    """Run all diagnostic checks and return results.

    Args:
        url: Dify URL (falls back to DIFY_URL env or localhost)
        email: Account email (falls back to DIFY_EMAIL env)
        password: Account password (falls back to DIFY_PASSWORD env)

    Returns:
        List of check results with: name, status (pass/fail/warn), message
    """
    url = url or os.environ.get("DIFY_URL") or "http://localhost:5001"
    email = email or os.environ.get("DIFY_EMAIL")
    password = password or os.environ.get("DIFY_PASSWORD")

    results: list[dict[str, Any]] = []

    # Check 1: URL reachability
    results.append(_check_reachability(url))

    # Check 2: Setup status
    results.append(_check_setup(url))

    # Check 3: Credentials configured
    results.append(_check_credentials(email, password))

    # Check 4: Authentication
    if email and password and results[0]["status"] == "pass":
        results.append(_check_auth(url, email, password))
    else:
        results.append(
            {
                "name": "auth",
                "status": "skip",
                "message": "Skipped (no credentials or server unreachable)",
            }
        )

    # Check 5: API access (list apps)
    if len(results) >= 4 and results[3]["status"] == "pass":
        results.append(_check_api_access(url, email, password))
    else:
        results.append(
            {
                "name": "api_access",
                "status": "skip",
                "message": "Skipped (auth not available)",
            }
        )

    return results


def _check_reachability(url: str) -> dict[str, Any]:
    """Check if Dify server is reachable."""
    try:
        resp = httpx.get(f"{url}/console/api/setup", timeout=10.0)
        return {
            "name": "reachability",
            "status": "pass",
            "message": f"Server reachable at {url} (HTTP {resp.status_code})",
        }
    except httpx.ConnectError:
        return {
            "name": "reachability",
            "status": "fail",
            "message": f"Cannot connect to {url}. Is Dify running?",
        }
    except Exception as e:
        return {
            "name": "reachability",
            "status": "fail",
            "message": f"Connection error: {e}",
        }


def _check_setup(url: str) -> dict[str, Any]:
    """Check Dify setup status."""
    try:
        resp = httpx.get(f"{url}/console/api/setup", timeout=10.0)
        if resp.status_code == 200:
            step = resp.json().get("step", "unknown")
            return {
                "name": "setup",
                "status": "pass",
                "message": f"Setup complete (step: {step})",
            }
        return {
            "name": "setup",
            "status": "warn",
            "message": f"Setup endpoint returned HTTP {resp.status_code}",
        }
    except Exception as e:
        return {
            "name": "setup",
            "status": "fail",
            "message": f"Cannot check setup: {e}",
        }


def _check_credentials(email: str | None, password: str | None) -> dict[str, Any]:
    """Check if credentials are configured."""
    if email and password:
        return {
            "name": "credentials",
            "status": "pass",
            "message": f"Credentials configured (email: {email})",
        }
    missing = []
    if not email:
        missing.append("DIFY_EMAIL")
    if not password:
        missing.append("DIFY_PASSWORD")
    return {
        "name": "credentials",
        "status": "fail",
        "message": f"Missing: {', '.join(missing)}",
    }


def _check_auth(url: str, email: str, password: str) -> dict[str, Any]:
    """Check if authentication works."""
    try:
        with DifyClient(url) as client:
            client.login(email, password)
        return {
            "name": "auth",
            "status": "pass",
            "message": "Authentication successful",
        }
    except Exception as e:
        return {
            "name": "auth",
            "status": "fail",
            "message": f"Authentication failed: {e}",
        }


def _check_api_access(url: str, email: str | None, password: str | None) -> dict[str, Any]:
    """Check if API access works (list apps)."""
    try:
        with DifyClient(url) as client:
            client.login(email, password)  # type: ignore[arg-type]
            apps = client.apps_list()
        return {
            "name": "api_access",
            "status": "pass",
            "message": f"API access OK ({len(apps)} apps found)",
        }
    except Exception as e:
        return {
            "name": "api_access",
            "status": "fail",
            "message": f"API access failed: {e}",
        }
