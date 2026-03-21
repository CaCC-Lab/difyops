"""App config and DSL diff utilities.

Compares two app configurations or DSL YAML strings
and produces a human-readable diff.
"""

from __future__ import annotations

import json
from typing import Any

import yaml


def diff_configs(
    left: dict[str, Any],
    right: dict[str, Any],
    left_label: str = "left",
    right_label: str = "right",
    prefix: str = "",
) -> list[dict[str, Any]]:
    """Compare two config dicts and return a list of differences.

    Args:
        left: First config
        right: Second config
        left_label: Label for left config
        right_label: Label for right config
        prefix: Key path prefix for recursion

    Returns:
        List of diffs, each with: path, type (added/removed/changed), left, right
    """
    diffs: list[dict[str, Any]] = []
    all_keys = sorted(left.keys() | right.keys())

    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key
        in_left = key in left
        in_right = key in right

        if in_left and not in_right:
            diffs.append(
                {
                    "path": path,
                    "type": "removed",
                    left_label: _format_value(left[key]),
                    right_label: None,
                }
            )
        elif not in_left and in_right:
            diffs.append(
                {
                    "path": path,
                    "type": "added",
                    left_label: None,
                    right_label: _format_value(right[key]),
                }
            )
        elif isinstance(left[key], dict) and isinstance(right[key], dict):
            diffs.extend(diff_configs(left[key], right[key], left_label, right_label, prefix=path))
        elif left[key] != right[key]:
            diffs.append(
                {
                    "path": path,
                    "type": "changed",
                    left_label: _format_value(left[key]),
                    right_label: _format_value(right[key]),
                }
            )

    return diffs


def _format_value(value: Any) -> str:
    """Format a value for display."""
    if isinstance(value, str) and len(value) > 100:
        return value[:100] + "..."
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
        if len(s) > 100:
            return s[:100] + "..."
        return s
    return str(value)


def format_diff_table(diffs: list[dict[str, Any]], left_label: str, right_label: str) -> str:
    """Format diffs as a human-readable string.

    Args:
        diffs: List of diff entries from diff_configs
        left_label: Label for left side
        right_label: Label for right side

    Returns:
        Formatted string
    """
    if not diffs:
        return "No differences found."

    lines = []
    for d in diffs:
        path = d["path"]
        dtype = d["type"]
        if dtype == "added":
            lines.append(f"  + {path}: {d[right_label]}")
        elif dtype == "removed":
            lines.append(f"  - {path}: {d[left_label]}")
        else:
            lines.append(f"  ~ {path}: {d[left_label]} → {d[right_label]}")
    return "\n".join(lines)


def diff_dsl(
    left_yaml: str,
    right_yaml: str,
    left_label: str = "left",
    right_label: str = "right",
) -> list[dict[str, Any]]:
    """Compare two DSL YAML strings.

    Args:
        left_yaml: First YAML string
        right_yaml: Second YAML string
        left_label: Label for left side
        right_label: Label for right side

    Returns:
        List of diffs (same format as diff_configs)
    """
    left_data = yaml.safe_load(left_yaml) or {}
    right_data = yaml.safe_load(right_yaml) or {}
    if not isinstance(left_data, dict):
        left_data = {"_raw": str(left_data)}
    if not isinstance(right_data, dict):
        right_data = {"_raw": str(right_data)}
    return diff_configs(left_data, right_data, left_label, right_label)
