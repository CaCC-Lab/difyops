"""dify-admin CLI — manage Dify from the command line."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import click

from dify_admin.auth import AuthenticationError
from dify_admin.client import DifyClient
from dify_admin.diff import diff_configs, format_diff_table
from dify_admin.env import load_dotenv
from dify_admin.exceptions import DifyAdminError
from dify_admin.help import build_help_text
from dify_admin.metadata import commands_for_json_list
from dify_admin.output import (
    confirm_destructive,
    get_console,
    get_json_mode,
    output_error,
    output_json,
    output_json_error,
    output_message,
    output_result,
    output_syntax,
    output_table,
)
from dify_admin.password import reset_via_docker
from dify_admin.patch import apply_patches
from dify_admin.resolve import (
    AmbiguousNameError,
    NameNotFoundError,
    resolve_app_by_name,
    resolve_kb_by_name,
)
from dify_admin.sync import compute_sync_plan, execute_sync


def _read_input(file_path: str | None, *, allow_stdin: bool = True) -> str:
    """Read text from a file path or from stdin when ``file_path`` is ``"-"``.

    Args:
        file_path: Path to a file, or ``"-"`` to read from ``sys.stdin``.
        allow_stdin: If ``False``, refuse to read from stdin.

    Returns:
        UTF-8 text read from the file or stdin.

    Raises:
        click.UsageError: If stdin is empty when ``"-"`` is used, or stdin is disallowed.
    """
    if file_path is None:
        raise click.UsageError("No input path specified.")

    if file_path == "-":
        if not allow_stdin:
            raise click.UsageError("stdin is not allowed for this invocation.")
        data = sys.stdin.read()
        if data == "":
            raise click.UsageError("No input received from stdin")
        return data

    return Path(file_path).read_text(encoding="utf-8")


def _resolve_credentials(email: Optional[str], password: Optional[str]) -> tuple[str, str]:
    """Resolve credentials from CLI args or environment variables.

    Priority: CLI argument > environment variable.
    Raises click.UsageError if either is missing.
    """
    resolved_email = email or os.environ.get("DIFY_EMAIL")
    resolved_password = password or os.environ.get("DIFY_PASSWORD")
    if not resolved_email or not resolved_password:
        missing = []
        if not resolved_email:
            missing.append("--email or DIFY_EMAIL")
        if not resolved_password:
            missing.append("--password or DIFY_PASSWORD")
        raise click.UsageError(f"Missing credentials: {', '.join(missing)}")
    return resolved_email, resolved_password


def _make_client(url: str, email: str, password: str) -> DifyClient:
    """Create and authenticate a DifyClient."""
    client = DifyClient(url)
    try:
        client.login(email, password)
    except AuthenticationError as e:
        client.close()
        output_error(f"[red]Login failed:[/red] {e}")
        raise SystemExit(1)
    return client


def _resolve_url(url: Optional[str]) -> str:
    """Resolve Dify API URL from CLI arg or DIFY_URL env var.

    Empty strings are treated as unset.
    """
    return url or os.environ.get("DIFY_URL") or "http://localhost:5001"


def _resolve_app_id(
    client: DifyClient,
    app_id: Optional[str],
    name: Optional[str],
) -> str:
    """Resolve app ID from --name or positional argument.

    Raises click.UsageError if neither or both are provided.
    """
    if app_id and name:
        raise click.UsageError("Specify either APP_ID or --name, not both.")
    if name:
        try:
            app = resolve_app_by_name(client, name)
        except NameNotFoundError as e:
            output_error(
                f"[red]{e}[/red]\n[dim]Run 'dify-admin apps list' to see available apps[/dim]"
            )
            raise SystemExit(1)
        except AmbiguousNameError as e:
            output_error(
                f"[red]{e}[/red]\n[dim]Use APP_ID instead of --name to select a single app.[/dim]"
            )
            raise SystemExit(1)
        return app["id"]
    if not app_id:
        raise click.UsageError("Specify APP_ID or --name.")
    return app_id


def _resolve_dataset_id(
    client: DifyClient,
    dataset_id: Optional[str],
    name: Optional[str],
) -> str:
    """Resolve dataset ID from --name or positional argument.

    Raises click.UsageError if neither or both are provided.
    """
    if dataset_id and name:
        raise click.UsageError("Specify either DATASET_ID or --name, not both.")
    if name:
        try:
            ds = resolve_kb_by_name(client, name)
        except NameNotFoundError as e:
            output_error(
                f"[red]{e}[/red]\n[dim]Run 'dify-admin kb list' to see available KBs[/dim]"
            )
            raise SystemExit(1)
        except AmbiguousNameError as e:
            output_error(f"[red]{e}[/red]\n[dim]Use DATASET_ID instead of --name[/dim]")
            raise SystemExit(1)
        return ds["id"]
    if not dataset_id:
        raise click.UsageError("Specify DATASET_ID or --name.")
    return dataset_id


class DifyAdminGroup(click.Group):
    """Click group with structured error handling."""

    def invoke(self, ctx: click.Context) -> Any:
        """Invoke with error handling, exit codes, and JSON error output."""
        import httpx

        from dify_admin.exceptions import (
            DifyConnectionError,
            exit_code_for_exception,
        )

        try:
            return super().invoke(ctx)
        except DifyConnectionError as e:
            code = exit_code_for_exception(e)
            if get_json_mode(ctx):
                output_json_error(
                    "DifyConnectionError",
                    str(e),
                    hint=e.hint if hasattr(e, "hint") else None,
                    exit_code=code,
                )
            else:
                output_error(f"[red]{e}[/red]")
            raise SystemExit(code)
        except httpx.TimeoutException as e:
            code = exit_code_for_exception(e)
            if get_json_mode(ctx):
                output_json_error(
                    "TimeoutError",
                    str(e),
                    hint="Check network connectivity or increase timeout",
                    exit_code=code,
                )
            else:
                output_error(f"[red]Timeout: {e}[/red]")
            raise SystemExit(code)
        except DifyAdminError as e:
            code = exit_code_for_exception(e)
            if get_json_mode(ctx):
                output_json_error(
                    type(e).__name__,
                    str(e),
                    hint=e.hint if hasattr(e, "hint") else None,
                    status_code=e.status_code if hasattr(e, "status_code") else None,
                    exit_code=code,
                )
            else:
                output_error(f"[red]{e}[/red]")
            raise SystemExit(code)


@click.group(cls=DifyAdminGroup, invoke_without_command=True)
@click.option(
    "--url",
    default=None,
    help="Dify API URL (env: DIFY_URL, default: http://localhost:5001)",
)
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
@click.option("--env-file", default=None, type=click.Path(), help="Path to .env file")
def main(ctx: click.Context, url: Optional[str], json_mode: bool, env_file: Optional[str]) -> None:
    """dify-admin — Manage Dify without the GUI."""
    load_dotenv(env_file)
    ctx.ensure_object(dict)
    ctx.obj["url"] = _resolve_url(url)
    ctx.obj["json"] = json_mode
    if ctx.invoked_subcommand is None:
        if json_mode:
            output_json({"commands": commands_for_json_list(None)})
        else:
            click.echo(ctx.get_help())


# ── Login ───────────────────────────────────────────────────


@main.command()
@click.option("--email", default=None, help="Account email")
@click.option("--password", default=None, help="Account password")
@click.pass_context
def login(ctx: click.Context, email: Optional[str], password: Optional[str]) -> None:
    """Test login and display session info."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        at = client.session.access_token
        cs = client.session.csrf_token
    data = {"access_token": at, "csrf_token": cs}
    if get_json_mode(ctx):
        output_json(data)
    else:
        console = get_console(ctx)
        console.print("[green]Login successful[/green]")
        console.print(f"  access_token: {at[:30]}{'...' if len(at) > 30 else ''}")
        console.print(f"  csrf_token:   {cs[:30]}{'...' if len(cs) > 30 else ''}")


login.help = build_help_text(
    summary="Test login and display session info.",
    description=(
        "Authenticate against the Dify server and display the resulting session tokens.\n"
        "Input: --email and --password (or DIFY_EMAIL / DIFY_PASSWORD env vars).\n"
        "Output: access_token and csrf_token from the authenticated session."
    ),
    examples=[
        "$ dify-admin login --email admin@example.com --password secret",
        "$ dify-admin --json login",
    ],
    idempotent="yes",
    json_output_keys=["access_token", "csrf_token"],
)


# ── Apps ────────────────────────────────────────────────────


@main.group(invoke_without_command=True)
@click.option("--json", "apps_json_mode", is_flag=True, default=False, help="Output as JSON")
@click.pass_context
def apps(ctx: click.Context, apps_json_mode: bool) -> None:
    """Manage Dify apps."""
    if apps_json_mode:
        ctx.ensure_object(dict)
        ctx.obj["json"] = True
    if ctx.invoked_subcommand is None:
        if get_json_mode(ctx):
            output_json({"commands": commands_for_json_list("apps")})
        else:
            click.echo(ctx.get_help())


@apps.command("list")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.pass_context
def apps_list(ctx: click.Context, email: Optional[str], password: Optional[str]) -> None:
    """List all apps."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        apps_data = client.apps_list()

    output_table(
        ctx,
        apps_data,
        title="Dify Apps",
        columns=[
            ("ID", {"style": "dim", "max_width": 12}),
            ("Name", {"style": "bold"}),
            ("Mode", {}),
            ("Created", {}),
        ],
        row_extractor=lambda app: (
            app.get("id", "")[:12],
            app.get("name", "-"),
            app.get("mode", "-"),
            str(app.get("created_at", "")),
        ),
    )


apps_list.help = build_help_text(
    summary="List all apps.",
    description=(
        "Retrieve every app visible to the authenticated account.\n"
        "Returns a table of app IDs, names, modes, and creation dates.\n"
        "Use --json for machine-readable output."
    ),
    examples=[
        "$ dify-admin apps list",
        "$ dify-admin --json apps list",
    ],
    idempotent="yes",
)


@apps.command("create")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option("--name", required=True, help="App name")
@click.option(
    "--mode",
    default="chat",
    help="App mode (chat, completion, advanced-chat, workflow)",
)
@click.option("--description", default="", help="App description")
@click.pass_context
def apps_create(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    name: str,
    mode: str,
    description: str,
) -> None:
    """Create a new app."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        result = client.apps_create(name=name, mode=mode, description=description)
    output_result(
        ctx,
        result,
        f"[green]Created app:[/green] {result.get('id', 'unknown')}\n"
        f"  Name: {result.get('name')}\n"
        f"  Mode: {result.get('mode')}",
    )


apps_create.help = build_help_text(
    summary="Create a new app.",
    description=(
        "Create a new Dify app with the specified name, mode, and description.\n"
        "Supported modes: chat, completion, advanced-chat, workflow.\n"
        "Returns the created app's ID and metadata."
    ),
    examples=[
        '$ dify-admin apps create --name "Bot" --mode chat',
        '$ dify-admin apps create --name "Summarizer" --mode completion',
    ],
    side_effects="A new app is created in the Dify instance.",
    idempotent="no",
)


@apps.command("rename")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="Current app name to resolve")
@click.option("--new-name", required=True, help="New app name")
@click.option("--description", default=None, help="New description")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show current and new name without renaming",
)
@click.pass_context
def apps_rename(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    new_name: str,
    description: Optional[str],
    dry_run: bool,
) -> None:
    """Rename an app."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        resolved_id = _resolve_app_id(client, app_id, app_name)
        current = client.apps_get(resolved_id)
        cur_name = str(current.get("name", ""))
        if dry_run:
            if get_json_mode(ctx):
                output_json(
                    {
                        "dry_run": True,
                        "app_id": resolved_id,
                        "current_name": cur_name,
                        "new_name": new_name,
                    }
                )
            else:
                console = get_console(ctx)
                console.print(
                    f"[bold]Dry-run:[/bold] Would rename [cyan]{cur_name}[/cyan] "
                    f"→ [green]{new_name}[/green] (app_id={resolved_id})"
                )
            return
        result = client.apps_rename(resolved_id, new_name, description=description)
    output_result(
        ctx,
        result,
        f"[green]Renamed app:[/green] {resolved_id}\n  New name: {new_name}",
    )


apps_rename.help = build_help_text(
    summary="Rename an app.",
    description=(
        "Change the display name of an existing app.\n"
        "Accepts either an APP_ID positional argument or --name to resolve by name.\n"
        "Optionally update the description at the same time."
    ),
    examples=[
        '$ dify-admin apps rename APP_ID --new-name "New Name"',
        '$ dify-admin apps rename --name "Old Name" --new-name "New Name"',
        '$ dify-admin apps rename APP_ID --new-name "New Name" --dry-run',
    ],
    side_effects="App name is changed in the Dify instance.",
    idempotent="conditional",
    supports_dry_run=True,
)


@apps.command("search")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("query")
@click.option("--mode", default=None, help="Filter by app mode")
@click.pass_context
def apps_search(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    query: str,
    mode: Optional[str],
) -> None:
    """Search apps by name."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        results = client.apps_search(query, mode=mode)

    output_table(
        ctx,
        results,
        title=f"Search: {query}",
        columns=[
            ("ID", {"style": "dim", "max_width": 12}),
            ("Name", {"style": "bold"}),
            ("Mode", {}),
            ("Created", {}),
        ],
        row_extractor=lambda app: (
            app.get("id", "")[:12],
            app.get("name", "-"),
            app.get("mode", "-"),
            str(app.get("created_at", "")),
        ),
    )


apps_search.help = build_help_text(
    summary="Search apps by name.",
    description=(
        "Search for apps whose name matches the given query string.\n"
        "Optionally filter results by app mode.\n"
        "Returns a table of matching apps with IDs, names, modes, and dates."
    ),
    examples=[
        '$ dify-admin apps search "FAQ"',
        '$ dify-admin apps search "Bot" --mode chat',
    ],
    idempotent="yes",
)


@apps.command("delete")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be deleted")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def apps_delete(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    dry_run: bool,
    yes: bool,
) -> None:
    """Delete an app."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        if dry_run:
            output_message(
                ctx,
                {"would_delete": app_id},
                f"[yellow]Would delete app:[/yellow] {app_id}",
            )
            return
        if not confirm_destructive(ctx, f"Delete app {app_id}?", yes=yes):
            return
        client.apps_delete(app_id)
    output_message(ctx, {"deleted": app_id}, f"[green]Deleted app:[/green] {app_id}")


apps_delete.help = build_help_text(
    summary="Delete an app.",
    description=(
        "Permanently delete an app from the Dify instance.\n"
        "Accepts either an APP_ID positional argument or --name to resolve by name.\n"
        "Use --dry-run to preview without deleting. This action cannot be undone."
    ),
    examples=[
        "$ dify-admin apps delete APP_ID",
        '$ dify-admin apps delete --name "My Bot"',
        "$ dify-admin apps delete APP_ID --dry-run",
    ],
    side_effects="App is permanently deleted and cannot be undone.",
    idempotent="conditional",
    supports_dry_run=True,
)


@apps.command("get")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.pass_context
def apps_get(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
) -> None:
    """Get app details."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_get(app_id)
    output_syntax(ctx, result)


apps_get.help = build_help_text(
    summary="Get app details.",
    description=(
        "Retrieve the full configuration and metadata for a single app.\n"
        "Accepts either an APP_ID positional argument or --name to resolve by name.\n"
        "Output is displayed as syntax-highlighted JSON."
    ),
    examples=[
        "$ dify-admin apps get APP_ID",
        '$ dify-admin apps get --name "My Bot"',
    ],
    idempotent="yes",
)


@apps.command("export")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option(
    "-o",
    "--output",
    "output_file",
    default=None,
    type=click.Path(),
    help="Output file path",
)
@click.pass_context
def apps_export(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    output_file: Optional[str],
) -> None:
    """Export app as DSL YAML."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_export(app_id)

    if get_json_mode(ctx):
        output_json(result)
        return

    yaml_data = result.get("data", "")
    if output_file:
        Path(output_file).write_text(yaml_data, encoding="utf-8")
        get_console(ctx).print(f"[green]Exported to:[/green] {output_file}")
    else:
        click.echo(yaml_data)


apps_export.help = build_help_text(
    summary="Export app as DSL YAML.",
    description=(
        "Export an app's full configuration as a DSL YAML document.\n"
        "Accepts either an APP_ID positional argument or --name to resolve by name.\n"
        "Use -o/--output to write directly to a file."
    ),
    examples=[
        "$ dify-admin apps export APP_ID",
        '$ dify-admin apps export --name "My Bot" -o bot.yml',
    ],
    idempotent="yes",
)


@apps.command("import")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option(
    "--file",
    "import_file",
    required=True,
    type=str,
    help="YAML file to import (use - for stdin)",
)
@click.option("--name", "app_name", default=None, help="Override app name")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse YAML and show app name/mode without importing",
)
@click.pass_context
def apps_import_cmd(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    import_file: str,
    app_name: Optional[str],
    dry_run: bool,
) -> None:
    """Import app from DSL YAML file."""  # replaced below
    import yaml as yaml_lib

    email, password = _resolve_credentials(email, password)
    if import_file == "-":
        yaml_data = _read_input("-")
    else:
        path = Path(import_file)
        if not path.is_file():
            raise click.BadParameter(
                f"File not found or not a file: {import_file}",
                param_hint="--file",
            )
        yaml_data = path.read_text(encoding="utf-8")
    if dry_run:
        try:
            data = yaml_lib.safe_load(yaml_data)
        except yaml_lib.YAMLError as e:
            output_error(f"[red]Invalid YAML:[/red] {e}")
            raise SystemExit(1)
        if not isinstance(data, dict):
            output_error(f"[red]DSL root must be a mapping, got {type(data).__name__}[/red]")
            raise SystemExit(1)
        app_block = data.get("app") if isinstance(data.get("app"), dict) else {}
        extracted_name = app_block.get("name", "(unknown)")
        extracted_mode = app_block.get("mode", "(unknown)")
        if get_json_mode(ctx):
            output_json(
                {
                    "dry_run": True,
                    "app_name": extracted_name,
                    "mode": extracted_mode,
                }
            )
        else:
            console = get_console(ctx)
            console.print(
                "[bold]Dry-run:[/bold] YAML parsed. "
                f"app.name={extracted_name!r}, app.mode={extracted_mode!r}"
            )
        return
    with _make_client(ctx.obj["url"], email, password) as client:
        result = client.apps_import(yaml_data, name=app_name)
    output_result(
        ctx,
        result,
        f"[green]Imported app:[/green] {result.get('id', 'unknown')}\n"
        f"  Name: {result.get('name', '-')}",
    )


apps_import_cmd.help = build_help_text(
    summary="Import app from DSL YAML file.",
    description=(
        "Create a new app by importing a DSL YAML file.\n"
        "The YAML file must be a valid Dify app export.\n"
        "Use --name to override the app name from the YAML."
    ),
    examples=[
        "$ dify-admin apps import --file bot.yml",
        '$ dify-admin apps import --file bot.yml --name "Imported Bot"',
        "$ dify-admin apps import --file bot.yml --dry-run",
    ],
    side_effects="A new app is created from the DSL YAML file.",
    idempotent="no",
    supports_dry_run=True,
)


@apps.command("scaffold")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("template_id")
@click.option("--name", "app_name", default=None, help="Override app name")
@click.pass_context
def apps_scaffold(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    template_id: str,
    app_name: Optional[str],
) -> None:
    """Create an app from a template."""  # replaced below
    from dify_admin.templates import get_template

    try:
        template = get_template(template_id)
    except KeyError as e:
        output_error(f"[red]{e}[/red]")
        raise SystemExit(1)

    if app_name:
        template["name"] = app_name

    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        result = client.apps_create(
            name=template["name"],
            mode=template["mode"],
            description=template.get("description", ""),
        )
    output_result(
        ctx,
        result,
        f"[green]Created from template '{template_id}':[/green] {result.get('id', '?')}\n"
        f"  Name: {result.get('name')}",
    )


apps_scaffold.help = build_help_text(
    summary="Create an app from a template.",
    description=(
        "Create a new app using a built-in template.\n"
        "Available templates: chat-basic, chat-rag, completion, workflow, agent.\n"
        "Use --name to override the default template name."
    ),
    examples=[
        '$ dify-admin apps scaffold chat-rag --name "RAG Bot"',
        "$ dify-admin apps scaffold workflow",
    ],
    side_effects="A new app is created from the selected template.",
    idempotent="no",
)


@apps.command("templates")
@click.pass_context
def apps_templates(ctx: click.Context) -> None:
    """List available app templates."""  # replaced below
    from dify_admin.templates import list_templates

    templates = list_templates()
    output_table(
        ctx,
        templates,
        title="App Templates",
        columns=[
            ("ID", {"style": "bold"}),
            ("Name", {}),
            ("Mode", {}),
            ("Description", {}),
        ],
        row_extractor=lambda t: (
            t.get("id", ""),
            t.get("name", ""),
            t.get("mode", ""),
            t.get("description", ""),
        ),
    )


apps_templates.help = build_help_text(
    summary="List available app templates.",
    description=(
        "Display all built-in app templates that can be used with scaffold.\n"
        "Each template includes an ID, name, mode, and description.\n"
        "Use this to discover available templates before scaffolding."
    ),
    examples=[
        "$ dify-admin apps templates",
        "$ dify-admin --json apps templates",
    ],
    idempotent="yes",
)


@apps.command("clone")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="Source app name to resolve")
@click.option("--clone-name", default=None, help="Name for the cloned app")
@click.pass_context
def apps_clone(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    clone_name: Optional[str],
) -> None:
    """Clone an app (export + import)."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_clone(app_id, name=clone_name)
    output_result(
        ctx,
        result,
        f"[green]Cloned app:[/green] {result.get('id', 'unknown')}\n"
        f"  Name: {result.get('name', '-')}",
    )


apps_clone.help = build_help_text(
    summary="Clone an app.",
    description=(
        "Create a copy of an existing app by exporting and re-importing it.\n"
        "Accepts either an APP_ID positional argument or --name to resolve by name.\n"
        "Use --clone-name to set a custom name for the new copy."
    ),
    examples=[
        "$ dify-admin apps clone APP_ID",
        '$ dify-admin apps clone --name "Original Bot" --clone-name "Bot Copy"',
    ],
    side_effects="A copy of the app is created in the Dify instance.",
    idempotent="no",
)


@apps.command("diff")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("left_app_id")
@click.argument("right_app_id")
@click.pass_context
def apps_diff(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    left_app_id: str,
    right_app_id: str,
) -> None:
    """Compare two apps' configurations."""  # replaced below
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        left = client.apps_get(left_app_id)
        right = client.apps_get(right_app_id)

    left_name = left.get("name", left_app_id[:12])
    right_name = right.get("name", right_app_id[:12])
    diffs = diff_configs(left, right, left_name, right_name)

    if get_json_mode(ctx):
        output_json(diffs)
        return

    console = get_console(ctx)
    if not diffs:
        console.print("[green]No differences found.[/green]")
    else:
        console.print(f"[bold]Diff: {left_name} vs {right_name}[/bold]")
        console.print(f"  {len(diffs)} differences found\n")
        console.print(format_diff_table(diffs, left_name, right_name))


apps_diff.help = build_help_text(
    summary="Compare two apps' configurations.",
    description=(
        "Show a side-by-side diff of two apps' configurations.\n"
        "Takes two APP_ID arguments and compares their settings.\n"
        "Differences are displayed in a formatted table."
    ),
    examples=[
        "$ dify-admin apps diff APP_ID_1 APP_ID_2",
        "$ dify-admin --json apps diff APP_ID_1 APP_ID_2",
    ],
    idempotent="yes",
)


@apps.command("dsl-diff")
@click.argument("left_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("right_file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def apps_dsl_diff(
    ctx: click.Context,
    left_file: str,
    right_file: str,
) -> None:
    """Compare two DSL YAML files."""  # replaced below
    from dify_admin.diff import diff_dsl, format_diff_table

    left_yaml = Path(left_file).read_text(encoding="utf-8")
    right_yaml = Path(right_file).read_text(encoding="utf-8")
    left_label = Path(left_file).name
    right_label = Path(right_file).name

    diffs = diff_dsl(left_yaml, right_yaml, left_label, right_label)

    if get_json_mode(ctx):
        output_json(diffs)
        return

    console = get_console(ctx)
    if not diffs:
        console.print("[green]No differences found.[/green]")
    else:
        console.print(f"[bold]DSL diff: {left_label} vs {right_label}[/bold]")
        console.print(f"  {len(diffs)} differences found\n")
        console.print(format_diff_table(diffs, left_label, right_label))


apps_dsl_diff.help = build_help_text(
    summary="Compare two DSL YAML files.",
    description=(
        "Show a side-by-side diff of two local DSL YAML files.\n"
        "Does not require a Dify connection; works entirely offline.\n"
        "Differences are displayed in a formatted table."
    ),
    examples=[
        "$ dify-admin apps dsl-diff left.yml right.yml",
        "$ dify-admin --json apps dsl-diff left.yml right.yml",
    ],
    idempotent="yes",
)


@apps.group("config")
def apps_config() -> None:
    """Manage app model configuration."""


@apps_config.command("get")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.pass_context
def apps_config_get(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
) -> None:
    """Get app model configuration."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_get_config(app_id)
    output_syntax(ctx, result)


apps_config_get.help = build_help_text(
    "Get app model configuration.",
    "Retrieve the model configuration for a Dify app.\n"
    "Input: APP_ID or --name for name resolution.\n"
    "Output: JSON object with model settings, prompts, and parameters.",
    examples=[
        "$ dify-admin apps config get APP_ID\n"
        "  → display model configuration as syntax-highlighted JSON",
        '$ dify-admin apps config get --name "FAQ Bot"\n'
        "  → resolve by name and display configuration",
    ],
    idempotent="yes",
    json_output_keys=["model", "pre_prompt", "opening_statement"],
)


@apps_config.command("set")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option(
    "--file",
    "config_file",
    required=True,
    type=str,
    help="JSON config file (use - for stdin)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate JSON locally without calling the API",
)
@click.pass_context
def apps_config_set(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    config_file: str,
    dry_run: bool,
) -> None:
    """Update app model configuration from a JSON file."""  # noqa: D401
    email, password = _resolve_credentials(email, password)
    try:
        if config_file == "-":
            raw = _read_input("-")
        else:
            raw = Path(config_file).read_text(encoding="utf-8")
    except (PermissionError, UnicodeDecodeError) as e:
        output_error(f"[red]Cannot read {config_file}:[/red] {e}")
        raise SystemExit(1)
    try:
        config_data = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:100]
        output_error(
            f"[red]Invalid JSON in {config_file}:[/red] {e}\n"
            f"[dim]Input (first 100 chars): {snippet}[/dim]"
        )
        raise SystemExit(1)
    if not isinstance(config_data, dict):
        output_error(f"[red]Config must be a JSON object, got {type(config_data).__name__}[/red]")
        raise SystemExit(1)
    if dry_run:
        if get_json_mode(ctx):
            output_json({"dry_run": True, "config": config_data})
        else:
            console = get_console(ctx)
            console.print(f"[bold]Dry-run:[/bold] JSON is valid ({type(config_data).__name__}).")
            output_syntax(ctx, config_data)
        return
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_update_config(app_id, config_data)
    output_result(
        ctx,
        result,
        f"[green]Updated config for app:[/green] {app_id}",
    )


apps_config_set.help = build_help_text(
    "Update app model configuration from a JSON file.",
    "Replace the entire model configuration for a Dify app.\n"
    "Input: APP_ID or --name, plus --file with a JSON config file.\n"
    "Output: confirmation message or JSON result.",
    examples=[
        "$ dify-admin apps config set APP_ID --file config.json\n"
        "  → apply the JSON configuration to the app",
        '$ dify-admin apps config set --name "Bot" --file config.json\n'
        "  → resolve by name and apply configuration",
        "$ dify-admin apps config set APP_ID --file c.json --dry-run\n"
        "  → validate JSON locally without applying",
    ],
    side_effects=(
        "The entire model configuration is overwritten.\n"
        "Previous settings are lost unless a snapshot was taken."
    ),
    idempotent="conditional",
    json_output_keys=["result"],
    supports_dry_run=True,
)


@apps_config.command("patch")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option(
    "--set", "set_ops", multiple=True, help="Set key=value (e.g. --set model.name=gpt-4o)"
)
@click.option("--unset", "unset_ops", multiple=True, help="Remove key (e.g. --unset model.stop)")
@click.option("--dry-run", is_flag=True, default=False, help="Show patched config without applying")
@click.pass_context
def apps_config_patch(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    set_ops: tuple[str, ...],
    unset_ops: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Patch app config with --set key=value and --unset key.

    Uses dot-notation for nested keys (e.g. model.completion_params.temperature).
    """
    if not set_ops and not unset_ops:
        raise click.UsageError("Specify at least one --set or --unset operation.")
    email, password = _resolve_credentials(email, password)

    parsed_sets: list[tuple[str, str]] = []
    for op in set_ops:
        if "=" not in op:
            raise click.UsageError(f"Invalid --set format: '{op}'. Use key=value.")
        key, _, value = op.partition("=")
        parsed_sets.append((key, value))

    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        config = client.apps_get_config(app_id)
        apply_patches(config, set_ops=parsed_sets, unset_ops=list(unset_ops))

        if dry_run:
            output_syntax(ctx, config)
            return

        result = client.apps_update_config(app_id, config)
    output_result(
        ctx,
        result,
        f"[green]Patched config for app:[/green] {app_id}",
    )


apps_config_patch.help = build_help_text(
    "Patch app config with --set key=value and --unset key.",
    "Modify specific config values using dot-notation keys.\n"
    "Input: APP_ID or --name, plus --set and/or --unset operations.\n"
    "Output: patched configuration or confirmation.",
    examples=[
        "$ dify-admin apps config patch APP_ID --set model.name=gpt-4o\n  → change the model name",
        '$ dify-admin apps config patch --name "Bot" '
        "--set model.completion_params.temperature=0.7\n"
        "  → resolve by name and patch temperature",
        "$ dify-admin apps config patch APP_ID "
        "--set model.name=gpt-4o --dry-run\n"
        "  → preview patched config without applying",
    ],
    side_effects=(
        "Specified config values are modified in place.\nUnspecified values remain unchanged."
    ),
    idempotent="conditional",
    json_output_keys=["result"],
    supports_dry_run=True,
)


# ── Knowledge Bases ─────────────────────────────────────────


@main.group()
def kb() -> None:
    """Manage knowledge bases."""


@kb.command("list")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.pass_context
def kb_list(ctx: click.Context, email: Optional[str], password: Optional[str]) -> None:
    """List knowledge bases."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        datasets = client.kb_list()

    output_table(
        ctx,
        datasets,
        title="Knowledge Bases",
        columns=[
            ("ID", {"style": "dim", "max_width": 12}),
            ("Name", {"style": "bold"}),
            ("Docs", {"justify": "right"}),
            ("Words", {"justify": "right"}),
            ("Embedding", {}),
        ],
        row_extractor=lambda ds: (
            ds.get("id", "")[:12],
            ds.get("name", "-"),
            str(ds.get("document_count", 0)),
            str(ds.get("word_count", 0)),
            ds.get("embedding_model", "-"),
        ),
    )


kb_list.help = build_help_text(
    "List knowledge bases.",
    "List all knowledge bases in the Dify instance.\n"
    "Input: authentication credentials.\n"
    "Output: table with ID, Name, Docs, Words, Embedding model.",
    examples=[
        "$ dify-admin kb list\n  → display knowledge bases as a table",
        "$ dify-admin --json kb list\n  → output as JSON array",
    ],
    idempotent="yes",
    json_output_keys=["id", "name", "document_count", "word_count"],
)


@kb.command("create")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option("--name", required=True, help="Knowledge base name")
@click.option("--description", default="")
@click.pass_context
def kb_create(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    name: str,
    description: str,
) -> None:
    """Create a knowledge base."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        result = client.kb_create(name=name, description=description)
    output_result(
        ctx,
        result,
        f"[green]Created KB:[/green] {result.get('id', 'unknown')}\n  Name: {result.get('name')}",
    )


kb_create.help = build_help_text(
    "Create a knowledge base.",
    "Create a new empty knowledge base in Dify.\n"
    "Input: --name (required) and optional --description.\n"
    "Output: created KB details with ID and name.",
    examples=[
        '$ dify-admin kb create --name "Company Docs"\n  → create a new knowledge base',
    ],
    side_effects="A new knowledge base is created.",
    idempotent="no",
    json_output_keys=["id", "name"],
)


@kb.command("upload")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.argument("path", type=click.Path())
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.option("--pattern", default="*.md", help="File glob pattern")
@click.option("--chunk-size", default=None, type=int, help="Max tokens per chunk")
@click.option("--chunk-overlap", default=None, type=int, help="Overlap tokens")
@click.option("--separator", default=None, help="Custom separator")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="List matching files without uploading",
)
@click.pass_context
def kb_upload(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    path: str,
    kb_name: Optional[str],
    pattern: str,
    chunk_size: Optional[int],
    chunk_overlap: Optional[int],
    separator: Optional[str],
    dry_run: bool,
) -> None:
    """Upload files to a knowledge base.

    PATH can be a single file or a directory (with --pattern).
    """
    email, password = _resolve_credentials(email, password)
    p = Path(path)

    if not p.is_file() and not p.is_dir():
        output_error(f"[red]Error:[/red] Path is not a file or directory: {path}")
        raise SystemExit(1)

    upload_kwargs = {
        k: v
        for k, v in [
            ("chunk_size", chunk_size),
            ("chunk_overlap", chunk_overlap),
            ("separator", separator),
        ]
        if v is not None
    }

    if dry_run:
        if p.is_file():
            matched = [p]
        else:
            matched = sorted(p.glob(pattern))
        with _make_client(ctx.obj["url"], email, password) as client:
            resolved_ds = _resolve_dataset_id(client, dataset_id, kb_name)
        if get_json_mode(ctx):
            output_json(
                {
                    "dry_run": True,
                    "dataset_id": resolved_ds,
                    "files": [str(x) for x in matched],
                }
            )
        else:
            console = get_console(ctx)
            console.print(
                f"[bold]Dry-run:[/bold] Would upload {len(matched)} file(s) to {resolved_ds}"
            )
            for f in matched:
                console.print(f"  [dim]{f}[/dim]")
        return

    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        console = get_console(ctx)
        if p.is_file():
            client.kb_upload_file(dataset_id, p, **upload_kwargs)
            output_message(
                ctx,
                {"uploaded": 1, "failed": 0, "total": 1, "failed_files": []},
                f"[green]Uploaded:[/green] {p.name}",
            )
        else:
            with console.status("Uploading..."):
                result = client.kb_upload_dir(dataset_id, p, pattern)
            output_message(
                ctx,
                result,
                f"[green]Done:[/green] {result['uploaded']}/{result['total']} uploaded, "
                f"{result['failed']} failed",
            )


kb_upload.help = build_help_text(
    "Upload files to a knowledge base.",
    "Upload a single file or directory of files to a KB.\n"
    "Input: DATASET_ID or --name, plus PATH (file or directory).\n"
    "Output: upload result with count of uploaded/failed files.",
    examples=[
        '$ dify-admin kb upload DATASET_ID ./docs/ --pattern "*.md"\n'
        "  → upload all Markdown files from directory",
        '$ dify-admin kb upload --name "Docs" ./file.pdf\n  → upload a single file by KB name',
        "$ dify-admin kb upload DATASET_ID ./docs/ --dry-run\n"
        "  → list files that would be uploaded",
    ],
    side_effects="Documents are uploaded and indexed in the KB.",
    idempotent="no",
    supports_dry_run=True,
)


@kb.group("docs")
def kb_docs() -> None:
    """Manage documents in a knowledge base."""


@kb_docs.command("list")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.pass_context
def kb_docs_list(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    kb_name: Optional[str],
) -> None:
    """List documents in a knowledge base."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        docs = client.kb_documents(dataset_id)

    output_table(
        ctx,
        docs,
        title="Documents",
        columns=[
            ("ID", {"style": "dim", "max_width": 12}),
            ("Name", {"style": "bold"}),
            ("Status", {}),
            ("Words", {"justify": "right"}),
            ("Created", {}),
        ],
        row_extractor=lambda doc: (
            doc.get("id", "")[:12],
            doc.get("name", "-"),
            doc.get("indexing_status", "-"),
            str(doc.get("word_count", 0)),
            str(doc.get("created_at", "")),
        ),
    )


kb_docs_list.help = build_help_text(
    "List documents in a knowledge base.",
    "List all documents with indexing status and metadata.\n"
    "Input: DATASET_ID or --name for KB resolution.\n"
    "Output: table with ID, Name, Status, Words, Created.\n"
    "Returns DOC_ID values for use with kb docs list subcommands.",
    examples=[
        "$ dify-admin kb docs list DATASET_ID\n  → display documents as a table",
        '$ dify-admin kb docs list --name "Company Docs"\n'
        "  → resolve KB by name and list documents",
    ],
    idempotent="yes",
    json_output_keys=["id", "name", "indexing_status", "word_count"],
)


@kb_docs.command("status")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.argument("doc_id")
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.pass_context
def kb_docs_status(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    doc_id: str,
    kb_name: Optional[str],
) -> None:
    """Get indexing status of a document."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        result = client.kb_document_status(dataset_id, doc_id)
    output_syntax(ctx, result)


kb_docs_status.help = build_help_text(
    "Get indexing status of a document.",
    "Retrieve the current indexing status and progress.\n"
    "Input: DATASET_ID (or --name) and DOC_ID.\n"
    "Output: JSON with indexing_status, timestamps, segments.\n"
    "Use 'kb docs list' to find document IDs.",
    examples=[
        "$ dify-admin kb docs status DATASET_ID DOC_ID\n"
        "  → show indexing status as syntax-highlighted JSON",
        '$ dify-admin kb docs status --name "Docs" DOC_ID\n  → resolve KB by name',
    ],
    idempotent="yes",
    json_output_keys=["indexing_status", "completed_segments", "total_segments"],
)


@kb_docs.command("reindex")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.argument("doc_id")
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.pass_context
def kb_docs_reindex(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    doc_id: str,
    kb_name: Optional[str],
) -> None:
    """Trigger re-indexing of a document."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        result = client.kb_document_reindex(dataset_id, doc_id)
    output_result(
        ctx,
        result,
        f"[green]Reindex triggered:[/green] {doc_id}",
    )


kb_docs_reindex.help = build_help_text(
    "Trigger re-indexing of a document.",
    "Re-index a document to refresh its vector embeddings.\n"
    "Input: DATASET_ID (or --name) and DOC_ID.\n"
    "Output: confirmation of reindex trigger.\n"
    "Use 'kb docs list' to find document IDs.",
    examples=[
        "$ dify-admin kb docs reindex DATASET_ID DOC_ID\n  → trigger re-indexing",
        '$ dify-admin kb docs reindex --name "Docs" DOC_ID\n  → resolve KB by name and reindex',
    ],
    side_effects=(
        "The document is queued for re-indexing.\n"
        "Existing index remains until new indexing completes."
    ),
    idempotent="conditional",
)


@kb_docs.command("delete")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.argument("doc_id")
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be deleted")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def kb_docs_delete(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    doc_id: str,
    kb_name: Optional[str],
    dry_run: bool,
    yes: bool,
) -> None:
    """Delete a document from a knowledge base."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        if dry_run:
            output_message(
                ctx,
                {"would_delete": doc_id, "dataset_id": dataset_id},
                f"[yellow]Would delete document:[/yellow] {doc_id}",
            )
            return
        if not confirm_destructive(ctx, f"Delete document {doc_id}?", yes=yes):
            return
        client.kb_delete_document(dataset_id, doc_id)
    output_message(
        ctx,
        {"deleted": doc_id, "dataset_id": dataset_id},
        f"[green]Deleted document:[/green] {doc_id}",
    )


kb_docs_delete.help = build_help_text(
    "Delete a document from a knowledge base.",
    "Permanently remove a single document and its index.\n"
    "Input: DATASET_ID (or --name) and DOC_ID.\n"
    "Output: confirmation of deletion.\n"
    "Use 'kb docs list' to find document IDs.",
    examples=[
        "$ dify-admin kb docs delete DATASET_ID DOC_ID --dry-run\n"
        "  → preview what would be deleted",
        '$ dify-admin kb docs delete --name "Docs" DOC_ID --yes\n  → delete without confirmation',
    ],
    side_effects=("The document and its index are permanently removed.\nThis cannot be undone."),
    idempotent="no",
    supports_dry_run=True,
)


@kb.command("clear")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be deleted")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def kb_clear(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    kb_name: Optional[str],
    dry_run: bool,
    yes: bool,
) -> None:
    """Delete all documents in a knowledge base."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        if dry_run:
            docs = client.kb_documents(dataset_id)
            output_message(
                ctx,
                {"would_delete_count": len(docs), "dataset_id": dataset_id},
                f"[yellow]Would delete {len(docs)} documents[/yellow]",
            )
            return
        if not confirm_destructive(ctx, "Delete ALL documents in this knowledge base?", yes=yes):
            return
        console = get_console(ctx)
        with console.status("Deleting documents..."):
            count = client.kb_delete_all_documents(dataset_id)
    output_message(
        ctx,
        {"deleted_count": count},
        f"[green]Deleted {count} documents[/green]",
    )


kb_clear.help = build_help_text(
    "Delete all documents in a knowledge base.",
    "Remove every document from a knowledge base.\n"
    "Input: DATASET_ID or --name for resolution.\n"
    "Output: count of deleted documents.",
    examples=[
        '$ dify-admin kb clear --name "Old Docs" --dry-run\n'
        "  → preview how many documents would be deleted",
        "$ dify-admin kb clear DATASET_ID --yes\n  → delete all documents without confirmation",
    ],
    side_effects=(
        "All documents and their indexes are permanently removed.\nThis cannot be undone."
    ),
    idempotent="no",
    supports_dry_run=True,
)


@kb.command("sync")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("dataset_id", required=False, default=None)
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--name", "kb_name", default=None, help="KB name to resolve")
@click.option("--pattern", default="*.md", help="File glob pattern")
@click.option("--recursive", is_flag=True, default=False, help="Recursively search subdirectories")
@click.option(
    "--delete-missing",
    is_flag=True,
    default=False,
    help="Delete remote documents not found locally",
)
@click.option("--checksum", is_flag=True, default=False, help="Compare checksums to detect changes")
@click.option("--dry-run", is_flag=True, default=False, help="Show plan without executing")
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip confirmation for destructive operations",
)
@click.pass_context
def kb_sync(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    dataset_id: Optional[str],
    path: str,
    kb_name: Optional[str],
    pattern: str,
    recursive: bool,
    delete_missing: bool,
    checksum: bool,
    dry_run: bool,
    yes: bool,
) -> None:
    """Sync local files to a knowledge base.

    Uploads new files and optionally deletes remote documents not found locally.
    """
    email, password = _resolve_credentials(email, password)
    local_path = Path(path)

    with _make_client(ctx.obj["url"], email, password) as client:
        dataset_id = _resolve_dataset_id(client, dataset_id, kb_name)
        console = get_console(ctx)

        with console.status("Computing sync plan..."):
            plan = compute_sync_plan(
                client,
                dataset_id,
                local_path,
                pattern,
                recursive,
                delete_missing,
                checksum,
            )

        plan_data = {
            "to_upload": [str(f) for f in plan.to_upload],
            "to_update": [str(f) for f in plan.to_update],
            "to_delete": [d.get("name", "?") for d in plan.to_delete],
            "unchanged": plan.unchanged,
            "skipped": plan.skipped,
        }

        if dry_run:
            if get_json_mode(ctx):
                output_json(plan_data)
            else:
                console.print(f"[bold]Sync plan for dataset {dataset_id}:[/bold]")
                console.print(f"  Upload:    {len(plan.to_upload)} files")
                console.print(f"  Update:    {len(plan.to_update)} files")
                console.print(f"  Delete:    {len(plan.to_delete)} documents")
                console.print(f"  Unchanged: {len(plan.unchanged)} documents")
                console.print(f"  Skipped:   {len(plan.skipped)} (checksum match)")
                if plan.to_upload:
                    console.print("\n[green]Files to upload:[/green]")
                    for f in plan.to_upload:
                        console.print(f"  + {f.name}")
                if plan.to_update:
                    console.print("\n[yellow]Files to update:[/yellow]")
                    for f in plan.to_update:
                        console.print(f"  ~ {f.name}")
                if plan.to_delete:
                    console.print("\n[red]Documents to delete:[/red]")
                    for d in plan.to_delete:
                        console.print(f"  - {d.get('name', '?')}")
            return

        if plan.to_delete and not confirm_destructive(
            ctx,
            f"Delete {len(plan.to_delete)} remote documents not found locally?",
            yes=yes,
        ):
            plan.to_delete.clear()

        with console.status("Syncing..."):
            result = execute_sync(client, dataset_id, plan)

    output_message(
        ctx,
        result,
        f"[green]Sync complete:[/green] {result['uploaded']} uploaded, "
        f"{result.get('updated', 0)} updated, "
        f"{result['deleted']} deleted, {result['unchanged']} unchanged, "
        f"{result.get('skipped', 0)} skipped, {result['failed']} failed",
    )


kb_sync.help = build_help_text(
    "Sync local files to a knowledge base.",
    "Compare local files with remote documents and sync changes.\n"
    "Input: DATASET_ID or --name, plus PATH (local directory).\n"
    "Output: sync result with upload/delete/unchanged counts.",
    examples=[
        '$ dify-admin kb sync --name "Docs" ./files/ --dry-run\n'
        "  → preview sync plan without executing",
        "$ dify-admin kb sync DATASET_ID ./files/ --checksum\n"
        "  → sync with checksum-based change detection",
        "$ dify-admin kb sync DATASET_ID ./files/ --delete-missing --yes\n"
        "  → sync and delete remote-only documents",
    ],
    side_effects=(
        "New files are uploaded, changed files are updated.\n"
        "With --delete-missing, remote-only documents are deleted."
    ),
    idempotent="conditional",
    supports_dry_run=True,
)


# ── Password Reset ──────────────────────────────────────────


@main.command("reset-password")
@click.option("--email", required=True, help="Account email")
@click.option("--new-password", required=True, help="New password")
@click.option("--container", default="dify-db", help="Docker container name")
@click.pass_context
def reset_password(ctx: click.Context, email: str, new_password: str, container: str) -> None:
    """Reset account password via direct database access."""
    if reset_via_docker(email, new_password, container_name=container):
        output_message(
            ctx,
            {"reset": True, "email": email},
            f"[green]Password reset for {email}[/green]",
        )
    else:
        output_error("[red]Password reset failed[/red]")
        raise SystemExit(1)


reset_password.help = build_help_text(
    summary="Reset account password via direct database access.",
    description=(
        "Change a Dify account password by executing SQL directly in the PostgreSQL container.\n"
        "Input: --email for the target account, --new-password for the replacement value.\n"
        "Output: success or failure message. Requires Docker access to the database container."
    ),
    examples=[
        "$ dify-admin reset-password --email admin@example.com --new-password newpass123",
        "$ dify-admin reset-password --email x --new-password y --container my-db",
    ],
    side_effects=(
        "Password is changed directly in PostgreSQL.\n"
        "This is a DB-level operation, not a Dify API call."
    ),
    idempotent="conditional",
)


# ── Status ──────────────────────────────────────────────────


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check Dify server status."""
    with DifyClient(ctx.obj["url"]) as client:
        try:
            setup = client.setup_status()
        except Exception as e:
            output_error(f"[red]Cannot connect to Dify:[/red] {e}")
            raise SystemExit(1)
    data = {
        "status": "running",
        "step": setup.get("step", "unknown"),
        "url": ctx.obj["url"],
    }
    if get_json_mode(ctx):
        output_json(data)
    else:
        console = get_console(ctx)
        console.print("[green]Dify is running[/green]")
        console.print(f"  Setup: {setup.get('step', 'unknown')}")
        console.print(f"  URL:   {ctx.obj['url']}")


status.help = build_help_text(
    summary="Check Dify server status.",
    description=(
        "Query the Dify server's setup endpoint to verify it is running and reachable.\n"
        "Input: no authentication required; uses the configured --url.\n"
        "Output: server status, setup step, and URL."
    ),
    examples=[
        "$ dify-admin status",
        "$ dify-admin --url http://dify.example.com:5001 status",
        "$ dify-admin --json status",
    ],
    idempotent="yes",
    json_output_keys=["status", "step", "url"],
)


# ── Snapshots ──────────────────────────────────────────────


@apps.command("snapshot")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.pass_context
def apps_snapshot(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
) -> None:
    """Take a snapshot of an app's current state."""
    from dify_admin.snapshot import take_snapshot

    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = take_snapshot(client, app_id)
    output_result(
        ctx,
        result,
        f"[green]Snapshot taken:[/green] {result['snapshot_id']}\n  App: {result['app_name']}",
    )


@apps.command("snapshots")
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.pass_context
def apps_snapshots(
    ctx: click.Context,
    app_id: Optional[str],
    app_name: Optional[str],
    email: Optional[str],
    password: Optional[str],
) -> None:
    """List snapshots for an app."""
    from dify_admin.snapshot import list_snapshots

    if app_name:
        email, password = _resolve_credentials(email, password)
        with _make_client(ctx.obj["url"], email, password) as client:
            app_id = _resolve_app_id(client, app_id, app_name)
    if not app_id:
        raise click.UsageError("Specify APP_ID or --name.")

    snapshots = list_snapshots(app_id)
    output_table(
        ctx,
        snapshots,
        title="Snapshots",
        columns=[
            ("ID", {"style": "bold"}),
            ("App Name", {}),
            ("Time", {}),
        ],
        row_extractor=lambda s: (
            s.get("snapshot_id", ""),
            s.get("app_name", ""),
            s.get("iso_time", ""),
        ),
    )


@apps.command("restore")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id")
@click.argument("snapshot_id")
@click.option("--yes", is_flag=True, default=False)
@click.pass_context
def apps_restore(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: str,
    snapshot_id: str,
    yes: bool,
) -> None:
    """Restore an app from a snapshot.

    Restore an app's configuration to a previously saved snapshot state.
    Reads the snapshot file from the local snapshots directory and applies
    the saved DSL configuration to the target app via import.

    Use 'dify-admin apps snapshots <app_id>' to list available snapshots.

    Examples:
      $ dify-admin apps restore <app_id> <snapshot_id> --yes

    Side Effects:
      Overwrites the app's current configuration with the snapshot state.
      The previous state is not automatically saved — take a snapshot first.

    JSON Output Keys: app_name, snapshot_id, status

    Idempotent: conditional"""
    from dify_admin.snapshot import restore_snapshot

    if not confirm_destructive(ctx, f"Restore app {app_id} from {snapshot_id}?", yes=yes):
        return

    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        result = restore_snapshot(client, app_id, snapshot_id)
    output_result(
        ctx,
        result,
        f"[green]Restored:[/green] {result['app_name']} from {snapshot_id}",
    )


# ── Env Diff ───────────────────────────────────────────────


@main.command("env-diff")
@click.option("--source-url", required=True, help="Source Dify URL")
@click.option("--target-url", required=True, help="Target Dify URL")
@click.option("--source-email", default=None, help="Source email (env: DIFY_EMAIL)")
@click.option("--source-password", default=None, help="Source password (env: DIFY_PASSWORD)")
@click.option("--target-email", default=None, help="Target email (defaults to source)")
@click.option("--target-password", default=None, help="Target password (defaults to source)")
@click.pass_context
def env_diff(
    ctx: click.Context,
    source_url: str,
    target_url: str,
    source_email: Optional[str],
    source_password: Optional[str],
    target_email: Optional[str],
    target_password: Optional[str],
) -> None:
    """Compare two Dify environments."""
    from dify_admin.env_diff import compare_environments

    s_email, s_password = _resolve_credentials(source_email, source_password)
    t_email = target_email or s_email
    t_password = target_password or s_password

    with _make_client(source_url, s_email, s_password) as source:
        with _make_client(target_url, t_email, t_password) as target:
            result = compare_environments(source, target)

    if get_json_mode(ctx):
        output_json(result)
        return

    console = get_console(ctx)
    s = result["summary"]
    console.print(f"[bold]Env diff: {source_url} vs {target_url}[/bold]\n")

    console.print("[bold]Apps:[/bold]")
    console.print(f"  Source only: {s['apps_source_only']}")
    console.print(f"  Target only: {s['apps_target_only']}")
    console.print(f"  Common:      {s['apps_common']}")

    if result["apps"]["source_only"]:
        console.print("\n  [green]Source only:[/green]")
        for a in result["apps"]["source_only"]:
            console.print(f"    + {a['name']} ({a.get('mode', '')})")
    if result["apps"]["target_only"]:
        console.print("\n  [red]Target only:[/red]")
        for a in result["apps"]["target_only"]:
            console.print(f"    - {a['name']} ({a.get('mode', '')})")

    console.print("\n[bold]Knowledge Bases:[/bold]")
    console.print(f"  Source only: {s['kb_source_only']}")
    console.print(f"  Target only: {s['kb_target_only']}")
    console.print(f"  Common:      {s['kb_common']}")


env_diff.help = build_help_text(
    summary="Compare two Dify environments.",
    description=(
        "Connect to two Dify instances and compare their apps and knowledge bases.\n"
        "Input: --source-url and --target-url for the two environments, plus credentials.\n"
        "Output: side-by-side summary of resources unique to each\n"
        "environment and those in common."
    ),
    examples=[
        "$ dify-admin env-diff --source-url http://dev:5001 --target-url http://prod:5001",
        "$ dify-admin --json env-diff --source-url http://dev:5001 --target-url http://prod:5001",
    ],
    idempotent="yes",
    json_output_keys=["summary", "apps", "knowledge_bases"],
)


# ── Audit Log ──────────────────────────────────────────────


@main.group("audit")
def audit() -> None:
    """View operation audit log."""


@audit.command("list")
@click.option("--limit", default=20, help="Number of entries to show")
@click.pass_context
def audit_list(ctx: click.Context, limit: int) -> None:
    """Show recent audit log entries."""
    from dify_admin.audit import get_recent

    entries = get_recent(limit)
    if get_json_mode(ctx):
        output_json(entries)
        return

    console = get_console(ctx)
    if not entries:
        console.print("[dim]No audit log entries.[/dim]")
        return

    for e in entries:
        t = e.get("iso_time", "?")
        op = e.get("operation", "?")
        rtype = e.get("resource_type", "?")
        rname = e.get("resource_name", "") or e.get("resource_id", "?")
        console.print(f"  {t}  {op:10s} {rtype:5s}  {rname}")


audit_list.help = build_help_text(
    "Show recent audit log entries.",
    "Display the most recent DESTRUCTIVE operations recorded.\n"
    "Input: optional --limit to control number of entries.\n"
    "Output: list of operations with timestamp, type, and resource.",
    examples=[
        "$ dify-admin audit list\n  → show last 20 entries",
        "$ dify-admin audit list --limit 50\n  → show last 50 entries",
    ],
    idempotent="yes",
    json_output_keys=["timestamp", "operation", "resource_type", "resource_id"],
)


@audit.command("clear")
@click.option("--yes", is_flag=True, default=False)
@click.pass_context
def audit_clear(ctx: click.Context, yes: bool) -> None:
    """Clear the audit log."""
    from dify_admin.audit import clear_log

    if not confirm_destructive(ctx, "Clear audit log?", yes=yes):
        return
    count = clear_log()
    output_message(ctx, {"cleared": count}, f"[green]Cleared {count} entries[/green]")


audit_clear.help = build_help_text(
    "Clear the audit log.",
    "Delete all entries from the local audit log file.\n"
    "Input: --yes to skip confirmation prompt.\n"
    "Output: count of cleared entries.",
    examples=[
        "$ dify-admin audit clear --yes\n  → clear all entries without confirmation",
    ],
    side_effects="All audit log entries are permanently deleted.",
    idempotent="no",
)


# ── State Management ───────────────────────────────────────


@main.command("plan")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("state_file", type=str)
@click.option(
    "--delete-missing",
    is_flag=True,
    default=False,
    help="Plan deletion of resources not in state file",
)
@click.pass_context
def state_plan(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    state_file: str,
    delete_missing: bool,
) -> None:
    """Show what changes would be made to reach desired state."""
    from dify_admin.state import compute_plan, load_state_file, load_state_yaml

    email, password = _resolve_credentials(email, password)
    if state_file == "-":
        desired = load_state_yaml(_read_input("-"))
    else:
        path = Path(state_file)
        if not path.is_file():
            raise click.BadParameter(
                f"File not found or not a file: {state_file}",
                param_hint="STATE_FILE",
            )
        desired = load_state_file(path)

    with _make_client(ctx.obj["url"], email, password) as client:
        plan = compute_plan(client, desired, delete_missing=delete_missing)

    if get_json_mode(ctx):
        output_json(
            [
                {
                    "action": a.action,
                    "type": a.resource_type,
                    "name": a.name,
                    "details": a.details,
                }
                for a in plan.actions
            ]
        )
        return

    console = get_console(ctx)
    summary = plan.summary
    if not plan.actions:
        console.print("[green]No changes needed. State is up to date.[/green]")
        return

    console.print("[bold]Plan:[/bold]")
    for a in plan.actions:
        if a.action == "create":
            console.print(f"  [green]+ {a.resource_type}:[/green] {a.name}")
        elif a.action == "update":
            changes = a.details.get("changes", {})
            console.print(f"  [yellow]~ {a.resource_type}:[/yellow] {a.name} ({changes})")
        elif a.action == "delete":
            console.print(f"  [red]- {a.resource_type}:[/red] {a.name}")
    console.print(
        f"\n  {summary['create']} to create, "
        f"{summary['update']} to update, "
        f"{summary['delete']} to delete"
    )


state_plan.help = build_help_text(
    summary="Show what changes would be made to reach desired state.",
    description=(
        "Load a YAML state file and compare it against the live Dify environment.\n"
        "Input: a state YAML file path, optional --delete-missing to include deletions.\n"
        "Output: a plan listing resources to create, update,\n"
        "or delete without applying any changes."
    ),
    examples=[
        "$ dify-admin plan state.yml",
        "$ dify-admin plan state.yml --delete-missing",
        "$ dify-admin --json plan state.yml",
    ],
    idempotent="yes",
    json_output_keys=["action", "type", "name", "details"],
)


@main.command("apply")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("state_file", type=str)
@click.option(
    "--delete-missing",
    is_flag=True,
    default=False,
    help="Delete resources not in state file",
)
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation")
@click.pass_context
def state_apply(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    state_file: str,
    delete_missing: bool,
    yes: bool,
) -> None:
    """Apply desired state from a YAML file."""
    from dify_admin.state import compute_plan, execute_plan, load_state_file, load_state_yaml

    email, password = _resolve_credentials(email, password)
    if state_file == "-":
        desired = load_state_yaml(_read_input("-"))
    else:
        path = Path(state_file)
        if not path.is_file():
            raise click.BadParameter(
                f"File not found or not a file: {state_file}",
                param_hint="STATE_FILE",
            )
        desired = load_state_file(path)

    with _make_client(ctx.obj["url"], email, password) as client:
        plan = compute_plan(client, desired, delete_missing=delete_missing)

        if not plan.actions:
            output_message(
                ctx,
                {"status": "no_changes"},
                "[green]No changes needed. State is up to date.[/green]",
            )
            return

        if not confirm_destructive(ctx, f"Apply {len(plan.actions)} changes?", yes=yes):
            return

        results = execute_plan(client, plan)

    if get_json_mode(ctx):
        output_json(results)
        return

    console = get_console(ctx)
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if r["status"] == "error")
    console.print(f"[green]Applied: {ok} succeeded, {errors} failed[/green]")
    for r in results:
        if r["status"] == "error":
            console.print(f"  [red]✗ {r['action']} {r['name']}: {r['error']}[/red]")


state_apply.help = build_help_text(
    summary="Apply desired state from a YAML file.",
    description=(
        "Load a YAML state file, compute a plan, and execute\n"
        "all changes against the live Dify environment.\n"
        "Input: a state YAML file path, optional --delete-missing and --yes flags.\n"
        "Output: summary of applied changes with success/failure counts per action."
    ),
    examples=[
        "$ dify-admin apply state.yml --yes",
        "$ dify-admin apply state.yml --delete-missing --yes",
        "$ dify-admin --json apply state.yml --yes",
    ],
    side_effects=(
        "Apps and KBs are created, updated, or deleted to match YAML.\n"
        "With --delete-missing, resources not in YAML are removed."
    ),
    idempotent="conditional",
)


# ── Doctor ──────────────────────────────────────────────────


@main.command()
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.pass_context
def doctor(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
) -> None:
    """Run diagnostic checks on Dify connectivity and auth."""
    from dify_admin.doctor import run_checks

    resolved_email = email or os.environ.get("DIFY_EMAIL")
    resolved_password = password or os.environ.get("DIFY_PASSWORD")
    results = run_checks(ctx.obj["url"], resolved_email, resolved_password)

    if get_json_mode(ctx):
        output_json(results)
        return

    console = get_console(ctx)
    status_icons = {
        "pass": "[green]✓[/green]",
        "fail": "[red]✗[/red]",
        "warn": "[yellow]![/yellow]",
        "skip": "[dim]-[/dim]",
    }
    console.print("[bold]dify-admin doctor[/bold]\n")
    for check in results:
        icon = status_icons.get(check["status"], "?")
        console.print(f"  {icon} {check['name']}: {check['message']}")

    failed = sum(1 for c in results if c["status"] == "fail")
    if failed:
        console.print(f"\n[red]{failed} check(s) failed[/red]")
        raise SystemExit(1)
    else:
        console.print("\n[green]All checks passed[/green]")


doctor.help = build_help_text(
    summary="Run diagnostic checks on Dify connectivity and auth.",
    description=(
        "Execute a series of health checks against the Dify server.\n"
        "Input: optional --email and --password to include authentication checks.\n"
        "Output: pass/fail/warn/skip status for each check (connectivity, auth, API version, etc.)."
    ),
    examples=[
        "$ dify-admin doctor",
        "$ dify-admin doctor --email admin@example.com --password secret",
        "$ dify-admin --json doctor",
    ],
    idempotent="yes",
    json_output_keys=["name", "status", "message"],
)


# ── MCP Server ─────────────────────────────────────────────


@main.group()
def mcp() -> None:
    """MCP (Model Context Protocol) server."""


@mcp.command("serve")
@click.pass_context
def mcp_serve(ctx: click.Context) -> None:
    """Start the MCP server for AI assistant integration.

    Requires DIFY_EMAIL and DIFY_PASSWORD environment variables.
    DIFY_URL defaults to http://localhost:5001.
    """
    from dify_admin.mcp_server import main as run_mcp

    run_mcp()


mcp_serve.help = build_help_text(
    summary="Start the MCP server for AI assistant integration.",
    description=(
        "Launch a Model Context Protocol (MCP) server that exposes Dify operations as tools.\n"
        "Input: requires DIFY_EMAIL and DIFY_PASSWORD environment variables to be set.\n"
        "Output: runs a persistent stdio-based MCP server for AI assistants like Claude Code."
    ),
    examples=[
        "$ dify-admin mcp serve",
        "$ DIFY_URL=http://dify:5001 dify-admin mcp serve",
    ],
    idempotent="yes",
)


if __name__ == "__main__":
    main()
