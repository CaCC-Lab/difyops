"""Audit log for dify-admin operations.

Records all destructive operations to a JSON Lines file for review and undo.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_DEFAULT_LOG_DIR = Path.home() / ".dify-admin" / "logs"


def _get_log_path() -> Path:
    """Get audit log file path."""
    log_dir = Path(os.environ.get("DIFY_AUDIT_DIR", str(_DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "audit.jsonl"


def record(
    operation: str,
    resource_type: str,
    resource_id: str = "",
    resource_name: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an operation to the audit log.

    Args:
        operation: Operation type (create, delete, update, rename, import, etc.)
        resource_type: Resource type (app, kb, document)
        resource_id: Resource ID
        resource_name: Resource name
        details: Additional details

    Returns:
        The recorded entry
    """
    entry = {
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "operation": operation,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "details": details or {},
    }

    try:
        log_path = _get_log_path()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        import sys

        print(f"[dify-admin] audit write failed: {e}", file=sys.stderr)

    return entry


def get_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent audit log entries.

    Args:
        limit: Maximum number of entries to return

    Returns:
        List of entries (newest first)
    """
    log_path = _get_log_path()
    if not log_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return list(reversed(entries[-limit:]))


def clear_log() -> int:
    """Clear the audit log.

    Returns:
        Number of entries cleared
    """
    log_path = _get_log_path()
    if not log_path.exists():
        return 0
    count = sum(1 for line in log_path.read_text().splitlines() if line.strip())
    log_path.write_text("")
    return count
