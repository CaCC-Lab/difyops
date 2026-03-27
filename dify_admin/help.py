"""Structured help text generation for dify-admin CLI.

Generates click-compatible docstrings with standardized sections:
summary, description, examples, side effects, JSON output keys,
and idempotency labels.
"""

from __future__ import annotations


def build_help_text(
    summary: str,
    description: str,
    examples: list[str],
    *,
    side_effects: str | None = None,
    idempotent: str = "yes",
    json_output_keys: list[str] | None = None,
    supports_dry_run: bool = False,
) -> str:
    """Generate a structured help text for a CLI subcommand.

    Args:
        summary: One-line command summary (first line of help).
        description: Detailed description (3+ lines recommended).
        examples: List of usage examples, each starting with '$ dify-admin'.
        side_effects: Description of side effects (destructive commands only).
        idempotent: Idempotency classification ("yes", "no", "conditional").
        json_output_keys: Top-level JSON output keys (for --json commands).
        supports_dry_run: Whether the command supports --dry-run.

    Returns:
        Formatted help text string usable as a click docstring.
    """
    parts: list[str] = []

    # 1. One-line summary
    parts.append(summary)
    parts.append("")

    # 2. Detailed description
    parts.append(description)
    parts.append("")

    # 3. Examples
    parts.append("Examples:")
    for example in examples:
        for line in example.splitlines():
            parts.append(f"  {line}")
    parts.append("")

    # 4. Side Effects (destructive commands only)
    if side_effects is not None:
        parts.append("Side Effects:")
        for line in side_effects.splitlines():
            parts.append(f"  {line}")
        parts.append("")

    # 5. JSON Output Keys
    if json_output_keys is not None:
        parts.append(f"JSON Output Keys: {', '.join(json_output_keys)}")

    # 6. Idempotent label
    parts.append(f"Idempotent: {idempotent}")

    return "\n".join(parts)
