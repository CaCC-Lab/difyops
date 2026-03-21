"""Exception hierarchy for dify-admin.

Provides meaningful error messages for API errors, making it easy for
both humans and AI assistants to understand what went wrong and how to fix it.
"""

from __future__ import annotations

from typing import Any

import httpx


class DifyAdminError(Exception):
    """Base exception for all dify-admin errors."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        self.hint = hint
        if hint:
            super().__init__(f"{message} (hint: {hint})")
        else:
            super().__init__(message)


class DifyApiError(DifyAdminError):
    """Error from Dify Console API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        method: str = "",
        path: str = "",
        detail: str = "",
        hint: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.method = method
        self.path = path
        self.detail = detail
        super().__init__(message, hint=hint)


class DifyNotFoundError(DifyApiError):
    """Resource not found (404)."""

    def __init__(self, resource: str, resource_id: str, **kwargs: Any) -> None:
        super().__init__(
            f"{resource} not found: {resource_id}",
            status_code=404,
            hint=f"Check that the {resource.lower()} ID is correct",
            **kwargs,
        )


class DifyPermissionError(DifyApiError):
    """Permission denied (403)."""

    def __init__(self, message: str = "Permission denied", **kwargs: Any) -> None:
        super().__init__(
            message,
            status_code=403,
            hint="Check your account permissions in Dify",
            **kwargs,
        )


class DifyMethodNotAllowedError(DifyApiError):
    """Method not allowed (405) — typically wrong endpoint for app mode."""

    def __init__(
        self,
        message: str = "Method not allowed",
        *,
        path: str = "",
        **kwargs: Any,
    ) -> None:
        hint = None
        if "model-config" in path:
            hint = (
                "model-config is not available for advanced-chat/workflow apps. "
                "Use apps_get to view the full app details instead"
            )
        super().__init__(message, status_code=405, path=path, hint=hint, **kwargs)


class DifyValidationError(DifyApiError):
    """Validation error (400)."""

    def __init__(self, message: str = "Invalid request", **kwargs: Any) -> None:
        super().__init__(message, status_code=400, **kwargs)


class DifyServerError(DifyApiError):
    """Server error (5xx)."""

    def __init__(self, message: str = "Dify server error", **kwargs: Any) -> None:
        super().__init__(
            message,
            hint="The Dify server encountered an internal error. Check server logs",
            **kwargs,
        )


class DifyConnectionError(DifyAdminError):
    """Cannot connect to Dify server."""

    def __init__(self, url: str, cause: str = "") -> None:
        detail = f": {cause}" if cause else ""
        super().__init__(
            f"Cannot connect to Dify at {url}{detail}",
            hint="Check that Dify is running and the URL is correct",
        )


def raise_for_dify_status(response: httpx.Response) -> None:
    """Check response status and raise a meaningful DifyApiError if not OK.

    Args:
        response: httpx Response to check

    Raises:
        DifyNotFoundError: 404
        DifyPermissionError: 403
        DifyMethodNotAllowedError: 405
        DifyValidationError: 400
        DifyServerError: 5xx
        DifyApiError: other non-2xx
    """
    if response.is_success:
        return

    status = response.status_code
    method = response.request.method
    path = str(response.request.url.path)

    # Try to extract error detail from response body
    detail = ""
    try:
        body = response.json()
        detail = body.get("message", "") or body.get("error", "") or body.get("msg", "")
    except Exception:
        detail = response.text[:200] if response.text else ""

    common = {"method": method, "path": path, "detail": detail}

    if status == 400:
        raise DifyValidationError(
            detail or "Invalid request",
            **common,
        )
    if status == 403:
        raise DifyPermissionError(
            detail or "Permission denied",
            **common,
        )
    if status == 404:
        # Try to infer resource type from path
        resource = "Resource"
        resource_id = ""
        parts = path.rstrip("/").split("/")
        if "apps" in parts:
            resource = "App"
            idx = parts.index("apps")
            if idx + 1 < len(parts):
                resource_id = parts[idx + 1]
        elif "datasets" in parts:
            resource = "Knowledge base"
            idx = parts.index("datasets")
            if idx + 1 < len(parts):
                resource_id = parts[idx + 1]
        elif "documents" in parts:
            resource = "Document"
            idx = parts.index("documents")
            if idx + 1 < len(parts):
                resource_id = parts[idx + 1]
        raise DifyNotFoundError(resource, resource_id, **common)
    if status == 405:
        raise DifyMethodNotAllowedError(
            detail or f"{method} not allowed on {path}",
            path=path,
            **{k: v for k, v in common.items() if k != "path"},
        )
    if status >= 500:
        raise DifyServerError(
            detail or f"Server error (HTTP {status})",
            status_code=status,
            **common,
        )

    # Catch-all for other status codes
    raise DifyApiError(
        detail or f"API error (HTTP {status})",
        status_code=status,
        **common,
    )
