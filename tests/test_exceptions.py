"""Tests for exceptions.py — error hierarchy and raise_for_dify_status."""

from __future__ import annotations

import httpx
import pytest

from dify_admin.exceptions import (
    DifyApiError,
    DifyMethodNotAllowedError,
    DifyNotFoundError,
    DifyPermissionError,
    DifyServerError,
    DifyValidationError,
    raise_for_dify_status,
)


def _make_response(
    status_code: int,
    path: str = "/console/api/test",
    method: str = "GET",
    json_body: dict | None = None,
    text: str = "",
) -> httpx.Response:
    """Create a mock httpx.Response."""
    request = httpx.Request(method, f"http://localhost:5001{path}")
    if json_body is not None:
        import json

        return httpx.Response(
            status_code=status_code,
            request=request,
            content=json.dumps(json_body).encode(),
            headers={"content-type": "application/json"},
        )
    return httpx.Response(
        status_code=status_code,
        request=request,
        text=text,
    )


class TestRaiseForDifyStatus:
    def test_success_does_nothing(self) -> None:
        resp = _make_response(200)
        raise_for_dify_status(resp)  # should not raise

    def test_400_raises_validation_error(self) -> None:
        resp = _make_response(400, json_body={"message": "Invalid param"})
        with pytest.raises(DifyValidationError, match="Invalid param"):
            raise_for_dify_status(resp)

    def test_403_raises_permission_error(self) -> None:
        resp = _make_response(403, json_body={"message": "Forbidden"})
        with pytest.raises(DifyPermissionError, match="Forbidden"):
            raise_for_dify_status(resp)

    def test_404_raises_not_found_error(self) -> None:
        resp = _make_response(404, path="/console/api/apps/abc123")
        with pytest.raises(DifyNotFoundError, match="App not found"):
            raise_for_dify_status(resp)

    def test_404_dataset_resource(self) -> None:
        resp = _make_response(404, path="/console/api/datasets/ds1")
        with pytest.raises(DifyNotFoundError, match="Knowledge base not found"):
            raise_for_dify_status(resp)

    def test_404_document_resource(self) -> None:
        resp = _make_response(404, path="/console/api/datasets/ds1/documents/doc1")
        # Path contains both datasets and documents; datasets is matched first
        with pytest.raises(DifyNotFoundError, match="not found"):
            raise_for_dify_status(resp)

    def test_405_raises_method_not_allowed(self) -> None:
        resp = _make_response(405, path="/console/api/apps/abc/model-config")
        with pytest.raises(DifyMethodNotAllowedError) as exc_info:
            raise_for_dify_status(resp)
        assert "model-config" in str(exc_info.value)
        assert exc_info.value.hint is not None
        assert "advanced-chat" in exc_info.value.hint

    def test_500_raises_server_error(self) -> None:
        resp = _make_response(500, json_body={"message": "Internal error"})
        with pytest.raises(DifyServerError, match="Internal error"):
            raise_for_dify_status(resp)

    def test_502_raises_server_error(self) -> None:
        resp = _make_response(502, text="Bad Gateway")
        with pytest.raises(DifyServerError):
            raise_for_dify_status(resp)

    def test_unknown_status_raises_api_error(self) -> None:
        resp = _make_response(418, text="I'm a teapot")
        with pytest.raises(DifyApiError) as exc_info:
            raise_for_dify_status(resp)
        assert exc_info.value.status_code == 418


class TestExceptionAttributes:
    def test_hint_in_message(self) -> None:
        err = DifyNotFoundError("App", "abc123")
        assert "hint" in str(err)
        assert "abc123" in str(err)

    def test_api_error_attributes(self) -> None:
        err = DifyApiError("test", status_code=400, method="POST", path="/test")
        assert err.status_code == 400
        assert err.method == "POST"
        assert err.path == "/test"


class TestExitCodeConstantsAndMapping:
    """REQ-005.1–005.5, PROP-007: exit code 定数と exit_code_for_exception.

    実装は dify_admin.exceptions に追加予定（Canon TDD）。新シンボルはメソッド内で import し、
    既存テストのモジュール読み込みを壊さない。
    """

    def test_exit_code_constants_match_requirements(self) -> None:
        """REQ-005.1–005.5: 定数が仕様どおりの整数値であること。"""
        from dify_admin.exceptions import (
            EXIT_APP_ERROR,
            EXIT_CONNECTION_ERROR,
            EXIT_SUCCESS,
            EXIT_TIMEOUT_ERROR,
            EXIT_USAGE_ERROR,
        )

        assert EXIT_SUCCESS == 0
        assert EXIT_APP_ERROR == 1
        assert EXIT_USAGE_ERROR == 2
        assert EXIT_CONNECTION_ERROR == 3
        assert EXIT_TIMEOUT_ERROR == 4

    def test_exit_code_for_dify_connection_error(self) -> None:
        """REQ-005.4, PROP-007: DifyConnectionError → 3."""
        from dify_admin.exceptions import DifyConnectionError, exit_code_for_exception

        exc = DifyConnectionError("http://localhost:5001")
        assert exit_code_for_exception(exc) == 3

    def test_exit_code_for_httpx_timeout(self) -> None:
        """REQ-005.5, PROP-007: httpx.TimeoutException → 4."""
        from dify_admin.exceptions import exit_code_for_exception

        # ReadTimeout は TimeoutException のサブクラス（実装は isinstance 判定想定）
        exc = httpx.ReadTimeout("timed out")
        assert exit_code_for_exception(exc) == 4

    def test_exit_code_for_dify_admin_error_subclass(self) -> None:
        """REQ-005.2, PROP-007: DifyAdminError（接続以外）→ 1。"""
        from dify_admin.exceptions import DifyNotFoundError, exit_code_for_exception

        exc = DifyNotFoundError("App", "x")
        assert exit_code_for_exception(exc) == 1

    def test_exit_code_for_generic_exception(self) -> None:
        """REQ-005.2: その他 Exception → 1（アプリケーションエラー扱い）。"""
        from dify_admin.exceptions import exit_code_for_exception

        assert exit_code_for_exception(ValueError("oops")) == 1
        assert exit_code_for_exception(RuntimeError("fail")) == 1
