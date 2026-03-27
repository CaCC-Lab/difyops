"""Shared pytest fixtures and patches for the test suite."""

from __future__ import annotations

import inspect

import click.testing

# ---------------------------------------------------------------------------
# Patch CliRunner so that mix_stderr defaults to False.
# This ensures result.stderr captures stderr output separately from stdout,
# which is required by tests that verify JSON error output on stderr
# (test_cli_errors.py) and tests that access result.stderr (test_cli_help.py).
# ---------------------------------------------------------------------------
_original_init = click.testing.CliRunner.__init__
_has_mix_stderr = "mix_stderr" in inspect.signature(_original_init).parameters


def _patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
    if _has_mix_stderr:
        kwargs.setdefault("mix_stderr", False)
    _original_init(self, *args, **kwargs)


click.testing.CliRunner.__init__ = _patched_init  # type: ignore[assignment]
