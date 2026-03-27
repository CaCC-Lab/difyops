"""Output helpers for dify-admin CLI.

Provides JSON and Rich table output modes, controlled by the --json flag.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Sequence

import click
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

_STDERR_CONSOLE = Console(stderr=True)


def get_json_mode(ctx: click.Context) -> bool:
    """Return True if JSON output mode is enabled."""
    return bool(ctx.obj and ctx.obj.get("json", False))


def get_console(ctx: click.Context) -> Console:
    """Return a Console instance, cached on ctx.obj.

    In JSON mode, Rich output goes to stderr so stdout stays clean for JSON.
    """
    if ctx.obj is None:
        return Console()
    if "_console" not in ctx.obj:
        ctx.obj["_console"] = _STDERR_CONSOLE if get_json_mode(ctx) else Console()
    return ctx.obj["_console"]


def output_json(data: Any) -> None:
    """Write JSON to stdout."""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def output_table(
    ctx: click.Context,
    data: Sequence[dict[str, Any]],
    title: str,
    columns: list[tuple[str, dict[str, Any]]],
    row_extractor: Callable[[dict[str, Any]], tuple[str, ...]],
) -> None:
    """Output data as a Rich table or JSON array.

    Args:
        ctx: Click context.
        data: List of dicts to display.
        title: Table title (Rich mode only).
        columns: List of (name, kwargs) for Table.add_column.
        row_extractor: Function to extract row values from each dict.
    """
    if get_json_mode(ctx):
        output_json(list(data))
        return
    console = get_console(ctx)
    table = Table(title=title)
    for col_name, col_kwargs in columns:
        table.add_column(col_name, **col_kwargs)
    for item in data:
        table.add_row(*row_extractor(item))
    console.print(table)


def output_syntax(ctx: click.Context, data: dict[str, Any]) -> None:
    """Output data as JSON (stdout) or syntax-highlighted Rich output."""
    if get_json_mode(ctx):
        output_json(data)
        return
    console = get_console(ctx)
    console.print(Syntax(json.dumps(data, indent=2, ensure_ascii=False), "json"))


def output_message(ctx: click.Context, data: Any, message: str) -> None:
    """Output a message (Rich mode) or JSON data (JSON mode)."""
    if get_json_mode(ctx):
        output_json(data)
        return
    get_console(ctx).print(message)


# output_result is an alias for output_message with a narrower type hint.
output_result = output_message


def confirm_destructive(ctx: click.Context, message: str, yes: bool = False) -> bool:
    """Confirm a destructive operation.

    In JSON mode, --yes is required (no interactive prompt).
    Returns True if confirmed, False otherwise.

    Args:
        ctx: Click context
        message: Confirmation message to display
        yes: If True, skip confirmation
    """
    if yes:
        return True
    if get_json_mode(ctx):
        _STDERR_CONSOLE.print(
            "[red]--yes is required for destructive operations in JSON mode[/red]"
        )
        return False
    return click.confirm(message)


def output_json_error(
    error_type: str,
    message: str,
    *,
    hint: str | None = None,
    status_code: int | None = None,
    exit_code: int = 1,
) -> None:
    """Output structured JSON error to stderr.

    stdout is reserved for success data only. Agents detect errors via
    exit code and parse structured error details from stderr.

    Args:
        error_type: Exception class name (e.g. "DifyNotFoundError")
        message: Human-readable error message
        hint: Optional recovery suggestion
        status_code: HTTP status code (for API errors)
        exit_code: CLI exit code
    """
    error_obj: dict[str, Any] = {
        "error": error_type,
        "message": message,
        "hint": hint,
        "exit_code": exit_code,
    }
    if status_code is not None:
        error_obj["status_code"] = status_code
    sys.stderr.write(json.dumps(error_obj, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def output_error(message: str) -> None:
    """Output error message to stderr."""
    _STDERR_CONSOLE.print(message)
