"""dify-admin CLI — manage Dify from the command line."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import click

from dify_admin.auth import AuthenticationError
from dify_admin.client import DifyClient
from dify_admin.diff import diff_configs, format_diff_table
from dify_admin.env import load_dotenv
from dify_admin.exceptions import DifyAdminError
from dify_admin.output import (
    confirm_destructive,
    get_console,
    get_json_mode,
    output_error,
    output_json,
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
        except (NameNotFoundError, AmbiguousNameError) as e:
            output_error(f"[red]{e}[/red]")
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
        except (NameNotFoundError, AmbiguousNameError) as e:
            output_error(f"[red]{e}[/red]")
            raise SystemExit(1)
        return ds["id"]
    if not dataset_id:
        raise click.UsageError("Specify DATASET_ID or --name.")
    return dataset_id


class DifyAdminGroup(click.Group):
    """Click group with DifyAdminError handling."""

    def invoke(self, ctx: click.Context) -> Any:
        """Invoke with error handling for DifyAdminError."""
        try:
            return super().invoke(ctx)
        except DifyAdminError as e:
            output_error(f"[red]{e}[/red]")
            raise SystemExit(1)


@click.group(cls=DifyAdminGroup)
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


# ── Apps ────────────────────────────────────────────────────


@main.group()
def apps() -> None:
    """Manage Dify apps."""


@apps.command("list")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.pass_context
def apps_list(ctx: click.Context, email: Optional[str], password: Optional[str]) -> None:
    """List all apps."""
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
    """Create a new app."""
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


@apps.command("rename")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="Current app name to resolve")
@click.option("--new-name", required=True, help="New app name")
@click.option("--description", default=None, help="New description")
@click.pass_context
def apps_rename(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    new_name: str,
    description: Optional[str],
) -> None:
    """Rename an app."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_rename(app_id, new_name, description=description)
    output_result(
        ctx,
        result,
        f"[green]Renamed app:[/green] {app_id}\n  New name: {new_name}",
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
    """Search apps by name."""
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
    """Delete an app."""
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
    """Get app details."""
    email, password = _resolve_credentials(email, password)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_get(app_id)
    output_syntax(ctx, result)


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
    """Export app as DSL YAML."""
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


@apps.command("import")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.option(
    "--file",
    "import_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="YAML file to import",
)
@click.option("--name", "app_name", default=None, help="Override app name")
@click.pass_context
def apps_import_cmd(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    import_file: str,
    app_name: Optional[str],
) -> None:
    """Import app from DSL YAML file."""
    email, password = _resolve_credentials(email, password)
    yaml_data = Path(import_file).read_text(encoding="utf-8")
    with _make_client(ctx.obj["url"], email, password) as client:
        result = client.apps_import(yaml_data, name=app_name)
    output_result(
        ctx,
        result,
        f"[green]Imported app:[/green] {result.get('id', 'unknown')}\n"
        f"  Name: {result.get('name', '-')}",
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
    """Create an app from a template.

    Templates: chat-basic, chat-rag, completion, workflow, agent
    """
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


@apps.command("templates")
@click.pass_context
def apps_templates(ctx: click.Context) -> None:
    """List available app templates."""
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
    """Clone an app (export + import)."""
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
    """Compare two apps' configurations."""
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


@apps.command("dsl-diff")
@click.argument("left_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("right_file", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def apps_dsl_diff(
    ctx: click.Context,
    left_file: str,
    right_file: str,
) -> None:
    """Compare two DSL YAML files."""
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


@apps_config.command("set")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("app_id", required=False, default=None)
@click.option("--name", "app_name", default=None, help="App name to resolve")
@click.option(
    "--file",
    "config_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSON config file",
)
@click.pass_context
def apps_config_set(
    ctx: click.Context,
    email: Optional[str],
    password: Optional[str],
    app_id: Optional[str],
    app_name: Optional[str],
    config_file: str,
) -> None:
    """Update app model configuration from a JSON file."""
    email, password = _resolve_credentials(email, password)
    try:
        raw = Path(config_file).read_text(encoding="utf-8")
    except (PermissionError, UnicodeDecodeError) as e:
        output_error(f"[red]Cannot read {config_file}:[/red] {e}")
        raise SystemExit(1)
    try:
        config_data = json.loads(raw)
    except json.JSONDecodeError as e:
        output_error(f"[red]Invalid JSON in {config_file}:[/red] {e}")
        raise SystemExit(1)
    if not isinstance(config_data, dict):
        output_error(f"[red]Config must be a JSON object, got {type(config_data).__name__}[/red]")
        raise SystemExit(1)
    with _make_client(ctx.obj["url"], email, password) as client:
        app_id = _resolve_app_id(client, app_id, app_name)
        result = client.apps_update_config(app_id, config_data)
    output_result(
        ctx,
        result,
        f"[green]Updated config for app:[/green] {app_id}",
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
    """Restore an app from a snapshot."""
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


# ── State Management ───────────────────────────────────────


@main.command("plan")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("state_file", type=click.Path(exists=True, dir_okay=False))
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
    from dify_admin.state import compute_plan, load_state_file

    email, password = _resolve_credentials(email, password)
    desired = load_state_file(Path(state_file))

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


@main.command("apply")
@click.option("--email", default=None)
@click.option("--password", default=None)
@click.argument("state_file", type=click.Path(exists=True, dir_okay=False))
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
    from dify_admin.state import compute_plan, execute_plan, load_state_file

    email, password = _resolve_credentials(email, password)
    desired = load_state_file(Path(state_file))

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


if __name__ == "__main__":
    main()
