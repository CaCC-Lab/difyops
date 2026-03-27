"""CLI コマンドメタデータ JSON 出力のテスト。

Canon TDD: 実装は `.kiro/specs/agent-friendly-cli-improvements/` のみ参照。
参照: requirements.md（REQ-012.1, REQ-012.2, REQ-012.3）,
design.md（PROP-012, PROP-017）

- タスク 28.1: `--json` 単体および `apps --json` でのメタデータ一覧
"""

from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from dify_admin.cli import main

_REQUIRED_KEYS = frozenset(
    {"name", "description", "destructive", "idempotent", "supports_dry_run"}
)
_IDEMPOTENT_VALUES = frozenset({"yes", "no", "conditional"})


def _parse_commands_json(stdout: str) -> list[dict[str, Any]]:
    data = json.loads(stdout.strip())
    assert "commands" in data
    assert isinstance(data["commands"], list)
    return data["commands"]


def _assert_command_entries(entries: list[dict[str, Any]]) -> None:
    assert len(entries) >= 1
    for entry in entries:
        assert _REQUIRED_KEYS.issubset(entry.keys()), entry
        assert set(entry.keys()) == _REQUIRED_KEYS, entry
        assert isinstance(entry["name"], str)
        assert isinstance(entry["description"], str)
        assert isinstance(entry["destructive"], bool)
        assert isinstance(entry["supports_dry_run"], bool)
        assert entry["idempotent"] in _IDEMPOTENT_VALUES


class TestCliMetadataJson:
    """REQ-012.1〜012.3: `--json` によるコマンドメタデータ出力。"""

    def test_root_json_lists_top_level_commands(self) -> None:
        """REQ-012.1: サブコマンドなし ``--json`` でトップレベル一覧 JSON。"""
        runner = CliRunner()
        result = runner.invoke(main, ["--json"], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        commands = _parse_commands_json(result.output)
        _assert_command_entries(commands)
        names = {c["name"] for c in commands}
        assert "login" in names
        assert "status" in names
        assert "mcp serve" in names

    def test_apps_json_lists_apps_group_commands(self) -> None:
        """REQ-012.2: ``apps --json``（サブコマンドなし）で apps グループ一覧 JSON。"""
        runner = CliRunner()
        result = runner.invoke(main, ["apps", "--json"], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        commands = _parse_commands_json(result.output)
        _assert_command_entries(commands)
        names = {c["name"] for c in commands}
        assert "apps list" in names
        assert "apps create" in names
        assert all(n.startswith("apps ") for n in names)
