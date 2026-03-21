"""Name resolution for apps and knowledge bases.

Resolves human-friendly names to resource IDs via exact case-sensitive matching.
"""

from __future__ import annotations

from typing import Any

from dify_admin.client import DifyClient


class NameNotFoundError(Exception):
    """No resource found with the given name."""


class AmbiguousNameError(Exception):
    """Multiple resources found with the given name."""


def resolve_app_by_name(client: DifyClient, name: str) -> dict[str, Any]:
    """Resolve an app by exact name (case-sensitive).

    Args:
        client: Authenticated DifyClient
        name: Exact app name to search for

    Returns:
        App dict matching the name

    Raises:
        NameNotFoundError: No app with this name
        AmbiguousNameError: Multiple apps with this name
    """
    apps = client.apps_list(fetch_all=True)
    matches = [a for a in apps if a.get("name") == name]
    if not matches:
        raise NameNotFoundError(f"No app found with name: {name}")
    if len(matches) > 1:
        ids = [m.get("id", "?")[:12] for m in matches]
        raise AmbiguousNameError(f"Multiple apps found with name '{name}': {', '.join(ids)}")
    return matches[0]


def resolve_kb_by_name(client: DifyClient, name: str) -> dict[str, Any]:
    """Resolve a knowledge base by exact name (case-sensitive).

    Args:
        client: Authenticated DifyClient
        name: Exact knowledge base name to search for

    Returns:
        Dataset dict matching the name

    Raises:
        NameNotFoundError: No KB with this name
        AmbiguousNameError: Multiple KBs with this name
    """
    datasets = client.kb_list(fetch_all=True)
    matches = [d for d in datasets if d.get("name") == name]
    if not matches:
        raise NameNotFoundError(f"No knowledge base found with name: {name}")
    if len(matches) > 1:
        ids = [m.get("id", "?")[:12] for m in matches]
        raise AmbiguousNameError(
            f"Multiple knowledge bases found with name '{name}': {', '.join(ids)}"
        )
    return matches[0]
