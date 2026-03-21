"""dify-admin: Dify Console API client library and CLI."""

from dify_admin.client import DifyClient
from dify_admin.exceptions import (
    DifyAdminError,
    DifyApiError,
    DifyConnectionError,
    DifyMethodNotAllowedError,
    DifyNotFoundError,
    DifyPermissionError,
    DifyServerError,
    DifyValidationError,
)

__all__ = [
    "DifyClient",
    "DifyAdminError",
    "DifyApiError",
    "DifyConnectionError",
    "DifyMethodNotAllowedError",
    "DifyNotFoundError",
    "DifyPermissionError",
    "DifyServerError",
    "DifyValidationError",
]
__version__ = "0.1.0"
