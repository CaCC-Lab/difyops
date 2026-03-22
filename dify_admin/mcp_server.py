"""MCP server for dify-admin.

Exposes Dify management operations as MCP tools.
State-changing tools are marked with DESTRUCTIVE: in their docstrings
and blocked when DIFY_ADMIN_MODE=readonly is set.

Usage:
    dify-admin mcp serve
    # or directly:
    python -m dify_admin.mcp_server
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from dify_admin.audit import record as _audit_record
from dify_admin.client import DifyClient
from dify_admin.diff import diff_configs, diff_dsl
from dify_admin.env import load_dotenv
from dify_admin.patch import apply_patches, get_nested
from dify_admin.resolve import (
    resolve_app_by_name,
    resolve_kb_by_name,
)
from dify_admin.sync import compute_sync_plan, execute_sync

mcp = FastMCP(
    "difyops",
    instructions="Manage Dify apps and knowledge bases via MCP tools. "
    "Read-only tools (safe to call without confirmation): "
    "apps_list, apps_get, apps_config_get, apps_config_get_key, "
    "apps_export, apps_search, apps_templates, apps_diff, "
    "apps_snapshot, apps_snapshots, dsl_diff, "
    "kb_list, kb_docs_list, kb_docs_status, kb_sync_dry_run, "
    "state_plan, status, doctor, audit_list, explain, list_operations, env_diff. "
    "State-changing tools (DESTRUCTIVE — confirm with user before calling): "
    "apps_create, apps_delete, apps_rename, apps_clone, apps_scaffold, apps_import, "
    "apps_config_set, apps_config_patch, apps_restore, "
    "kb_create, kb_upload, kb_docs_delete, kb_docs_reindex, kb_clear, kb_sync, "
    "state_apply. "
    "IMPORTANT: Always confirm DESTRUCTIVE operations with the user before executing. "
    "Use 'explain' tool to show risks before destructive operations.",
)


def _check_readonly() -> None:
    """Raise if running in read-only mode."""
    mode = os.environ.get("DIFY_ADMIN_MODE", "").lower()
    if mode == "readonly":
        raise PermissionError(
            "Operation blocked: dify-admin is running in read-only mode. "
            "Unset DIFY_ADMIN_MODE or set it to a value other than 'readonly' to allow changes."
        )


def _get_client() -> DifyClient:
    """Create and authenticate a DifyClient from environment variables.

    Loads .env file on first call.
    Requires DIFY_EMAIL and DIFY_PASSWORD.
    DIFY_URL defaults to http://localhost:5001.
    """
    load_dotenv()
    url = os.environ.get("DIFY_URL", "http://localhost:5001")
    email = os.environ.get("DIFY_EMAIL")
    password = os.environ.get("DIFY_PASSWORD")
    if not email or not password:
        raise ValueError("DIFY_EMAIL and DIFY_PASSWORD environment variables are required")
    client = DifyClient(url)
    client.login(email, password)
    return client


def _resolve_app(client: DifyClient, app_id: str | None, name: str | None) -> str:
    """Resolve app ID from id or name."""
    if app_id and name:
        raise ValueError("Specify either app_id or name, not both.")
    if name:
        app = resolve_app_by_name(client, name)
        return app["id"]
    if not app_id:
        raise ValueError("Specify app_id or name.")
    return app_id


def _resolve_dataset(client: DifyClient, dataset_id: str | None, name: str | None) -> str:
    """Resolve dataset ID from id or name."""
    if dataset_id and name:
        raise ValueError("Specify either dataset_id or name, not both.")
    if name:
        ds = resolve_kb_by_name(client, name)
        return ds["id"]
    if not dataset_id:
        raise ValueError("Specify dataset_id or name.")
    return dataset_id


# ── Read-only tools ──────────────────────────────────────────


@mcp.tool()
def apps_list() -> list[dict[str, Any]]:
    """List all Dify apps.

    Returns a list of apps with id, name, mode, and created_at.
    """
    with _get_client() as client:
        return client.apps_list(fetch_all=True)


@mcp.tool()
def apps_get(app_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Get app details by ID or name.

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        return client.apps_get(resolved_id)


@mcp.tool()
def apps_config_get(app_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Get app model configuration by ID or name.

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        return client.apps_get_config(resolved_id)


@mcp.tool()
def apps_export(app_id: str | None = None, name: str | None = None) -> str:
    """Export app as DSL YAML string.

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)

    Returns:
        YAML string of the app DSL
    """
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        result = client.apps_export(resolved_id)
        return result.get("data", "")


@mcp.tool()
def kb_list() -> list[dict[str, Any]]:
    """List all knowledge bases.

    Returns a list of datasets with id, name, document_count, word_count.
    """
    with _get_client() as client:
        return client.kb_list(fetch_all=True)


@mcp.tool()
def kb_docs_list(dataset_id: str | None = None, name: str | None = None) -> list[dict[str, Any]]:
    """List documents in a knowledge base by ID or name.

    Args:
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
    """
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        return client.kb_documents_all(resolved_id)


@mcp.tool()
def kb_sync_dry_run(
    dataset_id: str | None = None,
    name: str | None = None,
    path: str = ".",
    pattern: str = "*.md",
    recursive: bool = False,
    delete_missing: bool = False,
    checksum: bool = False,
) -> dict[str, Any]:
    """Preview what kb sync would do (dry-run).

    Args:
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
        path: Local directory path
        pattern: File glob pattern
        recursive: Search subdirectories
        delete_missing: Include remote-only documents in delete plan
        checksum: Compare checksums to detect changes
    """
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        plan = compute_sync_plan(
            client, resolved_id, Path(path), pattern, recursive, delete_missing, checksum
        )
        return {
            "to_upload": [str(f) for f in plan.to_upload],
            "to_update": [str(f) for f in plan.to_update],
            "to_delete": [d.get("name", "?") for d in plan.to_delete],
            "unchanged": plan.unchanged,
            "skipped": plan.skipped,
        }


@mcp.tool()
def status() -> dict[str, Any]:
    """Check Dify server status (no auth required)."""
    url = os.environ.get("DIFY_URL", "http://localhost:5001")
    with DifyClient(url) as client:
        setup = client.setup_status()
        return {"status": "running", "step": setup.get("step", "unknown"), "url": url}


@mcp.tool()
def state_plan(
    state_yaml: str,
    delete_missing: bool = False,
) -> list[dict[str, Any]]:
    """Plan changes to reach desired state defined in YAML.

    Args:
        state_yaml: YAML string defining desired state (apps and knowledge_bases)
        delete_missing: If True, plan deletion of resources not in desired state

    Returns:
        List of planned actions (create/update/delete)
    """
    import yaml

    from dify_admin.state import compute_plan

    desired = yaml.safe_load(state_yaml)
    with _get_client() as client:
        plan = compute_plan(client, desired, delete_missing=delete_missing)
        return [
            {
                "action": a.action,
                "type": a.resource_type,
                "name": a.name,
                "details": a.details,
            }
            for a in plan.actions
        ]


@mcp.tool()
def state_apply(
    state_yaml: str,
    delete_missing: bool = False,
) -> list[dict[str, Any]]:
    """DESTRUCTIVE: Apply desired state from YAML. Creates, updates, or deletes resources.

    Args:
        state_yaml: YAML string defining desired state
        delete_missing: If True, delete resources not in desired state
    """
    _check_readonly()
    import yaml

    from dify_admin.state import compute_plan, execute_plan

    desired = yaml.safe_load(state_yaml)
    with _get_client() as client:
        plan = compute_plan(client, desired, delete_missing=delete_missing)
        result = execute_plan(client, plan)
        _audit_record("state_apply", "state", details={"actions": len(plan.actions)})
        return result


@mcp.tool()
def doctor() -> list[dict[str, Any]]:
    """Run diagnostic checks on Dify connectivity, auth, and API access.

    Returns a list of check results (reachability, setup, credentials, auth, api_access).
    Each result has: name, status (pass/fail/warn/skip), message.
    """
    load_dotenv()
    from dify_admin.doctor import run_checks

    return run_checks()


@mcp.tool()
def explain(operation: str) -> dict[str, Any]:
    """Explain what an operation does, what it changes, and how to undo it.

    Args:
        operation: Operation name (e.g. "apps_delete", "kb_sync", "state_apply")
    """
    from dify_admin.explain import explain_operation

    return explain_operation(operation)


@mcp.tool()
def list_operations() -> list[dict[str, Any]]:
    """List all operations with their risk levels and descriptions."""
    from dify_admin.explain import list_operations as _list_ops

    return _list_ops()


@mcp.tool()
def apps_snapshot(app_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Take a snapshot of an app's current state (saves to local disk only).

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    from dify_admin.snapshot import take_snapshot

    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        return take_snapshot(client, resolved_id)


@mcp.tool()
def apps_snapshots(app_id: str) -> list[dict[str, Any]]:
    """List snapshots for an app (newest first).

    Args:
        app_id: App ID
    """
    from dify_admin.snapshot import list_snapshots

    return list_snapshots(app_id)


@mcp.tool()
def apps_restore(app_id: str, snapshot_id: str) -> dict[str, Any]:
    """DESTRUCTIVE: Restore an app from a snapshot. This overwrites current state.

    Args:
        app_id: App ID
        snapshot_id: Snapshot ID to restore
    """
    _check_readonly()
    from dify_admin.snapshot import restore_snapshot

    with _get_client() as client:
        result = restore_snapshot(client, app_id, snapshot_id)
        _audit_record("restore", "app", resource_id=app_id, details={"snapshot_id": snapshot_id})
        return result


@mcp.tool()
def env_diff(
    source_url: str,
    target_url: str,
    source_email: str | None = None,
    source_password: str | None = None,
    target_email: str | None = None,
    target_password: str | None = None,
) -> dict[str, Any]:
    """Compare two Dify environments (apps and knowledge bases).

    Args:
        source_url: Source Dify URL
        target_url: Target Dify URL
        source_email: Source email (defaults to DIFY_EMAIL)
        source_password: Source password (defaults to DIFY_PASSWORD)
        target_email: Target email (defaults to source)
        target_password: Target password (defaults to source)
    """
    from dify_admin.env_diff import compare_environments

    load_dotenv()
    s_email = source_email or os.environ.get("DIFY_EMAIL", "")
    s_password = source_password or os.environ.get("DIFY_PASSWORD", "")
    t_email = target_email or s_email
    t_password = target_password or s_password

    with DifyClient(source_url) as source:
        source.login(s_email, s_password)
        with DifyClient(target_url) as target:
            target.login(t_email, t_password)
            return compare_environments(source, target)


@mcp.tool()
def audit_list(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent audit log entries (newest first).

    Args:
        limit: Maximum entries to return
    """
    from dify_admin.audit import get_recent

    return get_recent(limit)


# ── Destructive tools ────────────────────────────────────────


@mcp.tool()
def apps_scaffold(
    template_id: str,
    name: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Create an app from a template.

    Args:
        template_id: Template ID (chat-basic, chat-rag, completion, workflow, agent)
        name: Override app name (default: template's default name)
    """
    _check_readonly()
    from dify_admin.templates import get_template

    template = get_template(template_id)
    if name:
        template["name"] = name
    with _get_client() as client:
        result = client.apps_create(
            name=template["name"],
            mode=template["mode"],
            description=template.get("description", ""),
        )
        _audit_record("scaffold", "app", resource_name=template["name"])
        return result


@mcp.tool()
def apps_templates() -> list[dict[str, str]]:
    """List available app templates.

    Returns template IDs, names, modes, and descriptions.
    """
    from dify_admin.templates import list_templates

    return list_templates()


@mcp.tool()
def apps_create(
    name: str,
    mode: str = "chat",
    description: str = "",
) -> dict[str, Any]:
    """DESTRUCTIVE: Create a new Dify app.

    Args:
        name: App name
        mode: App mode (chat, completion, advanced-chat, agent-chat, workflow)
        description: App description
    """
    _check_readonly()
    with _get_client() as client:
        result = client.apps_create(name=name, mode=mode, description=description)
        _audit_record("create", "app", resource_name=name)
        return result


@mcp.tool()
def apps_rename(
    new_name: str,
    app_id: str | None = None,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Rename an app and optionally update its description.

    Args:
        new_name: New app name
        app_id: App ID (use this or name)
        name: Current app name for resolution (exact match)
        description: New description (None = keep current)
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        result = client.apps_rename(resolved_id, new_name, description=description)
        _audit_record("rename", "app", resource_id=resolved_id, resource_name=new_name)
        return result


@mcp.tool()
def apps_search(
    query: str,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """Search apps by name (case-insensitive substring match).

    Args:
        query: Search string
        mode: Filter by mode (chat, completion, advanced-chat, workflow)
    """
    with _get_client() as client:
        return client.apps_search(query, mode=mode)


@mcp.tool()
def apps_delete(app_id: str | None = None, name: str | None = None) -> dict[str, str]:
    """DESTRUCTIVE: Delete an app. This cannot be undone.

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        client.apps_delete(resolved_id)
        _audit_record("delete", "app", resource_id=resolved_id, resource_name=name or "")
        return {"deleted": resolved_id}


@mcp.tool()
def apps_config_set(
    config_json: str,
    app_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Update app model configuration. This overwrites the entire config.

    Args:
        config_json: JSON string of the configuration to apply
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    _check_readonly()
    import json

    config = json.loads(config_json)
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        result = client.apps_update_config(resolved_id, config)
        _audit_record("config_set", "app", resource_id=resolved_id)
        return result


@mcp.tool()
def apps_config_patch(
    app_id: str | None = None,
    name: str | None = None,
    set_values: dict[str, str] | None = None,
    unset_keys: list[str] | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Patch app config with dot-notation keys. Modifies specified values in-place.

    Args:
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
        set_values: Dict of dot-notation key paths to values
            (e.g. {"model.name": "gpt-4o", "model.completion_params.temperature": "0.7"})
        unset_keys: List of dot-notation key paths to remove
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        config = client.apps_get_config(resolved_id)
        set_ops = list(set_values.items()) if set_values else None
        apply_patches(config, set_ops=set_ops, unset_ops=unset_keys)
        result = client.apps_update_config(resolved_id, config)
        _audit_record("config_patch", "app", resource_id=resolved_id)
        return result


@mcp.tool()
def apps_config_get_key(
    key_path: str,
    app_id: str | None = None,
    name: str | None = None,
) -> Any:
    """Get a specific config value by dot-notation key path.

    Args:
        key_path: Dot-separated key (e.g. "model.name", "pre_prompt")
        app_id: App ID (use this or name)
        name: App name for resolution (exact match)
    """
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        config = client.apps_get_config(resolved_id)
        return get_nested(config, key_path)


@mcp.tool()
def apps_import(yaml_data: str, name: str | None = None) -> dict[str, Any]:
    """DESTRUCTIVE: Import an app from DSL YAML string. Creates a new app.

    Args:
        yaml_data: YAML string of the app DSL
        name: Optional name override for the imported app
    """
    _check_readonly()
    with _get_client() as client:
        result = client.apps_import(yaml_data, name=name)
        _audit_record(
            "import",
            "app",
            resource_id=result.get("id", ""),
            resource_name=result.get("name", name or ""),
        )
        return result


@mcp.tool()
def apps_clone(
    app_id: str | None = None,
    name: str | None = None,
    clone_name: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Clone an app by exporting and re-importing its DSL.

    Args:
        app_id: Source app ID (use this or name)
        name: Source app name for resolution (exact match)
        clone_name: Name for the cloned app (default: "Copy of <original>")
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_app(client, app_id, name)
        result = client.apps_clone(resolved_id, name=clone_name)
        _audit_record("clone", "app", resource_id=resolved_id, resource_name=clone_name or "")
        return result


@mcp.tool()
def apps_diff(
    left_app_id: str,
    right_app_id: str,
) -> list[dict[str, Any]]:
    """Compare two apps and return their differences.

    Args:
        left_app_id: First app ID
        right_app_id: Second app ID
    """
    with _get_client() as client:
        left = client.apps_get(left_app_id)
        right = client.apps_get(right_app_id)
        left_name = left.get("name", left_app_id[:12])
        right_name = right.get("name", right_app_id[:12])
        return diff_configs(left, right, left_name, right_name)


@mcp.tool()
def dsl_diff(
    left_yaml: str,
    right_yaml: str,
    left_label: str = "left",
    right_label: str = "right",
) -> list[dict[str, Any]]:
    """Compare two DSL YAML strings and return differences.

    Args:
        left_yaml: First YAML string
        right_yaml: Second YAML string
        left_label: Label for left side
        right_label: Label for right side
    """
    return diff_dsl(left_yaml, right_yaml, left_label, right_label)


@mcp.tool()
def kb_create(name: str, description: str = "") -> dict[str, Any]:
    """DESTRUCTIVE: Create a new knowledge base.

    Args:
        name: Knowledge base name
        description: Knowledge base description
    """
    _check_readonly()
    with _get_client() as client:
        result = client.kb_create(name=name, description=description)
        _audit_record("create", "kb", resource_name=name)
        return result


@mcp.tool()
def kb_upload(
    dataset_id: str | None = None,
    name: str | None = None,
    path: str = ".",
    pattern: str = "*.md",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    separator: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Upload files to a knowledge base.

    Args:
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
        path: File or directory path to upload
        pattern: File glob pattern (only used when path is a directory; ignored for single files)
        chunk_size: Max tokens per chunk (None = automatic)
        chunk_overlap: Overlap tokens between chunks (None = automatic)
        separator: Custom separator string (None = automatic)
    """
    _check_readonly()
    upload_kwargs = {
        k: v
        for k, v in [
            ("chunk_size", chunk_size),
            ("chunk_overlap", chunk_overlap),
            ("separator", separator),
        ]
        if v is not None
    }

    p = Path(path)
    audit_path = p.name or str(p.resolve().name)
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        if p.is_file():
            result = client.kb_upload_file(resolved_id, p, **upload_kwargs)
            _audit_record("upload", "kb", resource_id=resolved_id, details={"path": audit_path})
            return {"uploaded": 1, "failed": 0, "total": 1, "result": result}
        result = client.kb_upload_dir(resolved_id, p, pattern)
        _audit_record("upload", "kb", resource_id=resolved_id, details={"path": audit_path})
        return result


@mcp.tool()
def kb_docs_status(
    doc_id: str,
    dataset_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Get indexing status of a document.

    Args:
        doc_id: Document ID
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution
    """
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        return client.kb_document_status(resolved_id, doc_id)


@mcp.tool()
def kb_docs_reindex(
    doc_id: str,
    dataset_id: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """DESTRUCTIVE: Trigger re-indexing of a document.

    Args:
        doc_id: Document ID
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        result = client.kb_document_reindex(resolved_id, doc_id)
        _audit_record(
            "reindex",
            "document",
            resource_id=doc_id,
            details={"dataset_id": resolved_id},
        )
        return result


@mcp.tool()
def kb_docs_delete(
    doc_id: str,
    dataset_id: str | None = None,
    name: str | None = None,
) -> dict[str, str]:
    """DESTRUCTIVE: Delete a document from a knowledge base.

    Args:
        doc_id: Document ID to delete
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        client.kb_delete_document(resolved_id, doc_id)
        _audit_record("delete", "document", resource_id=doc_id, details={"dataset_id": resolved_id})
        return {"deleted": doc_id, "dataset_id": resolved_id}


@mcp.tool()
def kb_clear(dataset_id: str | None = None, name: str | None = None) -> dict[str, int]:
    """DESTRUCTIVE: Delete ALL documents in a knowledge base. Cannot be undone.

    Args:
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        count = client.kb_delete_all_documents(resolved_id)
        _audit_record("clear", "kb", resource_id=resolved_id, details={"deleted_count": count})
        return {"deleted_count": count, "dataset_id": resolved_id}


@mcp.tool()
def kb_sync(
    dataset_id: str | None = None,
    name: str | None = None,
    path: str = ".",
    pattern: str = "*.md",
    recursive: bool = False,
    delete_missing: bool = False,
    checksum: bool = False,
) -> dict[str, Any]:
    """DESTRUCTIVE: Sync local files to a knowledge base.

    Uploads new files and optionally deletes remote-only documents.

    Args:
        dataset_id: Dataset ID (use this or name)
        name: KB name for resolution (exact match)
        path: Local directory path
        pattern: File glob pattern
        recursive: Search subdirectories
        delete_missing: Delete remote documents not found locally
        checksum: Compare checksums to detect and re-upload changed files
    """
    _check_readonly()
    with _get_client() as client:
        resolved_id = _resolve_dataset(client, dataset_id, name)
        plan = compute_sync_plan(
            client, resolved_id, Path(path), pattern, recursive, delete_missing, checksum
        )
        result = execute_sync(client, resolved_id, plan)
        sync_path = Path(path).name or str(Path(path).resolve().name)
        _audit_record("sync", "kb", resource_id=resolved_id, details={"path": sync_path})
        return result


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
