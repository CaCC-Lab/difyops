"""Knowledge base sync logic.

Compares local files against remote documents and produces a sync plan.
Supports checksum-based change detection to skip unchanged files.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dify_admin.client import DifyClient


@dataclass
class SyncPlan:
    """Plan for syncing local files to a remote knowledge base."""

    to_upload: list[Path] = field(default_factory=list)
    to_update: list[Path] = field(default_factory=list)
    to_delete: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    remote_by_name: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    skipped: list[str] = field(default_factory=list)


def _file_hash(path: Path) -> str:
    """Compute MD5 hash of a file."""
    h = hashlib.md5()  # noqa: S324 — not for security, just change detection
    h.update(path.read_bytes())
    return h.hexdigest()


def compute_sync_plan(
    client: DifyClient,
    dataset_id: str,
    local_path: Path,
    pattern: str = "*.md",
    recursive: bool = False,
    delete_missing: bool = False,
    checksum: bool = False,
) -> SyncPlan:
    """Compute a sync plan by comparing local files with remote documents.

    Args:
        client: Authenticated DifyClient
        dataset_id: Target dataset ID
        local_path: Local directory containing files
        pattern: Glob pattern for matching files
        recursive: Use rglob instead of glob
        delete_missing: Include remote-only documents in to_delete
        checksum: Compare file hashes to detect changes (re-upload changed files)

    Returns:
        SyncPlan with upload, update, delete, unchanged, and skipped lists
    """
    if recursive:
        local_files = sorted(local_path.rglob(pattern))
    else:
        local_files = sorted(local_path.glob(pattern))

    remote_docs = client.kb_documents_all(dataset_id)
    remote_by_name: dict[str, dict[str, Any]] = {doc.get("name", ""): doc for doc in remote_docs}

    plan = SyncPlan(remote_by_name=remote_by_name)
    local_names: set[str] = set()

    for f in local_files:
        local_names.add(f.name)
        if f.name not in remote_by_name:
            plan.to_upload.append(f)
        elif checksum:
            remote_doc = remote_by_name[f.name]
            local_hash = _file_hash(f)
            remote_hash = (
                remote_doc.get("data_source_detail_dict", {}).get("file_detail", {}).get("hash", "")
            )
            # If remote hash unavailable, compare by word count as heuristic
            if remote_hash and remote_hash == local_hash:
                plan.skipped.append(f.name)
            elif not remote_hash:
                # No remote hash available, compare file size heuristic
                remote_words = remote_doc.get("word_count", 0)
                local_size = f.stat().st_size
                if remote_words > 0 and abs(local_size - remote_words * 5) < 500:
                    plan.skipped.append(f.name)
                else:
                    plan.to_update.append(f)
            else:
                plan.to_update.append(f)
        else:
            plan.unchanged.append(f.name)

    if delete_missing:
        for name, doc in remote_by_name.items():
            if name not in local_names:
                plan.to_delete.append(doc)

    return plan


def execute_sync(
    client: DifyClient,
    dataset_id: str,
    plan: SyncPlan,
) -> dict[str, Any]:
    """Execute a sync plan.

    Note: plan must be created by compute_sync_plan() which populates
    remote_by_name for update operations.

    Args:
        client: Authenticated DifyClient
        dataset_id: Target dataset ID
        plan: SyncPlan from compute_sync_plan()

    Returns:
        Dict with uploaded, updated, deleted, failed, unchanged, skipped counts
    """
    uploaded = 0
    updated = 0
    failed = 0
    failed_files: list[dict[str, str]] = []

    for f in plan.to_upload:
        try:
            client.kb_upload_file(dataset_id, f)
            uploaded += 1
        except Exception as e:
            failed += 1
            failed_files.append({"name": f.name, "error": str(e)})

    # For updates: delete old doc then re-upload
    remote_docs = plan.remote_by_name
    for f in plan.to_update:
        try:
            old_doc = remote_docs.get(f.name)
            if old_doc and old_doc.get("id"):
                client.kb_delete_document(dataset_id, old_doc["id"])
            client.kb_upload_file(dataset_id, f)
            updated += 1
        except Exception as e:
            failed += 1
            failed_files.append({"name": f.name, "error": str(e)})

    deleted = 0
    for doc in plan.to_delete:
        doc_id = doc.get("id")
        if doc_id:
            try:
                client.kb_delete_document(dataset_id, doc_id)
                deleted += 1
            except Exception as e:
                failed += 1
                failed_files.append({"name": doc.get("name", "?"), "error": str(e)})

    return {
        "uploaded": uploaded,
        "updated": updated,
        "deleted": deleted,
        "failed": failed,
        "unchanged": len(plan.unchanged),
        "skipped": len(plan.skipped),
        "failed_files": failed_files,
    }
