"""Tests for dify_admin.output.output_json_error.

Canon TDD: tests precede implementation. Spec-only:
- .kiro/specs/agent-friendly-cli-improvements/requirements.md
  (REQ-004.7, REQ-005.6, REQ-011.1–011.5)
- .kiro/specs/agent-friendly-cli-improvements/design.md (output_json_error, PROP-008)

dify_admin/ 実装は参照しない。
"""

from __future__ import annotations

import json

import pytest


def _parse_stderr_json(capsys: pytest.CaptureFixture[str]) -> dict:
    """stderr の1行 JSON をパースする（output_json_error の想定出力）。"""
    err = capsys.readouterr().err.strip()
    return json.loads(err)


class TestOutputJsonError:
    """REQ-011, PROP-008: --json 時の構造化エラーは stderr のみ、フィールド検証。"""

    def test_stderr_json_stdout_empty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REQ-011.4, REQ-011.5: エラー JSON は stderr、stdout は空。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "DifyNotFoundError",
            "App not found: abc123",
            hint="Run 'dify-admin apps list' to see available apps",
            exit_code=1,
        )
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() != ""
        obj = json.loads(captured.err.strip())
        assert isinstance(obj, dict)

    def test_required_fields_types(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REQ-011.1: error, message, hint, exit_code の存在と型。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "DifyValidationError",
            "Invalid request",
            hint="Fix the payload",
            exit_code=1,
        )
        obj = _parse_stderr_json(capsys)
        assert obj["error"] == "DifyValidationError"
        assert isinstance(obj["error"], str)
        assert obj["message"] == "Invalid request"
        assert isinstance(obj["message"], str)
        assert obj["hint"] == "Fix the payload"
        assert isinstance(obj["hint"], str)
        assert obj["exit_code"] == 1
        assert isinstance(obj["exit_code"], int)

    def test_status_code_field_when_provided(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REQ-011.1: DifyApiError 相当で status_code を付与できること。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "DifyNotFoundError",
            "not found",
            hint="list apps",
            status_code=404,
            exit_code=1,
        )
        obj = _parse_stderr_json(capsys)
        assert obj["status_code"] == 404
        assert isinstance(obj["status_code"], int)

    def test_connection_error_exit_code_three(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REQ-011.2: DifyConnectionError 時は exit_code=3（ヘルパーへ exit_code=3 を渡す契約）。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "DifyConnectionError",
            "Cannot connect to Dify at http://localhost:5001",
            hint="Check that Dify is running and the URL is correct",
            exit_code=3,
        )
        obj = _parse_stderr_json(capsys)
        assert obj["error"] == "DifyConnectionError"
        assert obj["exit_code"] == 3

    def test_usage_error_exit_code_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        """REQ-011.3: UsageError 時は exit_code=2。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "UsageError",
            "Missing argument 'APP_ID'.",
            exit_code=2,
        )
        obj = _parse_stderr_json(capsys)
        assert obj["error"] == "UsageError"
        assert obj["exit_code"] == 2
        assert obj["message"] == "Missing argument 'APP_ID'."

    def test_hint_null_when_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """hint が None のとき JSON null（キーは維持）。"""
        from dify_admin.output import output_json_error

        output_json_error(
            "DifyServerError",
            "Server error",
            hint=None,
            exit_code=1,
        )
        obj = _parse_stderr_json(capsys)
        assert "hint" in obj
        assert obj["hint"] is None
