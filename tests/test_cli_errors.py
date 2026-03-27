"""CLI エラーハンドリングのテスト（click.testing.CliRunner）。

Canon TDD: agent-friendly-cli-improvements の実装に先立ち、仕様ベースで記述。
参照: .kiro/specs/agent-friendly-cli-improvements/requirements.md
（REQ-004.1〜004.6, REQ-005.3〜005.6, REQ-008.1〜008.4, REQ-008.6）,
design.md（PROP-005, PROP-007, PROP-008, PROP-013, PROP-015）

モック対象は `dify_admin.cli._make_client`（`apps list` が `client.apps_list()` を呼ぶ経路）。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner, Result

from dify_admin.cli import main
from dify_admin.exceptions import DifyConnectionError, DifyNotFoundError
from dify_admin.resolve import AmbiguousNameError, NameNotFoundError

# `apps list` は資格情報付きで API を呼ぶ（既存テストと同様のパターン）
_APPS_LIST_ARGS = [
    "--json",
    "apps",
    "list",
    "--email",
    "a@b.com",
    "--password",
    "pwd",
]


def _patch_make_client_with_client(mock_client: MagicMock) -> patch:
    """_make_client が with ブロックで mock_client を返すようにする。"""

    @contextmanager
    def _cm(*_a: object, **_kw: object) -> object:
        yield mock_client

    return patch("dify_admin.cli._make_client", new=_cm)


def _stderr_json(result: Result) -> dict:
    """stderr の JSON 1行をパース（--json 時の構造化エラー想定）。"""
    err = getattr(result, "stderr", "") or ""
    err = err.strip()
    if not err:
        raise AssertionError("expected non-empty stderr")
    return json.loads(err)


def _combined_cli_output(result: Result) -> str:
    """Human モードのエラー本文検証用（Rich は主に stderr）。"""
    return (result.stdout or "") + (result.stderr or "")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCliExitCodesByExceptionType:
    """REQ-005.3〜005.5, PROP-007: 例外型に応じた exit code。"""

    def test_dify_connection_error_exits_three(self, runner: CliRunner) -> None:
        """REQ-005.4: DifyConnectionError → 3。"""
        client = MagicMock()
        client.apps_list.side_effect = DifyConnectionError("http://localhost:5001")

        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                _APPS_LIST_ARGS,
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        assert result.exit_code == 3

    def test_httpx_timeout_exits_four(self, runner: CliRunner) -> None:
        """REQ-005.5: httpx.TimeoutException → 4。"""
        client = MagicMock()
        client.apps_list.side_effect = httpx.ReadTimeout("timed out")

        with _patch_make_client_with_client(client):
            # 未実装時は Timeout が握りつぶされずに伝播するため True（実装後は False でも可）
            result = runner.invoke(
                main,
                _APPS_LIST_ARGS,
                catch_exceptions=True,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        assert result.exit_code == 4

    def test_dify_admin_error_exits_one(self, runner: CliRunner) -> None:
        """REQ-005.2: DifyAdminError（接続・タイムアウト以外）→ 1。"""
        client = MagicMock()
        client.apps_list.side_effect = DifyNotFoundError("App", "missing-id")

        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                _APPS_LIST_ARGS,
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        assert result.exit_code == 1


class TestCliJsonErrorOutput:
    """REQ-004.7, REQ-011, PROP-008: --json 時は stderr に JSON、stdout は空。"""

    def test_json_mode_writes_error_json_to_stderr_empty_stdout(
        self, runner: CliRunner
    ) -> None:
        client = MagicMock()
        client.apps_list.side_effect = DifyNotFoundError("App", "bad-id")

        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                _APPS_LIST_ARGS,
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )

        assert result.stdout == ""
        payload = _stderr_json(result)
        assert "error" in payload
        assert "message" in payload
        assert "exit_code" in payload
        assert payload["exit_code"] == result.exit_code
        assert isinstance(payload["error"], str)
        assert isinstance(payload["message"], str)
        assert isinstance(payload["exit_code"], int)

    def test_json_error_includes_hint_when_present(self, runner: CliRunner) -> None:
        """REQ-004.6: DifyAdminError で hint があればエラー出力に含める。"""
        client = MagicMock()
        client.apps_list.side_effect = DifyNotFoundError("App", "bad-id")

        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                _APPS_LIST_ARGS,
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )

        payload = _stderr_json(result)
        assert "hint" in payload
        assert payload["hint"] is not None
        assert "app" in str(payload["hint"]).lower() or "list" in str(payload["hint"]).lower()


class TestSelfHealingErrorMessages:
    """REQ-004.2〜004.5, PROP-005, PROP-006: 自己修復向けエラーメッセージ。"""

    def test_name_not_found_suggests_apps_list_command(self, runner: CliRunner) -> None:
        """REQ-004.2: NameNotFoundError 時に apps list 実行を提案する。"""
        client = MagicMock()
        with _patch_make_client_with_client(client), patch(
            "dify_admin.cli.resolve_app_by_name",
            side_effect=NameNotFoundError("No app found with name: ghost"),
        ):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "get",
                    "--name",
                    "ghost",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        text = _combined_cli_output(result)
        assert "Run 'dify-admin apps list'" in text or "dify-admin apps list" in text

    def test_ambiguous_name_lists_matching_ids(self, runner: CliRunner) -> None:
        """REQ-004.3: AmbiguousNameError 時にマッチした ID が示される。"""
        client = MagicMock()
        with _patch_make_client_with_client(client), patch(
            "dify_admin.cli.resolve_app_by_name",
            side_effect=AmbiguousNameError(
                "Multiple apps found with name 'dup': abcd1111efgh, abcd2222efgh"
            ),
        ):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "get",
                    "--name",
                    "dup",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        text = _combined_cli_output(result)
        assert "abcd1111efgh" in text
        assert "abcd2222efgh" in text
        assert "--name" in text.lower()

    def test_connection_error_suggests_doctor(self, runner: CliRunner) -> None:
        """REQ-004.4: DifyConnectionError 時に doctor 実行を提案する。"""
        @contextmanager
        def _make_client_raises(*_a: object, **_kw: object) -> object:
            raise DifyConnectionError("http://localhost:5001")

        with patch("dify_admin.cli._make_client", new=_make_client_raises):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "get",
                    "abc123",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        text = _combined_cli_output(result)
        assert "http://localhost:5001" in text or "localhost" in text
        assert "dify-admin doctor" in text or "doctor" in text.lower()

    def test_apps_config_set_invalid_json_shows_position_and_input_snippet(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """REQ-004.5, PROP-006: 不正 JSON で位置情報と入力先頭付近が出る。"""
        bad = '{"model": broken'
        p = tmp_path / "bad.json"
        p.write_text(bad, encoding="utf-8")
        result = runner.invoke(
            main,
            [
                "apps",
                "config",
                "set",
                "--email",
                "a@b.com",
                "--password",
                "pwd",
                "--file",
                str(p),
            ],
            catch_exceptions=False,
            env={"DIFY_URL": "http://localhost:5001"},
        )
        text = _combined_cli_output(result)
        lower = text.lower()
        assert "line" in lower or "column" in lower or "char" in lower
        assert bad[: min(100, len(bad))] in text or bad.strip()[:50] in text


_ENV = {"DIFY_URL": "http://localhost:5001"}
_CRED = ["--email", "a@b.com", "--password", "pwd"]


class TestDryRunPreview:
    """REQ-008.1〜008.4, REQ-008.6, PROP-013, PROP-015: --dry-run プレビューと exit 0。"""

    def test_apps_config_set_dry_run_validates_json_without_api(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """REQ-008.1: JSON 検証・プレビュー表示、API なし、exit 0。"""
        cfg = tmp_path / "cfg.json"
        cfg.write_text('{"model": {"name": "gpt-4o"}}', encoding="utf-8")
        client = MagicMock()
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "config",
                    "set",
                    "app-1",
                    "--file",
                    str(cfg),
                    "--dry-run",
                    *_CRED,
                ],
                catch_exceptions=False,
                env=_ENV,
            )
        assert result.exit_code == 0, result.output
        client.apps_update_config.assert_not_called()
        text = _combined_cli_output(result)
        assert "Dry-run" in text or "dry-run" in text.lower()
        assert "gpt-4o" in text or "model" in text

    def test_apps_import_dry_run_parses_yaml_without_api(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """REQ-008.2: YAML から app.name / app.mode を表示、アプリ作成なし、exit 0。"""
        yml = tmp_path / "bot.yml"
        yml.write_text(
            "app:\n  name: PreviewBot\n  mode: chat\n",
            encoding="utf-8",
        )
        client = MagicMock()
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                ["apps", "import", "--file", str(yml), "--dry-run", *_CRED],
                catch_exceptions=False,
                env=_ENV,
            )
        assert result.exit_code == 0, result.output
        client.apps_import.assert_not_called()
        text = _combined_cli_output(result)
        assert "PreviewBot" in text
        assert "chat" in text

    def test_apps_rename_dry_run_shows_names_without_rename_api(
        self, runner: CliRunner
    ) -> None:
        """REQ-008.3: 現在名と新名を表示、rename API なし、exit 0。"""
        client = MagicMock()
        client.apps_get.return_value = {"id": "aid", "name": "CurrentName"}
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "rename",
                    "app-id-1",
                    "--new-name",
                    "RenamedOnlyInPreview",
                    "--dry-run",
                    *_CRED,
                ],
                catch_exceptions=False,
                env=_ENV,
            )
        assert result.exit_code == 0, result.output
        client.apps_rename.assert_not_called()
        client.apps_get.assert_called_once()
        text = _combined_cli_output(result)
        assert "CurrentName" in text
        assert "RenamedOnlyInPreview" in text

    def test_kb_upload_dry_run_lists_files_without_upload(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """REQ-008.4: マッチファイル一覧、アップロードなし、exit 0。"""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "note.md").write_text("body", encoding="utf-8")
        client = MagicMock()
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                [
                    "kb",
                    "upload",
                    "dataset-dry-1",
                    str(docs),
                    "--pattern",
                    "*.md",
                    "--dry-run",
                    *_CRED,
                ],
                catch_exceptions=False,
                env=_ENV,
            )
        assert result.exit_code == 0, result.output
        client.kb_upload_file.assert_not_called()
        client.kb_upload_dir.assert_not_called()
        text = _combined_cli_output(result)
        assert "note.md" in text
        assert "Dry-run" in text or "dry-run" in text.lower()
