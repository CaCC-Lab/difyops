"""Operation explainability for dify-admin.

Provides human-readable explanations of what an operation will do,
what it changes, and what risks are involved.
"""

from __future__ import annotations

from typing import Any

OPERATION_INFO: dict[str, dict[str, Any]] = {
    "apps_create": {
        "description": "Create a new Dify app",
        "changes": ["A new app will be added to your Dify instance"],
        "risk": "low",
        "reversible": True,
        "undo": "Delete the created app with apps_delete",
    },
    "apps_delete": {
        "description": "Permanently delete an app",
        "changes": ["The app and all its configurations will be removed"],
        "risk": "high",
        "reversible": False,
        "undo": "Cannot be undone. Take a snapshot first with apps_snapshot",
    },
    "apps_rename": {
        "description": "Rename an app",
        "changes": ["The app name will be updated"],
        "risk": "low",
        "reversible": True,
        "undo": "Rename it back or restore from snapshot",
    },
    "apps_config_set": {
        "description": "Replace entire app model configuration",
        "changes": ["The full model config will be overwritten"],
        "risk": "medium",
        "reversible": True,
        "undo": "Restore from snapshot or manually revert",
    },
    "apps_config_patch": {
        "description": "Patch specific config values",
        "changes": ["Only specified keys will be modified"],
        "risk": "low",
        "reversible": True,
        "undo": "Patch back to original values or restore from snapshot",
    },
    "apps_clone": {
        "description": "Clone an app (export + import)",
        "changes": ["A new app will be created as a copy"],
        "risk": "low",
        "reversible": True,
        "undo": "Delete the cloned app",
    },
    "apps_import": {
        "description": "Import an app from DSL YAML",
        "changes": ["A new app will be created from the YAML definition"],
        "risk": "low",
        "reversible": True,
        "undo": "Delete the imported app",
    },
    "kb_create": {
        "description": "Create a new knowledge base",
        "changes": ["An empty knowledge base will be created"],
        "risk": "low",
        "reversible": True,
        "undo": "Delete the knowledge base",
    },
    "kb_upload": {
        "description": "Upload files to a knowledge base",
        "changes": ["New documents will be added and indexed"],
        "risk": "low",
        "reversible": True,
        "undo": "Delete the uploaded documents",
    },
    "kb_docs_delete": {
        "description": "Delete a document from a knowledge base",
        "changes": ["The document and its index will be removed"],
        "risk": "medium",
        "reversible": False,
        "undo": "Re-upload the file",
    },
    "kb_clear": {
        "description": "Delete ALL documents in a knowledge base",
        "changes": ["All documents and their indexes will be removed"],
        "risk": "high",
        "reversible": False,
        "undo": "Re-upload all files",
    },
    "kb_sync": {
        "description": "Sync local files to a knowledge base",
        "changes": [
            "New files will be uploaded",
            "With --delete-missing, remote-only documents will be deleted",
        ],
        "risk": "medium",
        "reversible": False,
        "undo": "Re-sync with the original files",
    },
    "state_apply": {
        "description": "Apply desired state from YAML",
        "changes": [
            "Apps and KBs will be created/updated/deleted to match YAML",
        ],
        "risk": "high",
        "reversible": False,
        "undo": "Apply a previous state file or restore from snapshots",
    },
}


def explain_operation(operation: str) -> dict[str, Any]:
    """Get explanation for an operation.

    Args:
        operation: Operation name (e.g. "apps_delete")

    Returns:
        Dict with description, changes, risk, reversible, undo
    """
    if operation in OPERATION_INFO:
        return {"operation": operation, **OPERATION_INFO[operation]}
    return {
        "operation": operation,
        "description": f"Unknown operation: {operation}",
        "changes": [],
        "risk": "unknown",
        "reversible": False,
        "undo": "Check documentation",
    }


def list_operations() -> list[dict[str, Any]]:
    """List all known operations with their risk levels.

    Returns:
        List of operation info dicts
    """
    return [
        {"operation": op, "risk": info["risk"], "description": info["description"]}
        for op, info in OPERATION_INFO.items()
    ]
