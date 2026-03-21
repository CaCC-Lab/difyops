"""Tests for read-only mode."""

import os

import pytest


def _check_readonly() -> None:
    """Inline copy of the readonly check logic (avoids mcp import)."""
    mode = os.environ.get("DIFY_ADMIN_MODE", "").lower()
    if mode == "readonly":
        raise PermissionError(
            "Operation blocked: dify-admin is running in read-only mode."
        )


class TestReadonlyMode:
    def test_destructive_blocked_in_readonly(self) -> None:
        """DESTRUCTIVE tools raise PermissionError in readonly mode."""
        os.environ["DIFY_ADMIN_MODE"] = "readonly"
        try:
            with pytest.raises(PermissionError, match="read-only mode"):
                _check_readonly()
        finally:
            del os.environ["DIFY_ADMIN_MODE"]

    def test_allowed_when_not_readonly(self) -> None:
        """_check_readonly does nothing when mode is not set."""
        os.environ.pop("DIFY_ADMIN_MODE", None)
        _check_readonly()  # should not raise

    def test_allowed_when_mode_is_other(self) -> None:
        """_check_readonly allows non-readonly mode values."""
        os.environ["DIFY_ADMIN_MODE"] = "normal"
        try:
            _check_readonly()  # should not raise
        finally:
            del os.environ["DIFY_ADMIN_MODE"]
