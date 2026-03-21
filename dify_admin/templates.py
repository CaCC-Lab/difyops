"""App templates for quick scaffolding.

Provides pre-configured app specs for common use cases.
"""

from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "chat-basic": {
        "name": "Chat Bot",
        "mode": "chat",
        "description": "Basic chat bot",
    },
    "chat-rag": {
        "name": "RAG Chat Bot",
        "mode": "chat",
        "description": "Chat bot with knowledge base retrieval",
    },
    "completion": {
        "name": "Text Generator",
        "mode": "completion",
        "description": "Text completion / generation app",
    },
    "workflow": {
        "name": "Workflow App",
        "mode": "advanced-chat",
        "description": "Advanced workflow-based app",
    },
    "agent": {
        "name": "Agent",
        "mode": "agent-chat",
        "description": "Agent with tool calling capabilities",
    },
}


def list_templates() -> list[dict[str, str]]:
    """List available templates.

    Returns:
        List of dicts with: id, name, mode, description
    """
    return [
        {
            "id": tid,
            "name": t["name"],
            "mode": t["mode"],
            "description": t["description"],
        }
        for tid, t in TEMPLATES.items()
    ]


def get_template(template_id: str) -> dict[str, Any]:
    """Get a template by ID.

    Args:
        template_id: Template identifier (e.g. "chat-basic")

    Returns:
        Template spec dict

    Raises:
        KeyError: If template not found
    """
    if template_id not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise KeyError(f"Template '{template_id}' not found. Available: {available}")
    return dict(TEMPLATES[template_id])
