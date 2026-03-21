"""Config patching utilities.

Supports dot-notation key paths for reading and writing nested config values.
Example: "model.name" → config["model"]["name"]
"""

from __future__ import annotations

import json
from typing import Any


def get_nested(data: dict[str, Any], key_path: str) -> Any:
    """Get a value from a nested dict using dot-notation.

    Args:
        data: Source dictionary
        key_path: Dot-separated key path (e.g. "model.name")

    Returns:
        Value at the key path

    Raises:
        KeyError: If any key in the path doesn't exist
    """
    keys = key_path.split(".")
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            raise KeyError(f"Cannot traverse into non-dict at '{key}' in '{key_path}'")
        if key not in current:
            raise KeyError(f"Key '{key}' not found in '{key_path}'")
        current = current[key]
    return current


def set_nested(data: dict[str, Any], key_path: str, value: Any) -> dict[str, Any]:
    """Set a value in a nested dict using dot-notation.

    Creates intermediate dicts as needed.

    Args:
        data: Target dictionary (modified in place and returned)
        key_path: Dot-separated key path (e.g. "model.name")
        value: Value to set

    Returns:
        The modified dictionary
    """
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
    return data


def delete_nested(data: dict[str, Any], key_path: str) -> dict[str, Any]:
    """Delete a key from a nested dict using dot-notation.

    Args:
        data: Target dictionary (modified in place and returned)
        key_path: Dot-separated key path (e.g. "model.name")

    Returns:
        The modified dictionary

    Raises:
        KeyError: If the key path doesn't exist
    """
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise KeyError(f"Key path '{key_path}' not found")
        current = current[key]
    if not isinstance(current, dict) or keys[-1] not in current:
        raise KeyError(f"Key '{keys[-1]}' not found in '{key_path}'")
    del current[keys[-1]]
    return data


def parse_value(raw: str) -> Any:
    """Parse a string value into a Python object.

    Tries JSON first, falls back to string.
    Examples:
        "42" → 42
        "true" → True
        "0.7" → 0.7
        '"hello"' → "hello"
        "hello" → "hello"
        '["a","b"]' → ["a", "b"]

    Args:
        raw: Raw string value

    Returns:
        Parsed value
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def apply_patches(
    config: dict[str, Any],
    set_ops: list[tuple[str, str]] | None = None,
    unset_ops: list[str] | None = None,
) -> dict[str, Any]:
    """Apply set/unset operations to a config dict.

    Args:
        config: Config dictionary to patch
        set_ops: List of (key_path, raw_value) tuples
        unset_ops: List of key_paths to delete

    Returns:
        Modified config
    """
    if set_ops:
        for key_path, raw_value in set_ops:
            value = parse_value(raw_value)
            set_nested(config, key_path, value)
    if unset_ops:
        for key_path in unset_ops:
            delete_nested(config, key_path)
    return config
