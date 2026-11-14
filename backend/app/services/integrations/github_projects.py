"""Optional GitHub Projects (v2) hooks after issue creation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from app.utils.logger import logger


async def _graphql(
    client: httpx.AsyncClient,
    *,
    token: str,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    response = await client.post(
        "https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ManifestGitHubProject/1.0",
        },
        json={"query": query, "variables": variables},
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload.get("data") or {}


async def add_issue_to_project_v2(
    client: httpx.AsyncClient,
    *,
    issue_node_id: str,
    project_node_id: str | None = None,
    start_field_id: str | None = None,
    end_field_id: str | None = None,
    roadmap_days: int = 7,
) -> dict[str, Any] | None:
    """Attach a created issue to a Project v2 board and optionally set Start/End date fields."""
    token = os.getenv("MANIFEST_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    project_node_id = project_node_id or os.getenv("MANIFEST_GITHUB_PROJECT_NODE_ID")
    if not token or not project_node_id:
        return None

    start_field_id = start_field_id or os.getenv("MANIFEST_GITHUB_PROJECT_START_FIELD_ID")
    end_field_id = end_field_id or os.getenv("MANIFEST_GITHUB_PROJECT_END_FIELD_ID")
    try:
        days = max(1, int(os.getenv("MANIFEST_GITHUB_PROJECT_ROADMAP_DAYS", str(roadmap_days))))
    except ValueError:
        days = roadmap_days

    add_mutation = """
    mutation ($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = await _graphql(
        client,
        token=token,
        query=add_mutation,
        variables={"projectId": project_node_id, "contentId": issue_node_id},
    )
    add_payload = data.get("addProjectV2ItemById") or {}
    item = add_payload.get("item") or add_payload.get("projectV2Item") or {}
    item_id = item.get("id")
    if not item_id:
        logger.warning("[GitHubProject] addProjectV2ItemById returned no item id")
        return None

    today = datetime.now(timezone.utc).date()
    start_s = today.isoformat()
    end_s = (today + timedelta(days=days)).isoformat()

    update_mutation = """
    mutation ($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
      updateProjectV2ItemFieldValue(
        input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: $value}
      ) {
        projectV2Item { id }
      }
    }
    """

    for field_id, date_value in ((start_field_id, start_s), (end_field_id, end_s)):
        if not field_id:
            continue
        await _graphql(
            client,
            token=token,
            query=update_mutation,
            variables={
                "projectId": project_node_id,
                "itemId": item_id,
                "fieldId": field_id,
                "value": {"date": date_value},
            },
        )

    return {"project_item_id": item_id, "start_date": start_s, "end_date": end_s}


async def maybe_add_created_issues_to_project(
    client: httpx.AsyncClient,
    created_issues: list[dict[str, Any]],
) -> None:
    """Best-effort Project v2 linkage for issues that include node_id."""
    if not os.getenv("MANIFEST_GITHUB_PROJECT_NODE_ID"):
        return
    for issue in created_issues:
        node_id = issue.get("node_id")
        if not node_id:
            continue
        try:
            await add_issue_to_project_v2(client, issue_node_id=node_id)
        except Exception as exc:  # pragma: no cover - network/service dependent
            logger.warning("[GitHubProject] Failed to attach issue to project: %s", exc)
