"""Environment diff — compare two Dify instances.

Compares apps and knowledge bases between two environments (e.g. dev vs prod).
"""

from __future__ import annotations

from typing import Any

from dify_admin.client import DifyClient


def compare_environments(
    source: DifyClient,
    target: DifyClient,
) -> dict[str, Any]:
    """Compare two Dify environments.

    Args:
        source: Source environment client
        target: Target environment client

    Returns:
        Dict with apps_diff and kb_diff sections
    """
    source_apps = source.apps_list(fetch_all=True)
    target_apps = target.apps_list(fetch_all=True)
    apps_diff = _compare_resources(source_apps, target_apps)

    source_kbs = source.kb_list(fetch_all=True)
    target_kbs = target.kb_list(fetch_all=True)
    kb_diff = _compare_resources(source_kbs, target_kbs)

    return {
        "apps": apps_diff,
        "knowledge_bases": kb_diff,
        "summary": {
            "apps_source_only": len(apps_diff["source_only"]),
            "apps_target_only": len(apps_diff["target_only"]),
            "apps_common": len(apps_diff["common"]),
            "kb_source_only": len(kb_diff["source_only"]),
            "kb_target_only": len(kb_diff["target_only"]),
            "kb_common": len(kb_diff["common"]),
        },
    }


def _resource_summary(r: dict[str, Any]) -> dict[str, str]:
    """Extract summary fields from a resource."""
    return {"name": r.get("name", ""), "id": r.get("id", ""), "mode": r.get("mode", "")}


def _compare_resources(
    source_list: list[dict[str, Any]],
    target_list: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Compare two lists of resources by name."""
    source_by_name = {r.get("name", ""): r for r in source_list}
    target_by_name = {r.get("name", ""): r for r in target_list}

    source_names = set(source_by_name.keys())
    target_names = set(target_by_name.keys())

    source_only = [
        _resource_summary(source_by_name[n]) for n in sorted(source_names - target_names)
    ]
    target_only = [
        _resource_summary(target_by_name[n]) for n in sorted(target_names - source_names)
    ]
    common = [
        {
            "name": n,
            "source_id": source_by_name[n].get("id", ""),
            "target_id": target_by_name[n].get("id", ""),
            "mode": source_by_name[n].get("mode", ""),
        }
        for n in sorted(source_names & target_names)
    ]

    return {
        "source_only": source_only,
        "target_only": target_only,
        "common": common,
    }
