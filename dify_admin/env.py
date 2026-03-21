"""Dotenv file loading for dify-admin.

Loads .env files without external dependencies.
Supports: KEY=VALUE, KEY="VALUE", comments (#), empty lines.
Does NOT override existing environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | str | None = None) -> int:
    """Load environment variables from a .env file.

    Searches for .env in: specified path > CWD > home directory.
    Does NOT override existing environment variables.

    Args:
        path: Explicit .env file path. If None, searches default locations.

    Returns:
        Number of variables loaded.
    """
    env_file = _find_dotenv(path)
    if env_file is None:
        return 0
    return _parse_and_load(env_file)


def _find_dotenv(path: Path | str | None = None) -> Path | None:
    """Find .env file in search paths."""
    if path is not None:
        p = Path(path)
        return p if p.is_file() else None

    candidates = [
        Path.cwd() / ".env",
        Path.home() / ".dify-admin" / ".env",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _parse_and_load(env_file: Path) -> int:
    """Parse .env file and set environment variables."""
    loaded = 0
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Remove surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        # Don't override existing env vars
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1

    return loaded
