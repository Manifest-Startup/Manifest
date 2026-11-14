"""REST endpoints for third-party integrations used by the web client (e.g. voice flows)."""

from app.db.database import create_database_client
from app.routes.dependencies import require_user_id
from app.services.identity.guest_workspace import fetch_user_is_guest
from app.services.integrations.github_bootstrap import create_private_repo_for_idea
from app.utils.logger import logger
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


class GitHubBootstrapRequest(BaseModel):
    idea_id: str = Field(..., min_length=1)
    repo_name: str = Field(..., min_length=1, max_length=100)


class GitHubBootstrapResponse(BaseModel):
    html_url: str | None = None
    detail: str | None = None


@router.post("/github/bootstrap", response_model=GitHubBootstrapResponse)
async def github_bootstrap_repo(
    body: GitHubBootstrapRequest, user_id: str = Depends(require_user_id)
):
    """Create a private GitHub repository and seed README from the idea note."""
    db = create_database_client()
    if fetch_user_is_guest(db, user_id):
        raise HTTPException(
            status_code=403, detail="Full account required to create GitHub repositories."
        )

    logger.info(
        "[Integrations] GitHub bootstrap user=%s idea=%s repo=%s",
        user_id,
        body.idea_id,
        body.repo_name,
    )
    html_url, detail, code = create_private_repo_for_idea(
        db=db,
        user_id=user_id,
        idea_id=body.idea_id,
        repo_name=body.repo_name.strip(),
    )
    if html_url:
        return GitHubBootstrapResponse(html_url=html_url)
    if code == "not_found":
        raise HTTPException(status_code=404, detail=detail or "Not found")
    if code == "github_auth":
        raise HTTPException(status_code=400, detail=detail or "GitHub not connected")
    if code == "validation":
        raise HTTPException(status_code=422, detail=detail or "Invalid repository name")
    raise HTTPException(status_code=502, detail=detail or "GitHub request failed")
