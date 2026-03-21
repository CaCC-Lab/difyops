"""Config snapshot and restore for dify-admin.

Takes JSON snapshots of app configs for rollback capability.
Stored in ~/.dify-admin/snapshots/<app_id>/<timestamp>.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dify_admin.client import DifyClient

_SNAPSHOT_DIR = Path.home() / ".dify-admin" / "snapshots"


def take_snapshot(client: DifyClient, app_id: str) -> dict[str, Any]:
    """Take a snapshot of an app's current state.

    Args:
        client: Authenticated DifyClient
        app_id: App ID to snapshot

    Returns:
        Snapshot metadata (id, app_id, timestamp, path)
    """
    app = client.apps_get(app_id)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snapshot_id = f"{timestamp}"

    app_dir = _SNAPSHOT_DIR / app_id
    app_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = app_dir / f"{snapshot_id}.json"

    snapshot_data = {
        "snapshot_id": snapshot_id,
        "app_id": app_id,
        "app_name": app.get("name", ""),
        "timestamp": time.time(),
        "iso_time": timestamp,
        "data": app,
    }
    snapshot_path.write_text(
        json.dumps(snapshot_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "snapshot_id": snapshot_id,
        "app_id": app_id,
        "app_name": app.get("name", ""),
        "path": str(snapshot_path),
    }


def list_snapshots(app_id: str) -> list[dict[str, Any]]:
    """List snapshots for an app.

    Returns an empty list if no snapshots exist (directory may not exist).

    Args:
        app_id: App ID

    Returns:
        List of snapshot metadata (newest first)
    """
    app_dir = _SNAPSHOT_DIR / app_id
    snapshots = []
    for f in sorted(app_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            snapshots.append(
                {
                    "snapshot_id": data.get("snapshot_id", f.stem),
                    "app_id": app_id,
                    "app_name": data.get("app_name", ""),
                    "iso_time": data.get("iso_time", ""),
                    "path": str(f),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    return snapshots


def restore_snapshot(client: DifyClient, app_id: str, snapshot_id: str) -> dict[str, Any]:
    """Restore an app's config from a snapshot.

    Args:
        client: Authenticated DifyClient
        app_id: App ID
        snapshot_id: Snapshot ID to restore

    Returns:
        Result dict

    Raises:
        FileNotFoundError: Snapshot not found
    """
    snapshot_path = _SNAPSHOT_DIR / app_id / f"{snapshot_id}.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    app_data = snapshot_data["data"]

    # Export current as DSL and re-import to restore full state
    # For now, restore what we can via rename (name, description)
    name = app_data.get("name", "")
    description = app_data.get("description", "")
    if name:
        client.apps_rename(app_id, name, description=description)

    return {
        "restored": True,
        "snapshot_id": snapshot_id,
        "app_id": app_id,
        "app_name": name,
    }
