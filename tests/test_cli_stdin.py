"""`_read_input()` および `apps import` の stdin 対応テスト。

Canon TDD: 実装に先立ち仕様ベースで記述。
参照: requirements.md（REQ-003.1, 003.5, 003.6）,
design.md（PROP-003, PROP-004, PROP-019）

シグネチャ（design.md）::

    def _read_input(file_path: str | None, *, allow_stdin: bool = True) -> str

- タスク 17.1: `_read_input` 単体
- タスク 18.1: `apps import --file -` / ファイルとの等価性（PROP-003）
- タスク 19.1: `plan -` / `apply -`（REQ-003.3, REQ-003.4）
- タスク 20.1: `apps config set` の `--file -`（REQ-003.2）
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
import yaml
from click.testing import CliRunner

from dify_admin.cli import _read_input, main
from dify_admin.state import StateAction, StatePlan


class TestReadInput:
    """REQ-003.5, REQ-003.6, PROP-003, PROP-004, PROP-019。"""

    def test_returns_file_contents_when_path_is_regular_file(
        self, tmp_path: Path
    ) -> None:
        """ファイルパス指定時はそのファイルの内容を返す。"""
        path = tmp_path / "state.yaml"
        path.write_text("desired_state:\n  apps: []\n", encoding="utf-8")
        assert _read_input(str(path)) == "desired_state:\n  apps: []\n"

    def test_reads_from_stdin_when_path_is_hyphen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """\"-\" 指定時は stdin から読み取る。"""
        monkeypatch.setattr(sys, "stdin", io.StringIO("from stdin\n"))
        assert _read_input("-") == "from stdin\n"

    def test_empty_stdin_raises_usage_error_with_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stdin が空のとき click.UsageError かつ所定メッセージ（REQ-003.5）。"""
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        with pytest.raises(click.UsageError) as exc_info:
            _read_input("-")
        assert "No input received from stdin" in str(exc_info.value)

    def test_regular_file_path_takes_priority_over_stdin(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ファイルパス（\"-\" 以外）と stdin データが両方ある場合はファイル優先（REQ-003.6）。"""
        path = tmp_path / "data.yml"
        path.write_text("content: from file\n", encoding="utf-8")
        monkeypatch.setattr(sys, "stdin", io.StringIO("from stdin should be ignored"))
        assert _read_input(str(path)) == "content: from file\n"


_MINIMAL_DSL_YAML = (
    "app:\n"
    "  name: Stdin Import Test\n"
    "  mode: chat\n"
)


def _patch_make_client_with_client(mock_client: MagicMock) -> patch:
    """`_make_client` が with ブロックで mock_client を返すようにする。"""

    @contextmanager
    def _cm(*_a: object, **_kw: object) -> object:
        yield mock_client

    return patch("dify_admin.cli._make_client", new=_cm)


class TestAppsImportStdin:
    """REQ-003.1, PROP-003: `apps import` の `--file -` とファイル入力の等価性。"""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_import_reads_yaml_from_stdin_when_file_is_hyphen(
        self, runner: CliRunner
    ) -> None:
        """`--file -` で stdin から DSL YAML を読み、`apps_import` に渡す。"""
        client = MagicMock()
        client.apps_import.return_value = {
            "id": "imported-id",
            "name": "Stdin Import Test",
        }
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "import",
                    "--file",
                    "-",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
                input=_MINIMAL_DSL_YAML,
            )
        assert result.exit_code == 0, result.output
        client.apps_import.assert_called_once()
        yaml_passed, = client.apps_import.call_args[0]
        assert yaml_passed == _MINIMAL_DSL_YAML

    def test_file_path_and_stdin_round_trip_equivalent(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """ファイル入力と stdin が `apps_import` に同じ YAML 文字列を渡す（PROP-003）。"""
        yml = tmp_path / "bot.yml"
        yml.write_text(_MINIMAL_DSL_YAML, encoding="utf-8")

        client_file = MagicMock()
        client_file.apps_import.return_value = {"id": "1", "name": "x"}
        with _patch_make_client_with_client(client_file):
            r_file = runner.invoke(
                main,
                [
                    "apps",
                    "import",
                    "--file",
                    str(yml),
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
            )
        assert r_file.exit_code == 0, r_file.output

        client_stdin = MagicMock()
        client_stdin.apps_import.return_value = {"id": "1", "name": "x"}
        with _patch_make_client_with_client(client_stdin):
            r_stdin = runner.invoke(
                main,
                [
                    "apps",
                    "import",
                    "--file",
                    "-",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
                input=_MINIMAL_DSL_YAML,
            )
        assert r_stdin.exit_code == 0, r_stdin.output

        yaml_from_file = client_file.apps_import.call_args[0][0]
        yaml_from_stdin = client_stdin.apps_import.call_args[0][0]
        assert yaml_from_file == yaml_from_stdin == _MINIMAL_DSL_YAML


_MINIMAL_STATE_YAML = "apps: []\nknowledge_bases: []\n"


class TestPlanApplyStdin:
    """REQ-003.3, REQ-003.4, PROP-003: `plan` / `apply` の STATE_FILE に `-` を指定。"""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_plan_reads_state_yaml_from_stdin_when_hyphen(
        self, runner: CliRunner
    ) -> None:
        """`plan -` で stdin から state YAML を読み、`compute_plan` に渡す。"""
        client = MagicMock()
        empty_plan = StatePlan(actions=[])
        expected_desired = yaml.safe_load(_MINIMAL_STATE_YAML)
        with _patch_make_client_with_client(client), patch(
            "dify_admin.state.compute_plan", return_value=empty_plan
        ) as mock_compute:
            result = runner.invoke(
                main,
                ["plan", "-", "--email", "a@b.com", "--password", "pwd"],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
                input=_MINIMAL_STATE_YAML,
            )
        assert result.exit_code == 0, result.output
        mock_compute.assert_called_once()
        args, kwargs = mock_compute.call_args
        assert args[0] is client
        assert args[1] == expected_desired
        assert kwargs.get("delete_missing") is False

    def test_apply_reads_state_yaml_from_stdin_and_calls_execute_plan(
        self, runner: CliRunner
    ) -> None:
        """`apply -` で stdin から読み、`compute_plan` / `execute_plan` を呼ぶ。"""
        client = MagicMock()
        expected_desired = yaml.safe_load(_MINIMAL_STATE_YAML)
        action = StateAction(
            resource_type="app",
            action="create",
            name="n",
            details={"name": "n", "mode": "chat"},
        )
        fake_plan = StatePlan(actions=[action])
        exec_results = [
            {"status": "ok", "action": "create", "name": "n", "type": "app"},
        ]
        with _patch_make_client_with_client(client), patch(
            "dify_admin.state.compute_plan", return_value=fake_plan
        ) as mock_compute, patch(
            "dify_admin.state.execute_plan", return_value=exec_results
        ) as mock_exec:
            result = runner.invoke(
                main,
                [
                    "apply",
                    "-",
                    "--yes",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
                input=_MINIMAL_STATE_YAML,
            )
        assert result.exit_code == 0, result.output
        mock_compute.assert_called_once()
        c_args, c_kw = mock_compute.call_args
        assert c_args[0] is client
        assert c_args[1] == expected_desired
        assert c_kw.get("delete_missing") is False
        mock_exec.assert_called_once_with(client, fake_plan)


_MINIMAL_CONFIG_JSON = '{"model": {"name": "gpt-4o"}}\n'


class TestAppsConfigSetStdin:
    """REQ-003.2, PROP-003: `apps config set --file -` で stdin から JSON を読む。"""

    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_config_set_reads_json_from_stdin_when_file_is_hyphen(
        self, runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`--file -` で stdin から JSON を読み、`apps_update_config` に渡す。

        ``monkeypatch`` で ``sys.stdin`` を指す ``StringIO`` に差し替えたうえで、
        ``CliRunner.invoke(..., input=...)`` を渡す（Click は ``input`` から
        ``sys.stdin`` を再設定し、``_read_input("-")`` が JSON を読める）。
        """
        client = MagicMock()
        client.apps_update_config.return_value = {"status": "ok"}
        expected_config = json.loads(_MINIMAL_CONFIG_JSON)
        monkeypatch.setattr(sys, "stdin", io.StringIO(_MINIMAL_CONFIG_JSON))
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                [
                    "apps",
                    "config",
                    "set",
                    "app-id-xyz",
                    "--file",
                    "-",
                    "--email",
                    "a@b.com",
                    "--password",
                    "pwd",
                ],
                catch_exceptions=False,
                env={"DIFY_URL": "http://localhost:5001"},
                input=_MINIMAL_CONFIG_JSON,
            )
        assert result.exit_code == 0, result.output
        client.apps_update_config.assert_called_once_with("app-id-xyz", expected_config)
