"""Desired state management for dify-admin.

Terraform-lite: define desired state in YAML, plan changes, apply them.

YAML format:
    apps:
      - name: "FAQ Bot"
        mode: chat
        description: "Customer FAQ chatbot"
      - name: "Workflow App"
        mode: advanced-chat

    knowledge_bases:
      - name: "Company Docs"
        description: "Internal documentation"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dify_admin.client import DifyClient


@dataclass
class StateAction:
    """A single action in a state plan."""

    resource_type: str  # "app" or "kb"
    action: str  # "create", "update", "delete"
    name: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StatePlan:
    """Plan of actions to reach desired state."""

    actions: list[StateAction] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        """Count of actions by type."""
        counts: dict[str, int] = {"create": 0, "update": 0, "delete": 0}
        for a in self.actions:
            counts[a.action] = counts.get(a.action, 0) + 1
        return counts


def load_state_file(path: Path) -> dict[str, Any]:
    """Load desired state from a YAML file.

    Args:
        path: Path to YAML state file

    Returns:
        Parsed state dict with 'apps' and/or 'knowledge_bases' keys
    """
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError(f"State file must be a YAML mapping, got {type(data).__name__}")
    return data


def _plan_resources(
    plan: StatePlan,
    resource_type: str,
    desired_specs: list[dict[str, Any]],
    current_list: list[dict[str, Any]],
    delete_missing: bool,
    diff_fn: Any = None,
) -> None:
    """Plan create/update/delete actions for a resource type.

    Assumes resource names are unique. Resources with no name are skipped.
    """
    if not desired_specs:
        return

    current_by_name = {r.get("name"): r for r in current_list if r.get("name")}

    for spec in desired_specs:
        name = spec.get("name")
        if not name:
            continue
        if name not in current_by_name:
            plan.actions.append(
                StateAction(resource_type=resource_type, action="create", name=name, details=spec)
            )
        elif diff_fn:
            changes = diff_fn(current_by_name[name], spec)
            if changes:
                plan.actions.append(
                    StateAction(
                        resource_type=resource_type,
                        action="update",
                        name=name,
                        details={"id": current_by_name[name]["id"], "changes": changes},
                    )
                )

    if delete_missing:
        desired_names = {s.get("name") for s in desired_specs}
        for name, current in current_by_name.items():
            if name not in desired_names:
                plan.actions.append(
                    StateAction(
                        resource_type=resource_type,
                        action="delete",
                        name=name,
                        details={"id": current["id"]},
                    )
                )


def compute_plan(
    client: DifyClient,
    desired: dict[str, Any],
    delete_missing: bool = False,
) -> StatePlan:
    """Compare desired state with current state and produce a plan.

    Args:
        client: Authenticated DifyClient
        desired: Desired state dict (from load_state_file)
        delete_missing: If True, plan deletion of resources not in desired state

    Returns:
        StatePlan with actions to reach desired state
    """
    plan = StatePlan()

    _plan_resources(
        plan,
        "app",
        desired.get("apps", []),
        client.apps_list(fetch_all=True) if desired.get("apps") else [],
        delete_missing,
        diff_fn=_diff_app,
    )
    _plan_resources(
        plan,
        "kb",
        desired.get("knowledge_bases", []),
        client.kb_list(fetch_all=True) if desired.get("knowledge_bases") else [],
        delete_missing,
    )

    return plan


def execute_plan(client: DifyClient, plan: StatePlan) -> list[dict[str, Any]]:
    """Execute a state plan.

    Args:
        client: Authenticated DifyClient
        plan: StatePlan to execute

    Returns:
        List of results for each action
    """
    results: list[dict[str, Any]] = []

    for action in plan.actions:
        try:
            if action.resource_type == "app":
                result = _execute_app_action(client, action)
            elif action.resource_type == "kb":
                result = _execute_kb_action(client, action)
            else:
                result = {"status": "skip", "reason": f"Unknown type: {action.resource_type}"}
            results.append(
                {
                    "action": action.action,
                    "type": action.resource_type,
                    "name": action.name,
                    "status": "ok",
                    **result,
                }
            )
        except Exception as e:
            results.append(
                {
                    "action": action.action,
                    "type": action.resource_type,
                    "name": action.name,
                    "status": "error",
                    "error": str(e),
                }
            )

    return results


def _diff_app(current: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Find differences between current app and desired spec."""
    changes: dict[str, Any] = {}
    for key in ("description", "icon", "icon_type"):
        if key in desired and desired[key] != current.get(key):
            changes[key] = desired[key]
    return changes


def _execute_app_action(client: DifyClient, action: StateAction) -> dict[str, Any]:
    """Execute an app action."""
    if action.action == "create":
        result = client.apps_create(
            name=action.details.get("name", action.name),
            mode=action.details.get("mode", "chat"),
            description=action.details.get("description", ""),
        )
        return {"id": result.get("id")}
    if action.action == "update":
        app_id = action.details["id"]
        changes = action.details.get("changes", {})
        if changes:
            client.apps_rename(app_id, action.name, **changes)
        return {"id": app_id, "changes": changes}
    if action.action == "delete":
        app_id = action.details["id"]
        client.apps_delete(app_id)
        return {"id": app_id}
    return {}


def _execute_kb_action(client: DifyClient, action: StateAction) -> dict[str, Any]:
    """Execute a KB action."""
    if action.action == "create":
        result = client.kb_create(
            name=action.details.get("name", action.name),
            description=action.details.get("description", ""),
        )
        return {"id": result.get("id")}
    if action.action == "delete":
        kb_id = action.details["id"]
        client.kb_delete(kb_id)
        return {"id": kb_id}
    return {}
