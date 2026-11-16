"""Voice command capability metadata for the Manifest voice surface."""

from typing import Any

VOICE_COMMAND_CAPABILITIES: list[dict[str, Any]] = [
    {
        "id": "navigate-ideas",
        "category": "navigation",
        "title": "Open the founder workspace",
        "description": "Move between the main app surfaces without touching the keyboard or pointer.",
        "examples": [
            "Open ideas",
            "Go to account",
            "Open messages",
            "Open pitch reels",
            "Open API docs",
        ],
    },
    {
        "id": "account-claim",
        "category": "account",
        "title": "Claim a full account (guest tryouts)",
        "description": "Jump to account access or email a one-time upgrade link to an address you say aloud.",
        "examples": [
            "Claim my account",
            "Send upgrade link to you at example dot com",
        ],
    },
    {
        "id": "integrations-github",
        "category": "account",
        "title": "Integrations and GitHub bootstrap",
        "description": "Open Account integrations to connect GitHub, or create a private repo from the current idea when GitHub is connected.",
        "examples": [
            "Open integrations",
            "Open GitHub integration",
            "Bootstrap GitHub repo my-startup confirm bootstrap",
        ],
    },
    {
        "id": "ideas-create-open",
        "category": "ideas",
        "title": "Create and open ideas",
        "description": "Start new ideas and jump straight into the right section of the workspace.",
        "examples": [
            "Create a new idea called Climate Ledger",
            "Open the canvas",
            "Open the patent",
        ],
    },
    {
        "id": "ideas-manage",
        "category": "ideas",
        "title": "Manage the current idea",
        "description": "Rename, publish, unpublish, share, open history, or delete the current idea.",
        "examples": [
            "Rename this idea to Startup OS",
            "Publish this idea",
            "Open share",
            "Open history",
        ],
    },
    {
        "id": "ideas-generate",
        "category": "ideas",
        "title": "Generate core documents",
        "description": "Kick off pitch deck, PRD, provisional patent, or background tasks from your idea note.",
        "examples": [
            "Generate pitch deck",
            "Generate PRD",
            "Generate patent",
            "Run background tasks",
        ],
    },
    {
        "id": "workspace-layout",
        "category": "workspace",
        "title": "Tune the workspace layout",
        "description": "Control focus mode and the supporting panels with deterministic voice commands.",
        "examples": ["Turn on focus mode", "Collapse the library", "Expand the context panel"],
    },
    {
        "id": "search",
        "category": "search",
        "title": "Search Manifest",
        "description": "Open universal search and seed it with a spoken query.",
        "examples": ["Search for climate fintech", "Open search", "Find marketplace ideas"],
    },
    {
        "id": "reels",
        "category": "reels",
        "title": "Control pitch reels",
        "description": "Move through reels and trigger the same social actions available on the page.",
        "examples": [
            "Next reel",
            "Like this reel",
            "Repost this reel",
            "Follow this creator",
            "Open comments",
            "Comment on this reel This is sharp",
            "Open workspace for this reel",
        ],
    },
]


VOICE_COMMAND_CAPABILITY_SUMMARY = (
    "Manifest Voice can navigate the app (including messages), create and manage ideas, generate pitch decks and "
    "other core documents, control the workspace layout, search Manifest, run pitch-reel actions, open account "
    "integrations (including GitHub), bootstrap a private GitHub repository from the current idea when connected, "
    "and help guest tryouts request an email link to claim a full account."
)
