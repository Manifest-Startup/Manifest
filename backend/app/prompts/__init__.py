"""Prompt definitions (``*.mcp.json``) used by the AI services.

Use :func:`prompt_path` instead of building paths relative to a module, so
moving a module never breaks how its prompt is found.
"""

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


def prompt_path(filename: str) -> str:
    """Absolute path of a prompt file in this folder, e.g. ``prompt_path("pitch_deck.mcp.json")``."""
    return str(PROMPTS_DIR / filename)
