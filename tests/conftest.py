"""Shared pytest fixtures and patches for the test suite."""

from __future__ import annotations

import click.testing


# Patch click.testing.Result.stderr to return empty string instead of raising
# ValueError when stderr is not separately captured. This allows test helpers
# that use ``getattr(result, "stderr", None)`` to work regardless of whether
# the CliRunner was created with ``mix_stderr=False``.
_original_stderr = click.testing.Result.stderr


@property  # type: ignore[misc]
def _safe_stderr(self: click.testing.Result) -> str:
    """Return stderr output, or empty string if not separately captured."""
    if self.stderr_bytes is None:
        return ""
    return self.stderr_bytes.decode(self.runner.charset, "replace").replace(
        "\r\n", "\n"
    )


click.testing.Result.stderr = _safe_stderr  # type: ignore[assignment]
