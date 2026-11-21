"""Manifest's tools for the live voice agent, generated from the same catalog as /mcp and the CLI.

The voice agent can do everything the agent plugin and the ``manifest`` CLI can, because
it reads the very same generated catalog (``scripts/generate_agent_tools.py`` writes
``tools.generated.json`` next to this file) and calls the same public GraphQL and REST
routes with the person's own session token, so every backend permission check applies.

Sending ~130 tool schemas on every spoken turn would be slow and expensive, so the model
sees a small set of everyday tools directly plus two meta tools:

- ``find_tools(query)`` searches the whole catalog and returns matching tools with schemas;
- ``use_tool(name, arguments)`` runs any catalog tool by name.

Destructive tools keep the ``confirm`` handshake from the Worker (deploy/cloudflare/src/
mcp-account.mjs): without ``confirm: true`` they return a preview the agent reads aloud.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

CATALOG_PATH = Path(__file__).with_name("tools.generated.json")

# Everyday tools the model sees directly on every turn (everything else via find_tools).
CORE_TOOLS: tuple[str, ...] = (
    "me",
    "ideas",
    "idea",
    "create_idea",
    "update_idea",
    "universal_search",
    "find_similar_ideas",
    "start_idea_qualification",
    "continue_idea_qualification",
    "enqueue_background_tasks",
    "generation_job",
    "my_inbox",
    "reply_in_inbox",
    "unread_message_count",
    "put_vault_file",
    "customer_discovery",
    "research_market",
    "find_prospects",
    "draft_outreach",
)

# Answers longer than this are cut before they reach the model (speech needs gist, not dumps).
MAX_RESULT_CHARS = 10000
# Market and prospect research search the live web; stay under the edge proxy's 100 s.
REQUEST_TIMEOUT_SECONDS = 95.0
AUTH_ERROR = re.compile(r"not authenticated|authentication required|unauthori[sz]ed", re.I)

# Client-side actions the browser performs (navigation and workspace controls).
APP_PAGES: dict[str, str] = {
    "ideas": "/ideas",
    "new_idea": "/ideas/qualify",
    "account": "/account",
    "ai_settings": "/account#ai-key",
    "billing": "/account/billing",
    "messages": "/messages",
    "pitch_reels": "/pitch-reels",
    "docs": "/docs",
    "user_guide": "/docs/guide",
    "api_docs": "/docs/api",
}
# The idea workspace's routes: /ideas/{id}/{aspect}.
IDEA_SECTIONS = (
    "description",
    "business-model-canvas",
    "pitch-deck",
    "product-requirements-document",
    "patent",
    "knowledge-graph",
)

# Spoken-style labels for the activity list; other tools use their catalog title.
TOOL_LABELS: dict[str, str] = {
    "me": "Checking your profile",
    "ideas": "Looking through your ideas",
    "idea": "Reading the idea",
    "create_idea": "Creating the idea",
    "update_idea": "Updating the idea",
    "universal_search": "Searching Manifest",
    "find_similar_ideas": "Checking similar ideas",
    "start_idea_qualification": "Starting the interview",
    "continue_idea_qualification": "Saving your answers",
    "enqueue_background_tasks": "Starting document generation",
    "generation_job": "Checking generation progress",
    "generate_pitch_deck": "Generating the pitch deck",
    "generate_product_requirements_document": "Generating the PRD",
    "generate_provisional_patent": "Drafting the patent",
    "my_inbox": "Checking your inbox",
    "reply_in_inbox": "Sending your reply",
    "send_message": "Sending the message",
    "unread_message_count": "Counting unread messages",
    "put_vault_file": "Saving to your vault",
    "customer_discovery": "Checking the customer research",
    "research_market": "Researching the market",
    "find_prospects": "Researching potential customers",
    "exclude_prospects": "Updating the prospect list",
    "draft_outreach": "Drafting the emails",
    "create_outreach_email_drafts": "Saving drafts to Gmail",
    "save_customer_discovery": "Saving the customer research",
    "delete_idea": "Deleting the idea",
    "toggle_publish_idea": "Changing who can see the idea",
    "invite_collaborator": "Inviting a collaborator",
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, Any]]:
    """Every generated tool by name (the ``_call`` recipe included)."""
    data = json.loads(CATALOG_PATH.read_text())
    return {tool["name"]: tool for tool in data["tools"]}


def _public(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": tool["inputSchema"],
        "destructive": bool(tool["annotations"].get("destructiveHint")),
    }


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def find_tools(query: str, *, limit: int = 6) -> list[dict[str, Any]]:
    """Rank catalog tools for a plain-language need (names weigh more than descriptions)."""
    wanted = _words(query)
    if not wanted:
        return []
    scored: list[tuple[float, str]] = []
    for name, tool in load_catalog().items():
        name_words = _words(name.replace("_", " "))
        text_words = _words(f"{tool.get('title', '')} {tool['description']}")
        score = 3 * len(wanted & name_words) + len(wanted & text_words)
        # Prefix matches catch plurals and stems ("invest" → investment, "deck" → decks).
        score += 0.5 * sum(
            1 for w in wanted for n in name_words | text_words if n != w and n.startswith(w[:5])
        )
        if score:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [_public(load_catalog()[name]) for _, name in scored[:limit]]


def check_arguments(tool: dict[str, Any], args: dict[str, Any]) -> str | None:
    schema = tool["inputSchema"]
    known = schema.get("properties", {})
    unknown = [key for key in args if key not in known]
    if unknown:
        return f"Unknown argument(s): {', '.join(unknown)}."
    missing = [key for key in schema.get("required", []) if args.get(key) is None]
    if missing:
        return f"Missing required argument(s): {', '.join(missing)}."
    return None


def _clip(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    if isinstance(value, dict):  # keep short fields (summaries, status) whole; cut the bulk
        small = {
            k: v
            for k, v in value.items()
            if len(json.dumps(v, ensure_ascii=False, default=str)) <= 500
        }
        budget = MAX_RESULT_CHARS - len(json.dumps(small, ensure_ascii=False, default=str))
        if small and budget > 500:
            rest = {k: v for k, v in value.items() if k not in small}
            preview = json.dumps(rest, ensure_ascii=False, default=str)[:budget]
            return {**small, "truncated": True, "preview": preview}
    return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}


class AuthExpired(Exception):
    """The person's session stopped working mid-conversation."""


@dataclass
class ToolExecutor:
    """Runs catalog tools as the signed-in person over Manifest's public API."""

    api_origin: str
    session_token: str
    client_ip: str | None = None
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.session_token}",
            "user-agent": "manifest-voice",
        }
        edge_secret = (os.getenv("EDGE_SHARED_SECRET") or "").strip()
        if edge_secret:
            headers["x-manifest-edge"] = edge_secret
        if self.client_ip:
            headers["cf-connecting-ip"] = self.client_ip
        return headers

    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_origin,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
                transport=self.transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def run(self, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        """Run one tool; always returns a JSON-able dict the model can read."""
        args = dict(args or {})
        tool = load_catalog().get(name)
        if tool is None:
            return {"error": f"There is no tool called {name}. Use find_tools to look it up."}
        problem = check_arguments(tool, args)
        if problem:
            return {"error": problem, "parameters": tool["inputSchema"]}
        if tool["annotations"].get("destructiveHint") and args.get("confirm") is not True:
            return {
                "needs_confirmation": True,
                "tool": name,
                "would_do": tool["description"],
                "arguments": {k: v for k, v in args.items() if k != "confirm"},
                "next_step": "Say exactly what this will do and ask. Only after a clear yes, "
                "call again with confirm: true.",
            }
        args.pop("confirm", None)
        call = tool["_call"]
        try:
            response = await self._send(call, args)
        except httpx.HTTPError as exc:
            return {
                "error": f"Manifest did not answer ({type(exc).__name__}). Try again in a moment."
            }
        return _interpret(call, response)

    async def _send(self, call: dict[str, Any], args: dict[str, Any]) -> httpx.Response:
        if call["via"] == "graphql":
            variables = {k: args[k] for k in call["variables"] if k in args}
            return await self.client().post(
                "/graphql", json={"query": call["document"], "variables": variables}
            )
        path = re.sub(
            r"{(\w+)}", lambda m: quote(str(args.get(m.group(1), "")), safe=""), call["path"]
        )
        body = None
        if call["method"] not in ("GET", "DELETE"):
            body = {**(call.get("extras") or {})}
            body.update({k: args[k] for k in call["body"] if k in args})
        return await self.client().request(call["method"], path, json=body)


def _interpret(call: dict[str, Any], response: httpx.Response) -> dict[str, Any]:
    """Turn a GraphQL/REST answer into what the model reads (raises AuthExpired on 401)."""
    if response.status_code == 401:
        raise AuthExpired()
    payload: Any
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": f"Manifest answered {response.status_code} without JSON."}
    if call["via"] == "graphql":
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            messages = "; ".join(str(e.get("message", "")) for e in errors if isinstance(e, dict))
            if AUTH_ERROR.search(messages):
                raise AuthExpired()
            return {"error": messages or f"HTTP {response.status_code}"}
        data = (payload or {}).get("data") or {}
        return {call["field"]: _clip(data.get(call["field"]))}
    if response.status_code >= 400:
        return {"status": response.status_code, "error": _clip(payload)}
    return _clip(payload) if isinstance(payload, dict) else {"result": _clip(payload)}


# ---- tool definitions the model sees -------------------------------------------------

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def model_tool_definitions() -> list[dict[str, Any]]:
    """Function definitions (name, description, JSON-schema parameters) sent on every turn."""
    catalog = load_catalog()
    definitions = [
        {
            "name": name,
            "description": catalog[name]["description"],
            "parameters": catalog[name]["inputSchema"],
        }
        for name in CORE_TOOLS
        if name in catalog
    ]
    definitions += [
        {
            "name": "find_tools",
            "description": "Search all of Manifest's abilities (about 130: pitch decks, PRDs, patents, "
            "canvas, collaborators, investments, cap tables, messages, vault, account, privacy, API "
            "keys, integrations, pitch reels and more). Returns matching tools with their parameters; "
            "then run one with use_tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What the person wants to do"}
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "use_tool",
            "description": "Run any Manifest tool found with find_tools. Destructive tools first return "
            "a preview: read it to the person, and only after a clear yes call again with "
            "arguments.confirm = true.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tool name from find_tools"},
                    "arguments": {
                        "type": "object",
                        "description": "Arguments matching its parameters",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "show_in_app",
            "description": "Move the person's screen in the Manifest app: open a page, or one idea "
            "(optionally a section of it). Use it whenever showing helps, e.g. after creating an idea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {"type": "string", "enum": sorted(APP_PAGES)},
                    "idea_id": {
                        "type": "string",
                        "description": "Open this idea instead of a page",
                    },
                    "section": {"type": "string", "enum": list(IDEA_SECTIONS)},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "end_conversation",
            "description": "End the voice conversation when the person says goodbye or asks to stop.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]
    return definitions


def app_path(page: str | None, idea_id: str | None, section: str | None) -> str | None:
    """The in-app path for a show_in_app call, or None when nothing valid was asked for."""
    if idea_id:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", idea_id)
        if not safe_id:
            return None
        return f"/ideas/{safe_id}/{section if section in IDEA_SECTIONS else 'description'}"
    return APP_PAGES.get(page or "")


def spoken_label(name: str) -> str:
    """Short human label for the activity timeline (e.g. "Create idea")."""
    if name in TOOL_LABELS:
        return TOOL_LABELS[name]
    tool = load_catalog().get(name)
    title = (tool or {}).get("title") or name.replace("_", " ")
    return title[:1].upper() + title[1:]


def tool_changes_data(name: str) -> bool:
    tool = load_catalog().get(name)
    return bool(tool) and not tool["annotations"].get("readOnlyHint")
