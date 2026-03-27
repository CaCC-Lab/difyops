"""Tests for dify_admin.metadata.CommandMeta and COMMAND_METADATA.

Based on .kiro/specs/agent-friendly-cli-improvements/requirements.md (REQ-007.x,
REQ-012.3) and tasks.md task 1.1 only. Implementation lives in dify_admin/metadata.py
(Canon TDD: tests precede implementation).

References:
- REQ-007.1–007.5: idempotency classification for CLI commands
- REQ-012.3: JSON listing fields per command (name, description, destructive,
  idempotent, supports_dry_run); tasks.md extends with group, supports_name,
  supports_json, supports_stdin for CommandMeta.
"""

from __future__ import annotations

import dataclasses
from typing import Literal, get_args, get_type_hints

import pytest

# --- Expected command keys (38 total): derived from tasks.md Phase 3 / 14 groupings
# and REQ-007 command lists (apps snapshot + apps snapshots + apps restore per design.md).

_EXPECTED_COMMAND_KEYS: frozenset[str] = frozenset(
    {
        # apps (16)
        "apps list",
        "apps get",
        "apps search",
        "apps export",
        "apps create",
        "apps rename",
        "apps delete",
        "apps import",
        "apps scaffold",
        "apps templates",
        "apps clone",
        "apps diff",
        "apps dsl-diff",
        "apps snapshot",
        "apps snapshots",
        "apps restore",
        # apps config (3)
        "apps config get",
        "apps config set",
        "apps config patch",
        # kb (5)
        "kb list",
        "kb create",
        "kb upload",
        "kb clear",
        "kb sync",
        # kb docs (4)
        "kb docs list",
        "kb docs status",
        "kb docs reindex",
        "kb docs delete",
        # audit (2)
        "audit list",
        "audit clear",
        # top-level (8)
        "login",
        "status",
        "doctor",
        "reset-password",
        "plan",
        "apply",
        "env-diff",
        "mcp serve",
    }
)

assert len(_EXPECTED_COMMAND_KEYS) == 38, "expected command catalogue must contain 38 entries"

_IDEMPOTENT_LITERAL = Literal["yes", "no", "conditional"]


def test_expected_command_catalogue_is_self_consistent() -> None:
    """Sanity check: the specification-derived set has exactly 38 unique names."""
    assert len(_EXPECTED_COMMAND_KEYS) == 38


def test_command_meta_is_dataclass_with_documented_fields() -> None:
    """CommandMeta SHALL be a dataclass exposing the fields from tasks.md 1.1."""
    from dify_admin.metadata import CommandMeta

    assert dataclasses.is_dataclass(CommandMeta)
    field_names = {f.name for f in dataclasses.fields(CommandMeta)}
    assert field_names == {
        "name",
        "group",
        "description",
        "destructive",
        "idempotent",
        "supports_dry_run",
        "supports_name",
        "supports_json",
        "supports_stdin",
    }


def test_command_meta_idempotent_annotation_matches_req007_5() -> None:
    """REQ-007.5: idempotent metadata values SHALL be yes | no | conditional."""
    from dify_admin.metadata import CommandMeta

    idem_field = next(f for f in dataclasses.fields(CommandMeta) if f.name == "idempotent")
    assert idem_field.name == "idempotent"
    hints = get_type_hints(CommandMeta, include_extras=True)
    ann = hints["idempotent"]
    literal_args = get_args(ann)
    assert literal_args, "idempotent should be annotated as Literal[...]"
    assert set(literal_args) == {"yes", "no", "conditional"}


def test_command_metadata_contains_exactly_38_commands() -> None:
    """tasks.md 1.1: COMMAND_METADATA SHALL contain all 38 CLI subcommands."""
    from dify_admin.metadata import COMMAND_METADATA

    assert len(COMMAND_METADATA) == 38
    assert set(COMMAND_METADATA.keys()) == _EXPECTED_COMMAND_KEYS


@pytest.mark.parametrize("cmd_key", sorted(_EXPECTED_COMMAND_KEYS))
def test_each_command_metadata_entry_shape_and_value_domains(cmd_key: str) -> None:
    """REQ-012.3 + tasks 1.1: type and value-domain checks for every command."""
    from dify_admin.metadata import COMMAND_METADATA, CommandMeta

    meta = COMMAND_METADATA[cmd_key]
    assert isinstance(meta, CommandMeta)

    assert isinstance(meta.name, str) and meta.name.strip() != ""
    assert isinstance(meta.group, str) and meta.group.strip() != ""
    assert isinstance(meta.description, str) and meta.description.strip() != ""

    assert isinstance(meta.destructive, bool)
    assert isinstance(meta.supports_dry_run, bool)
    assert isinstance(meta.supports_name, bool)
    assert isinstance(meta.supports_json, bool)
    assert isinstance(meta.supports_stdin, bool)

    assert meta.idempotent in get_args(_IDEMPOTENT_LITERAL), (
        f"{cmd_key}: idempotent must be one of {get_args(_IDEMPOTENT_LITERAL)}, "
        f"got {meta.idempotent!r}"
    )

    # name SHOULD match catalogue key (machine-readable stable id for agents).
    assert meta.name == cmd_key


def test_idempotent_field_only_uses_yes_no_conditional() -> None:
    """REQ-007.5 / REQ-012.3: idempotent field domain is fixed."""
    from dify_admin.metadata import COMMAND_METADATA

    allowed = set(get_args(_IDEMPOTENT_LITERAL))
    for key, meta in COMMAND_METADATA.items():
        assert meta.idempotent in allowed, f"{key}: invalid idempotent {meta.idempotent!r}"
