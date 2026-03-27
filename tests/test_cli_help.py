"""apps グループおよび apps config サブグループの `--help` 構造テスト。

Canon TDD: 実装は `.kiro/specs/agent-friendly-cli-improvements/` のみ参照。
参照: requirements.md（REQ-001.1〜001.5, REQ-002.1, REQ-002.2, REQ-002.4）,
design.md（PROP-001, PROP-002）

README 整合性（タスク 31.1）: requirements.md（REQ-009.1〜009.5）

後方互換性（タスク 32.1）: requirements.md（§後方互換性要件）

- タスク 9.1: apps 直下13コマンド
- タスク 10.1: `apps config` の get / set / patch
- タスク 11.1: `kb` の list / create / upload / clear / sync
- タスク 12.1: `kb docs` の list / status / reindex / delete
- タスク 13.1: `audit` の list / clear
- タスク 14.1: トップレベル login / status / doctor / reset-password / plan / apply /
  env-diff / mcp serve

CliRunner で実際の CLI を起動し、仕様どおりのセクション・ラベル・例を検証する。
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from dify_admin.cli import main


def _readme_path() -> Path:
    """リポジトリルートの README.md。"""
    return Path(__file__).resolve().parents[1] / "README.md"


def _section_level2(text: str, title: str) -> str:
    """``## {title}`` から次のレベル2見出しの直前までを返す。見出しが無ければ空文字。"""
    header = f"## {title}"
    start = text.find(header)
    if start == -1:
        return ""
    rest = text[start:]
    sub = rest[len(header) :]
    m = re.search(r"\n## .", sub)
    if m:
        return rest[: len(header) + m.start()]
    return rest


def _patch_make_client_with_client(mock_client: MagicMock) -> patch:
    """`_make_client` が with ブロックで ``mock_client`` を返す（test_cli_errors と同パターン）。"""

    @contextmanager
    def _cm(*_a: object, **_kw: object) -> object:
        yield mock_client

    return patch("dify_admin.cli._make_client", new=_cm)


# タスク 9.1 指定の apps 配下13コマンド（順不同・表記は CLI と一致させる）
_APPS_SUBCOMMANDS = (
    "list",
    "create",
    "rename",
    "search",
    "delete",
    "get",
    "export",
    "import",
    "scaffold",
    "templates",
    "clone",
    "diff",
    "dsl-diff",
)

IdempotentLabel = Literal["yes", "no", "conditional"]


def _expected_idempotent_label(cmd: str) -> IdempotentLabel:
    """REQ-007.1 の Idempotent_Command 分類とタスク 9.1 の分類に整合。"""
    mapping: dict[str, IdempotentLabel] = {
        "list": "yes",
        "create": "no",
        "rename": "conditional",
        "search": "yes",
        "delete": "conditional",
        "get": "yes",
        "export": "yes",
        "import": "no",
        "scaffold": "no",
        "templates": "yes",
        "clone": "no",
        "diff": "yes",
        "dsl-diff": "yes",
    }
    return mapping[cmd]


def _invoke_apps_help(runner: CliRunner, subcommand: str) -> str:
    """stdout + stderr を結合（click は通常 stdout のみ）。"""
    result = runner.invoke(
        main,
        ["apps", subcommand, "--help"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _body_before_options(help_text: str) -> str:
    """Usage 行と Options: ブロックの手前の本文（docstring 相当）。"""
    if "Options:" not in help_text:
        return help_text
    return help_text.split("Options:", 1)[0]


def _non_empty_lines(block: str) -> list[str]:
    return [ln for ln in block.splitlines() if ln.strip()]


def _summary_and_detail_line_count(help_text: str) -> int:
    """REQ-001.1 / REQ-002.1: 1行サマリ + 詳細は Options より前の非空行で数える。"""
    head = _body_before_options(help_text)
    lines = head.splitlines()
    # 先頭の Usage: 行を除く
    if lines and lines[0].strip().startswith("Usage:"):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return len(_non_empty_lines(body))


def _examples_tail(help_text: str) -> str:
    """Examples: 以降（JSON Output Keys / Side Effects より前を優先して切る）。"""
    lower = help_text.lower()
    idx = lower.find("examples:")
    if idx == -1:
        return ""
    tail = help_text[idx:]
    for stop in ("JSON Output Keys:", "Side Effects:", "Idempotent:"):
        if stop in tail:
            tail = tail.split(stop, 1)[0]
    return tail


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestAppsGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: サマリ・詳細・Examples。"""

    @pytest.mark.parametrize("subcommand", _APPS_SUBCOMMANDS)
    def test_each_has_summary_detail_and_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_help(runner, subcommand)
        assert "Examples:" in text, f"{subcommand}: missing Examples section"
        # REQ-002.4: 具体例は $ dify-admin 形式
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, f"{subcommand}: missing $ dify-admin example"
        # REQ-002.1: 詳細説明は少なくとも3行（Options より前の本文でカウント）
        assert _summary_and_detail_line_count(text) >= 3, (
            f"{subcommand}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )


class TestAppsHelpSideEffects:
    """REQ-001.2, PROP-002: destructive コマンドの Side Effects。"""

    @pytest.mark.parametrize(
        "subcommand",
        ("create", "rename", "delete", "import", "scaffold", "clone"),
    )
    def test_destructive_has_side_effects_section(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_help(runner, subcommand)
        assert "Side Effects:" in text, f"{subcommand}: missing Side Effects (REQ-001.2)"


class TestAppsHelpNameDualExamples:
    """REQ-001.3, REQ-002.3: --name 対応コマンドは APP_ID 形式と --name 形式の例。"""

    @pytest.mark.parametrize(
        "subcommand",
        ("rename", "delete", "get", "export", "clone"),
    )
    def test_name_resolution_shows_app_id_and_name_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--name" in ex_block, f"{subcommand}: missing --name in Examples"
        assert re.search(r"\bAPP_ID\b", ex_block), (
            f"{subcommand}: missing APP_ID placeholder in Examples (REQ-001.3)"
        )


class TestAppsHelpDryRunExamples:
    """REQ-001.5: --dry-run 対応コマンドは Examples に dry-run 例。"""

    @pytest.mark.parametrize("subcommand", ("delete", "import", "rename"))
    def test_dry_run_appears_in_examples(self, runner: CliRunner, subcommand: str) -> None:
        text = _invoke_apps_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--dry-run" in ex_block, (
            f"{subcommand}: missing --dry-run under Examples (REQ-001.5)"
        )


class TestAppsHelpIdempotentLabel:
    """REQ-001.4, REQ-007 整合: Idempotent ラベル（yes / no / conditional）。"""

    @pytest.mark.parametrize("subcommand", _APPS_SUBCOMMANDS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_help(runner, subcommand)
        expect = _expected_idempotent_label(subcommand)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"{subcommand}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


# ── タスク 10.1: apps config サブグループ（get / set / patch）────────────────

_APPS_CONFIG_SUBCOMMANDS = ("get", "set", "patch")


def _invoke_apps_config_help(runner: CliRunner, subcommand: str) -> str:
    """apps config <subcommand> --help の結合出力。"""
    result = runner.invoke(
        main,
        ["apps", "config", subcommand, "--help"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _expected_idempotent_label_apps_config(cmd: str) -> IdempotentLabel:
    """タスク 10.1 指定: get=yes, set=conditional, patch=conditional（REQ-007.3 整合）。"""
    mapping: dict[str, IdempotentLabel] = {
        "get": "yes",
        "set": "conditional",
        "patch": "conditional",
    }
    return mapping[cmd]


class TestAppsConfigGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.2, REQ-002.4, PROP-001: apps config の構造化ヘルプ。"""

    @pytest.mark.parametrize("subcommand", _APPS_CONFIG_SUBCOMMANDS)
    def test_each_has_summary_detail_examples_and_json_keys(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_config_help(runner, subcommand)
        assert "Examples:" in text, f"config {subcommand}: missing Examples section"
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, (
            f"config {subcommand}: missing $ dify-admin example (REQ-002.4)"
        )
        assert _summary_and_detail_line_count(text) >= 3, (
            f"config {subcommand}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )
        assert "JSON Output Keys:" in text, (
            f"config {subcommand}: missing JSON Output Keys (REQ-002.2)"
        )


class TestAppsConfigHelpSideEffects:
    """REQ-001.2, PROP-002: destructive（set, patch）に Side Effects。"""

    @pytest.mark.parametrize("subcommand", ("set", "patch"))
    def test_mutating_commands_have_side_effects_section(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_config_help(runner, subcommand)
        assert "Side Effects:" in text, (
            f"config {subcommand}: missing Side Effects (REQ-001.2)"
        )


class TestAppsConfigHelpDryRunExamples:
    """REQ-001.5: --dry-run 対応（set, patch）の Examples に dry-run 例。"""

    @pytest.mark.parametrize("subcommand", ("set", "patch"))
    def test_dry_run_appears_in_examples(self, runner: CliRunner, subcommand: str) -> None:
        text = _invoke_apps_config_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--dry-run" in ex_block, (
            f"config {subcommand}: missing --dry-run under Examples (REQ-001.5)"
        )


class TestAppsConfigHelpIdempotentLabel:
    """REQ-001.4: Idempotent ラベル（get=yes, set=conditional, patch=conditional）。"""

    @pytest.mark.parametrize("subcommand", _APPS_CONFIG_SUBCOMMANDS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_config_help(runner, subcommand)
        expect = _expected_idempotent_label_apps_config(subcommand)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"config {subcommand}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


class TestAppsConfigHelpNameDualExamples:
    """REQ-001.3: 全3コマンドで APP_ID 形式と --name 形式の例。"""

    @pytest.mark.parametrize("subcommand", _APPS_CONFIG_SUBCOMMANDS)
    def test_name_resolution_shows_app_id_and_name_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_apps_config_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--name" in ex_block, f"config {subcommand}: missing --name in Examples"
        assert re.search(r"\bAPP_ID\b", ex_block), (
            f"config {subcommand}: missing APP_ID placeholder in Examples (REQ-001.3)"
        )


# ── タスク 11.1: kb グループ（list / create / upload / clear / sync）──────────

_KB_SUBCOMMANDS = ("list", "create", "upload", "clear", "sync")


def _invoke_kb_help(runner: CliRunner, subcommand: str) -> str:
    """kb <subcommand> --help の結合出力。"""
    result = runner.invoke(
        main,
        ["kb", subcommand, "--help"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _expected_idempotent_label_kb(cmd: str) -> IdempotentLabel:
    """タスク 11.1 指定の Idempotent ラベル。"""
    mapping: dict[str, IdempotentLabel] = {
        "list": "yes",
        "create": "no",
        "upload": "no",
        "clear": "no",
        "sync": "conditional",
    }
    return mapping[cmd]


class TestKbGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: kb グループの構造化ヘルプ。"""

    @pytest.mark.parametrize("subcommand", _KB_SUBCOMMANDS)
    def test_each_has_summary_detail_and_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_help(runner, subcommand)
        assert "Examples:" in text, f"kb {subcommand}: missing Examples section"
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, (
            f"kb {subcommand}: missing $ dify-admin example (REQ-002.4)"
        )
        assert _summary_and_detail_line_count(text) >= 3, (
            f"kb {subcommand}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )


class TestKbHelpSideEffects:
    """REQ-001.2, PROP-002: destructive（create, upload, clear, sync）に Side Effects。"""

    @pytest.mark.parametrize(
        "subcommand",
        ("create", "upload", "clear", "sync"),
    )
    def test_destructive_has_side_effects_section(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_help(runner, subcommand)
        assert "Side Effects:" in text, f"kb {subcommand}: missing Side Effects (REQ-001.2)"


class TestKbHelpDryRunExamples:
    """REQ-001.5: --dry-run 対応（upload, clear, sync）の Examples に dry-run 例。"""

    @pytest.mark.parametrize("subcommand", ("upload", "clear", "sync"))
    def test_dry_run_appears_in_examples(self, runner: CliRunner, subcommand: str) -> None:
        text = _invoke_kb_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--dry-run" in ex_block, (
            f"kb {subcommand}: missing --dry-run under Examples (REQ-001.5)"
        )


class TestKbHelpNameDualExamples:
    """REQ-001.3: upload / clear / sync で DATASET_ID 形式と --name 形式の例。"""

    @pytest.mark.parametrize("subcommand", ("upload", "clear", "sync"))
    def test_name_resolution_shows_dataset_id_and_name_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--name" in ex_block, f"kb {subcommand}: missing --name in Examples"
        assert re.search(r"\bDATASET_ID\b", ex_block), (
            f"kb {subcommand}: missing DATASET_ID placeholder in Examples (REQ-001.3)"
        )


class TestKbHelpIdempotentLabel:
    """REQ-001.4: Idempotent ラベル（タスク 11.1 の yes/no/conditional マップ）。"""

    @pytest.mark.parametrize("subcommand", _KB_SUBCOMMANDS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_help(runner, subcommand)
        expect = _expected_idempotent_label_kb(subcommand)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"kb {subcommand}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


# ── タスク 12.1: kb docs グループ（list / status / reindex / delete）────────

_KB_DOCS_SUBCOMMANDS = ("list", "status", "reindex", "delete")


def _invoke_kb_docs_help(runner: CliRunner, subcommand: str) -> str:
    """kb docs <subcommand> --help の結合出力。"""
    result = runner.invoke(
        main,
        ["kb", "docs", subcommand, "--help"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _expected_idempotent_label_kb_docs(cmd: str) -> IdempotentLabel:
    """タスク 12.1 指定の Idempotent ラベル。"""
    mapping: dict[str, IdempotentLabel] = {
        "list": "yes",
        "status": "yes",
        "reindex": "conditional",
        "delete": "no",
    }
    return mapping[cmd]


class TestKbDocsGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: kb docs グループの構造化ヘルプ。"""

    @pytest.mark.parametrize("subcommand", _KB_DOCS_SUBCOMMANDS)
    def test_each_has_summary_detail_and_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_docs_help(runner, subcommand)
        assert "Examples:" in text, f"kb docs {subcommand}: missing Examples section"
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, (
            f"kb docs {subcommand}: missing $ dify-admin example (REQ-002.4)"
        )
        assert _summary_and_detail_line_count(text) >= 3, (
            f"kb docs {subcommand}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )


class TestKbDocsHelpSideEffects:
    """REQ-001.2, PROP-002: destructive（reindex, delete）に Side Effects。"""

    @pytest.mark.parametrize("subcommand", ("reindex", "delete"))
    def test_destructive_has_side_effects_section(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_docs_help(runner, subcommand)
        assert "Side Effects:" in text, (
            f"kb docs {subcommand}: missing Side Effects (REQ-001.2)"
        )


class TestKbDocsHelpDryRunExamples:
    """REQ-001.5: delete の Examples に dry-run 例。"""

    def test_delete_has_dry_run_in_examples(self, runner: CliRunner) -> None:
        text = _invoke_kb_docs_help(runner, "delete")
        ex_block = _examples_tail(text)
        assert "--dry-run" in ex_block, (
            "kb docs delete: missing --dry-run under Examples (REQ-001.5)"
        )


class TestKbDocsHelpNameDualExamples:
    """REQ-001.3: 全4コマンドで DATASET_ID 形式と --name 形式の例。"""

    @pytest.mark.parametrize("subcommand", _KB_DOCS_SUBCOMMANDS)
    def test_name_resolution_shows_dataset_id_and_name_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_docs_help(runner, subcommand)
        ex_block = _examples_tail(text)
        assert "--name" in ex_block, f"kb docs {subcommand}: missing --name in Examples"
        assert re.search(r"\bDATASET_ID\b", ex_block), (
            f"kb docs {subcommand}: missing DATASET_ID placeholder in Examples (REQ-001.3)"
        )


class TestKbDocsHelpPositionalDocId:
    """REQ-002.3: positional DOC_ID の意味と取得方法の言及。"""

    @pytest.mark.parametrize("subcommand", _KB_DOCS_SUBCOMMANDS)
    def test_doc_id_positional_documented(self, runner: CliRunner, subcommand: str) -> None:
        text = _invoke_kb_docs_help(runner, subcommand)
        assert re.search(r"\bDOC_ID\b", text), (
            f"kb docs {subcommand}: missing DOC_ID (REQ-002.3)"
        )
        assert re.search(r"(?i)docs\s+list", text), (
            f"kb docs {subcommand}: missing pointer to docs list for resolving IDs (REQ-002.3)"
        )


class TestKbDocsHelpIdempotentLabel:
    """REQ-001.4: Idempotent ラベル（タスク 12.1 のマップ）。"""

    @pytest.mark.parametrize("subcommand", _KB_DOCS_SUBCOMMANDS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_kb_docs_help(runner, subcommand)
        expect = _expected_idempotent_label_kb_docs(subcommand)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"kb docs {subcommand}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


# ── タスク 13.1: audit グループ（list / clear）──────────────────────────────

_AUDIT_SUBCOMMANDS = ("list", "clear")


def _invoke_audit_help(runner: CliRunner, subcommand: str) -> str:
    """audit <subcommand> --help の結合出力。"""
    result = runner.invoke(
        main,
        ["audit", subcommand, "--help"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _expected_idempotent_label_audit(cmd: str) -> IdempotentLabel:
    """タスク 13.1 指定: list=yes, clear=no。"""
    mapping: dict[str, IdempotentLabel] = {
        "list": "yes",
        "clear": "no",
    }
    return mapping[cmd]


class TestAuditGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: audit グループの構造化ヘルプ。"""

    @pytest.mark.parametrize("subcommand", _AUDIT_SUBCOMMANDS)
    def test_each_has_summary_detail_and_examples(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_audit_help(runner, subcommand)
        assert "Examples:" in text, f"audit {subcommand}: missing Examples section"
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, (
            f"audit {subcommand}: missing $ dify-admin example (REQ-002.4)"
        )
        assert _summary_and_detail_line_count(text) >= 3, (
            f"audit {subcommand}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )


class TestAuditHelpSideEffects:
    """REQ-001.2, PROP-002: audit clear に Side Effects。"""

    def test_clear_has_side_effects_section(self, runner: CliRunner) -> None:
        text = _invoke_audit_help(runner, "clear")
        assert "Side Effects:" in text, "audit clear: missing Side Effects (REQ-001.2)"


class TestAuditHelpIdempotentLabel:
    """REQ-001.4: Idempotent ラベル（list=yes, clear=no）。"""

    @pytest.mark.parametrize("subcommand", _AUDIT_SUBCOMMANDS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, subcommand: str
    ) -> None:
        text = _invoke_audit_help(runner, subcommand)
        expect = _expected_idempotent_label_audit(subcommand)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"audit {subcommand}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


# ── タスク 14.1: トップレベルコマンド（login … mcp serve）────────────────────

_TOP_LEVEL_HELP_INVOCATIONS: tuple[tuple[str, list[str]], ...] = (
    ("login", ["login", "--help"]),
    ("status", ["status", "--help"]),
    ("doctor", ["doctor", "--help"]),
    ("reset-password", ["reset-password", "--help"]),
    ("plan", ["plan", "--help"]),
    ("apply", ["apply", "--help"]),
    ("env-diff", ["env-diff", "--help"]),
    ("mcp serve", ["mcp", "serve", "--help"]),
)


def _invoke_top_level_help(runner: CliRunner, argv: list[str]) -> str:
    """トップレベルまたは `mcp serve` の --help 結合出力。"""
    result = runner.invoke(
        main,
        argv,
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    return (result.output or "") + (getattr(result, "stderr", None) or "")


def _expected_idempotent_label_top_level(label: str) -> IdempotentLabel:
    """タスク 14.1 指定の Idempotent ラベル。"""
    mapping: dict[str, IdempotentLabel] = {
        "login": "yes",
        "status": "yes",
        "doctor": "yes",
        "reset-password": "conditional",
        "plan": "yes",
        "apply": "conditional",
        "env-diff": "yes",
        "mcp serve": "yes",
    }
    return mapping[label]


class TestTopLevelGroupHelpStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: トップレベル構造化ヘルプ。"""

    @pytest.mark.parametrize("label,argv", _TOP_LEVEL_HELP_INVOCATIONS)
    def test_each_has_summary_detail_and_examples(
        self, runner: CliRunner, label: str, argv: list[str]
    ) -> None:
        text = _invoke_top_level_help(runner, argv)
        assert "Examples:" in text, f"{label}: missing Examples section"
        ex_block = _examples_tail(text)
        assert "$ dify-admin" in ex_block, (
            f"{label}: missing $ dify-admin example (REQ-002.4)"
        )
        assert _summary_and_detail_line_count(text) >= 3, (
            f"{label}: expected at least 3 non-empty description lines "
            "before Options (REQ-002.1)"
        )


class TestTopLevelHelpSideEffects:
    """REQ-001.2, PROP-002: destructive（reset-password, apply）に Side Effects。"""

    @pytest.mark.parametrize(
        "label,argv",
        (
            ("reset-password", ["reset-password", "--help"]),
            ("apply", ["apply", "--help"]),
        ),
    )
    def test_destructive_has_side_effects_section(
        self, runner: CliRunner, label: str, argv: list[str]
    ) -> None:
        text = _invoke_top_level_help(runner, argv)
        assert "Side Effects:" in text, f"{label}: missing Side Effects (REQ-001.2)"


class TestTopLevelHelpPositionalArgs:
    """REQ-002.3: positional を取るコマンドは入力の種類と取得方法が説明されること。"""

    @pytest.mark.parametrize(
        "label,argv",
        (
            ("plan", ["plan", "--help"]),
            ("apply", ["apply", "--help"]),
            ("env-diff", ["env-diff", "--help"]),
        ),
    )
    def test_file_or_path_inputs_documented(
        self, runner: CliRunner, label: str, argv: list[str]
    ) -> None:
        text = _invoke_top_level_help(runner, argv)
        assert re.search(
            r"(?i)(file|path|yaml|state|stdin|environment|env|diff)",
            text,
        ), f"{label}: help should describe positional inputs (REQ-002.3)"


class TestTopLevelHelpIdempotentLabel:
    """REQ-001.4: Idempotent ラベル（タスク 14.1 のマップ）。"""

    @pytest.mark.parametrize("label,argv", _TOP_LEVEL_HELP_INVOCATIONS)
    def test_idempotent_label_matches_expectation(
        self, runner: CliRunner, label: str, argv: list[str]
    ) -> None:
        text = _invoke_top_level_help(runner, argv)
        expect = _expected_idempotent_label_top_level(label)
        assert re.search(
            rf"Idempotent:\s*{re.escape(expect)}\b",
            text,
            flags=re.IGNORECASE,
        ), f"{label}: expected 'Idempotent: {expect}' in help (REQ-001.4)"


class TestReadmeAgentFriendly:
    """REQ-009: README.md と CLI の整合性（タスク 31.1: Agent-Friendly 節・終了コード・stdin）。"""

    @pytest.fixture(scope="module")
    def readme_text(self) -> str:
        return _readme_path().read_text(encoding="utf-8")

    def test_readme_has_agent_friendly_section(self, readme_text: str) -> None:
        """REQ-009.5: 「Agent-Friendly CLI」セクションが存在すること。"""
        assert "## Agent-Friendly CLI" in readme_text

    def test_readme_has_exit_code_table_0_to_4(self, readme_text: str) -> None:
        """REQ-009.2: 終了コード 0〜4 のテーブルが README に含まれること。"""
        section = _section_level2(readme_text, "Agent-Friendly CLI")
        assert section, "README に ## Agent-Friendly CLI セクションが必要です (REQ-009.5)"
        for code in (0, 1, 2, 3, 4):
            assert f"| {code} |" in section, (
                f"Exit code テーブルに | {code} | 行が必要です (REQ-009.2)"
            )

    def test_readme_documents_stdin_file_dash(self, readme_text: str) -> None:
        """REQ-009.4: stdin 用の `--file -` / `-` が README に記載されていること。"""
        section = _section_level2(readme_text, "Agent-Friendly CLI")
        assert section
        assert "--file -" in section
        assert "または `-`" in section


class TestBackwardCompatibility:
    """requirements.md §後方互換性要件（タスク 32.1）。

    - ``--json`` の stdout JSON 維持、主要コマンド名の維持、成功時 exit code 0、
      ``--dry-run`` / ``--yes`` の継続利用（``--help`` で確認）。
    """

    _ENV = {"DIFY_URL": "http://localhost:5001"}
    _CREDS = ("--email", "a@b.com", "--password", "pwd")

    def _invoke_apps_list_json(self, runner: CliRunner, prefix_json: list[str]) -> None:
        """prefix_json: ``['--json', 'apps', 'list', ...]`` または ``['apps', '--json', 'list', ...]``。"""
        client = MagicMock()
        client.apps_list.return_value = [
            {"id": "app-1", "name": "Bot", "mode": "chat", "created_at": ""},
        ]
        argv = [*prefix_json, *self._CREDS]
        with _patch_make_client_with_client(client):
            result = runner.invoke(
                main,
                argv,
                catch_exceptions=False,
                env=self._ENV,
            )
        assert result.exit_code == 0, result.output
        parsed = json.loads((result.stdout or "").strip())
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0].get("name") == "Bot"

    def test_json_apps_list_outputs_json_to_stdout_global_flag(self, runner: CliRunner) -> None:
        """後方互換性: トップレベル ``--json apps list`` で stdout に JSON（リスト）。"""
        self._invoke_apps_list_json(
            runner,
            ["--json", "apps", "list"],
        )

    def test_json_apps_list_outputs_json_to_stdout_group_flag(self, runner: CliRunner) -> None:
        """後方互換性: ``apps --json list`` でも JSON 一覧が stdout に出る。"""
        self._invoke_apps_list_json(
            runner,
            ["apps", "--json", "list"],
        )

    @pytest.mark.parametrize(
        "argv",
        (
            ["apps", "list", "--help"],
            ["apps", "create", "--help"],
            ["kb", "list", "--help"],
            ["status", "--help"],
            ["doctor", "--help"],
        ),
    )
    def test_major_commands_still_registered(self, runner: CliRunner, argv: list[str]) -> None:
        """後方互換性: 主要サブコマンド名が変わらず ``--help`` が exit 0。"""
        result = runner.invoke(main, argv, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert "Usage:" in (result.output or "")

    @pytest.mark.parametrize(
        "argv",
        (
            ["apps", "delete", "--help"],
            ["kb", "sync", "--help"],
        ),
    )
    def test_dry_run_and_yes_options_still_in_help(
        self, runner: CliRunner, argv: list[str]
    ) -> None:
        """後方互換性: ``--dry-run`` / ``--yes`` が破壊的操作系の help に残る。"""
        result = runner.invoke(main, argv, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        text = (result.output or "") + (getattr(result, "stderr", None) or "")
        assert "--dry-run" in text
        assert "--yes" in text
