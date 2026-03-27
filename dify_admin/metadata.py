"""Command metadata for dify-admin CLI.

Provides structured metadata for all CLI subcommands, used by
help text generation, command listing, and agent-friendly features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class CommandMeta:
    """Metadata for a single CLI subcommand."""

    name: str
    group: str  # "apps", "apps config", "kb", "kb docs", "audit", "top"
    description: str
    destructive: bool
    idempotent: Literal["yes", "no", "conditional"]
    supports_dry_run: bool
    supports_name: bool
    supports_json: bool
    supports_stdin: bool


COMMAND_METADATA: dict[str, CommandMeta] = {
    # ── Top-level ────────────────────────────────────────
    "login": CommandMeta(
        name="login",
        group="top",
        description="Test login and display session info",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "status": CommandMeta(
        name="status",
        group="top",
        description="Check Dify server status",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "doctor": CommandMeta(
        name="doctor",
        group="top",
        description="Run diagnostic checks on Dify connectivity and auth",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "reset-password": CommandMeta(
        name="reset-password",
        group="top",
        description="Reset account password via direct database access",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "plan": CommandMeta(
        name="plan",
        group="top",
        description="Show what changes would be made to reach desired state",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=True,
    ),
    "apply": CommandMeta(
        name="apply",
        group="top",
        description="Apply desired state from a YAML file",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=True,
    ),
    "env-diff": CommandMeta(
        name="env-diff",
        group="top",
        description="Compare two Dify environments",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "mcp serve": CommandMeta(
        name="mcp serve",
        group="top",
        description="Start the MCP server for AI assistant integration",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=False,
        supports_stdin=False,
    ),
    # ── Apps ──────────────────────────────────────────────
    "apps list": CommandMeta(
        name="apps list",
        group="apps",
        description="List all apps",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps create": CommandMeta(
        name="apps create",
        group="apps",
        description="Create a new app",
        destructive=True,
        idempotent="no",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps rename": CommandMeta(
        name="apps rename",
        group="apps",
        description="Rename an app",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps search": CommandMeta(
        name="apps search",
        group="apps",
        description="Search apps by name",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps delete": CommandMeta(
        name="apps delete",
        group="apps",
        description="Delete an app",
        destructive=True,
        idempotent="no",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps get": CommandMeta(
        name="apps get",
        group="apps",
        description="Get app details",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps export": CommandMeta(
        name="apps export",
        group="apps",
        description="Export app as DSL YAML",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps import": CommandMeta(
        name="apps import",
        group="apps",
        description="Import app from DSL YAML file",
        destructive=True,
        idempotent="no",
        supports_dry_run=True,
        supports_name=False,
        supports_json=True,
        supports_stdin=True,
    ),
    "apps scaffold": CommandMeta(
        name="apps scaffold",
        group="apps",
        description="Create an app from a template",
        destructive=True,
        idempotent="no",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps templates": CommandMeta(
        name="apps templates",
        group="apps",
        description="List available app templates",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps clone": CommandMeta(
        name="apps clone",
        group="apps",
        description="Clone an app (export + import)",
        destructive=True,
        idempotent="no",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps diff": CommandMeta(
        name="apps diff",
        group="apps",
        description="Compare two apps' configurations",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps dsl-diff": CommandMeta(
        name="apps dsl-diff",
        group="apps",
        description="Compare two DSL YAML files",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps snapshot": CommandMeta(
        name="apps snapshot",
        group="apps",
        description="Take a snapshot of an app's current state",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps snapshots": CommandMeta(
        name="apps snapshots",
        group="apps",
        description="List snapshots for an app",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    # ── Apps Config ───────────────────────────────────────
    "apps config get": CommandMeta(
        name="apps config get",
        group="apps config",
        description="Get app model configuration",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "apps config set": CommandMeta(
        name="apps config set",
        group="apps config",
        description="Update app model configuration from a JSON file",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=True,
    ),
    "apps config patch": CommandMeta(
        name="apps config patch",
        group="apps config",
        description="Patch app config with --set key=value and --unset key",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    # ── KB ────────────────────────────────────────────────
    "kb list": CommandMeta(
        name="kb list",
        group="kb",
        description="List knowledge bases",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb create": CommandMeta(
        name="kb create",
        group="kb",
        description="Create a knowledge base",
        destructive=True,
        idempotent="no",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb upload": CommandMeta(
        name="kb upload",
        group="kb",
        description="Upload files to a knowledge base",
        destructive=True,
        idempotent="no",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb clear": CommandMeta(
        name="kb clear",
        group="kb",
        description="Delete all documents in a knowledge base",
        destructive=True,
        idempotent="no",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb sync": CommandMeta(
        name="kb sync",
        group="kb",
        description="Sync local files to a knowledge base",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    # ── KB Docs ───────────────────────────────────────────
    "kb docs list": CommandMeta(
        name="kb docs list",
        group="kb docs",
        description="List documents in a knowledge base",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb docs status": CommandMeta(
        name="kb docs status",
        group="kb docs",
        description="Get indexing status of a document",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb docs reindex": CommandMeta(
        name="kb docs reindex",
        group="kb docs",
        description="Trigger re-indexing of a document",
        destructive=True,
        idempotent="conditional",
        supports_dry_run=False,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    "kb docs delete": CommandMeta(
        name="kb docs delete",
        group="kb docs",
        description="Delete a document from a knowledge base",
        destructive=True,
        idempotent="no",
        supports_dry_run=True,
        supports_name=True,
        supports_json=True,
        supports_stdin=False,
    ),
    # ── Audit ─────────────────────────────────────────────
    "audit list": CommandMeta(
        name="audit list",
        group="audit",
        description="Show recent audit log entries",
        destructive=False,
        idempotent="yes",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    "audit clear": CommandMeta(
        name="audit clear",
        group="audit",
        description="Clear the audit log",
        destructive=True,
        idempotent="no",
        supports_dry_run=False,
        supports_name=False,
        supports_json=True,
        supports_stdin=False,
    ),
    # NOTE: "apps restore" exists in CLI but is excluded from the
    # original 37-command spec. To add it, update the spec first
    # (Canon TDD exception procedure) then add the entry here.
}


def command_json_entry(meta: CommandMeta) -> dict[str, Any]:
    """Serialize command metadata for REQ-012 JSON listings."""
    return {
        "name": meta.name,
        "description": meta.description,
        "destructive": meta.destructive,
        "idempotent": meta.idempotent,
        "supports_dry_run": meta.supports_dry_run,
    }


def commands_for_json_list(group_filter: str | None) -> list[dict[str, Any]]:
    """Return command entries for JSON output.

    Args:
        group_filter: ``None`` for top-level commands (``group == "top"``), or
            e.g. ``"apps"`` for all commands in that metadata group.

    Returns:
        Sorted list of dicts suitable for ``output_json({"commands": ...})``.
    """
    if group_filter is None:
        metas = [m for m in COMMAND_METADATA.values() if m.group == "top"]
    else:
        metas = [m for m in COMMAND_METADATA.values() if m.group == group_filter]
    metas.sort(key=lambda m: m.name)
    return [command_json_entry(m) for m in metas]
