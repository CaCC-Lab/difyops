"""Tests for dify_admin.help.build_help_text.

Canon TDD: tests precede implementation. Spec-only basis:
- .kiro/specs/agent-friendly-cli-improvements/requirements.md (REQ-001.1, 001.2,
  001.4, 001.5, REQ-002.2)
- .kiro/specs/agent-friendly-cli-improvements/design.md (help.py, PROP-001, PROP-002)

dify_admin/ 実装は参照しない。
"""

from __future__ import annotations

import pytest

# design.md のシグネチャに合わせる（実装は dify_admin/help.py 予定）
# def build_help_text(
#     summary: str,
#     description: str,
#     examples: list[str],
#     *,
#     side_effects: str | None = None,
#     idempotent: str = "yes",
#     json_output_keys: list[str] | None = None,
#     supports_dry_run: bool = False,
# ) -> str


def _three_line_description() -> str:
    """REQ-002.1: 詳細説明は少なくとも3行。"""
    return (
        "What the command does: lists resources.\n"
        "Input: optional flags and JSON mode.\n"
        "Output: table to stderr or JSON array to stdout when --json is set."
    )


@pytest.fixture
def build_help_text():
    from dify_admin.help import build_help_text as _fn

    return _fn


class TestBuildHelpTextStructure:
    """REQ-001.1, REQ-002.1, REQ-002.4, PROP-001: 1行サマリ、詳細説明、Examples。"""

    def test_includes_one_line_summary_first(self, build_help_text) -> None:
        text = build_help_text(
            "List all Dify applications.",
            _three_line_description(),
            examples=["$ dify-admin apps list\n  → prints a table of apps"],
        )
        first_line = text.strip().splitlines()[0]
        assert first_line == "List all Dify applications."

    def test_includes_detailed_description_with_at_least_three_lines(
        self, build_help_text
    ) -> None:
        desc = _three_line_description()
        text = build_help_text(
            "Summary line.",
            desc,
            examples=["$ dify-admin apps list\n  → example"],
        )
        for line in desc.splitlines():
            assert line in text
        assert desc.count("\n") >= 2

    def test_includes_examples_section_with_dify_admin_invocation(
        self, build_help_text
    ) -> None:
        text = build_help_text(
            "Get one app.",
            _three_line_description(),
            examples=[
                '$ dify-admin apps get --name "FAQ Bot"\n'
                "  → show app details as JSON when --json is used"
            ],
        )
        assert "Examples:" in text
        assert "$ dify-admin" in text


class TestBuildHelpTextSideEffects:
    """REQ-001.2, PROP-002: destructive 用 Side Effects セクション。"""

    def test_includes_side_effects_section_when_destructive_content_given(
        self, build_help_text
    ) -> None:
        body = (
            "The app is permanently removed. This cannot be undone.\n"
            "Take an apps snapshot before running this command."
        )
        text = build_help_text(
            "Delete an application.",
            _three_line_description(),
            examples=["$ dify-admin apps delete ID\n  → deletes the app"],
            side_effects=body,
        )
        assert "Side Effects:" in text
        assert "permanently removed" in text

    def test_omits_side_effects_section_when_none(self, build_help_text) -> None:
        text = build_help_text(
            "List apps.",
            _three_line_description(),
            examples=["$ dify-admin apps list\n  → lists apps"],
            side_effects=None,
        )
        assert "Side Effects:" not in text


class TestBuildHelpTextIdempotent:
    """REQ-001.4, PROP-002: Idempotent ラベル。"""

    @pytest.mark.parametrize("value", ("yes", "no", "conditional"))
    def test_includes_idempotent_label_with_allowed_values(
        self, build_help_text, value: str
    ) -> None:
        text = build_help_text(
            "Sample command.",
            _three_line_description(),
            examples=["$ dify-admin apps list\n  → example"],
            idempotent=value,
        )
        assert f"Idempotent: {value}" in text


class TestBuildHelpTextJsonOutputKeys:
    """REQ-002.2, PROP-002: JSON 出力のトップレベルキー列挙。"""

    def test_includes_json_output_keys_when_provided(self, build_help_text) -> None:
        keys = ["id", "name", "mode", "model_config", "created_at"]
        text = build_help_text(
            "Get app details.",
            _three_line_description(),
            examples=["$ dify-admin apps get ID\n  → JSON object"],
            json_output_keys=keys,
        )
        assert "JSON Output Keys:" in text
        assert "id" in text and "name" in text
        # design.md 例: カンマ区切り1行
        assert "JSON Output Keys:" in text
        after = text.split("JSON Output Keys:", 1)[1].splitlines()[0].strip()
        for k in keys:
            assert k in after


class TestBuildHelpTextDryRunExample:
    """REQ-001.5, PROP-002: --dry-run 対応時は Examples に dry-run 例。"""

    def test_examples_contain_dry_run_when_supported(self, build_help_text) -> None:
        text = build_help_text(
            "Upload files to a knowledge base.",
            _three_line_description(),
            examples=[
                "$ dify-admin kb upload DATASET ./docs --dry-run\n"
                "  → lists files that would be uploaded without uploading"
            ],
            supports_dry_run=True,
        )
        ex_block = text.split("Examples:", 1)[1]
        if "JSON Output Keys:" in ex_block:
            ex_block = ex_block.split("JSON Output Keys:", 1)[0]
        if "Side Effects:" in ex_block:
            ex_block = ex_block.split("Side Effects:", 1)[0]
        assert "--dry-run" in ex_block
