"""GraphQL types for a person's own GitHub (``github*`` fields).

Shapes come from ``app.services.integrations.github_api``; ``to_type`` builds
any of these from such a dict (unknown keys are dropped).
"""

from __future__ import annotations

from typing import Any, TypeVar

import strawberry


@strawberry.type
class GithubAccount:
    """Whether GitHub is connected and as whom (the token itself is never returned).
    ``method``: "oauth" (Sign in with GitHub) or "token" (personal access token)."""

    connected: bool
    oauth_available: bool
    login: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    scopes: list[str] = strawberry.field(default_factory=list)
    method: str | None = None
    connected_at: str | None = None
    connect_url: str | None = None
    message: str | None = None


@strawberry.type
class GithubRepo:
    full_name: str
    name: str
    owner: str
    private: bool
    html_url: str
    description: str | None = None
    default_branch: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    archived: bool = False
    fork: bool = False
    homepage: str | None = None
    topics: list[str] = strawberry.field(default_factory=list)
    pushed_at: str | None = None
    updated_at: str | None = None


@strawberry.type
class GithubComment:
    id: str
    body: str
    html_url: str
    author: str | None = None
    created_at: str | None = None


@strawberry.type
class GithubIssue:
    number: int
    title: str
    state: str
    html_url: str
    body: str | None = None
    author: str | None = None
    labels: list[str] = strawberry.field(default_factory=list)
    assignees: list[str] = strawberry.field(default_factory=list)
    comments_count: int = 0
    is_pull_request: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    comments: list[GithubComment] = strawberry.field(default_factory=list)


@strawberry.type
class GithubChangedFile:
    filename: str
    status: str
    additions: int = 0
    deletions: int = 0


@strawberry.type
class GithubPullRequest:
    """``state``: open, closed or merged."""

    number: int
    title: str
    state: str
    head: str
    base: str
    html_url: str
    body: str | None = None
    author: str | None = None
    draft: bool = False
    merged: bool = False
    mergeable: bool | None = None
    mergeable_state: str | None = None
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    files: list[GithubChangedFile] = strawberry.field(default_factory=list)


@strawberry.type
class GithubBranch:
    name: str
    sha: str
    protected: bool = False


@strawberry.type
class GithubCommit:
    sha: str
    message: str
    html_url: str
    author: str | None = None
    date: str | None = None


@strawberry.type
class GithubContentEntry:
    name: str
    path: str
    type: str
    size: int | None = None


@strawberry.type
class GithubContent:
    """A file (``text`` holds it when it is UTF-8 and under 1 MB) or a folder (``entries``)."""

    type: str
    path: str
    html_url: str
    sha: str | None = None
    size: int | None = None
    text: str | None = None
    note: str | None = None
    entries: list[GithubContentEntry] = strawberry.field(default_factory=list)


@strawberry.type
class GithubFileCommit:
    path: str
    commit_sha: str
    html_url: str
    created: bool = False


@strawberry.type
class GithubWorkflow:
    id: str
    name: str
    path: str
    state: str
    html_url: str


@strawberry.type
class GithubWorkflowRun:
    id: str
    name: str
    workflow_id: str
    html_url: str
    branch: str | None = None
    event: str | None = None
    status: str | None = None
    conclusion: str | None = None
    created_at: str | None = None


@strawberry.type
class GithubRelease:
    id: str
    tag: str
    html_url: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    published_at: str | None = None


@strawberry.type
class GithubApiResponse:
    """Raw answer from api.github.com: HTTP status and the JSON body as text."""

    status: int
    ok: bool
    body: str
    truncated: bool = False


T = TypeVar("T")

_NESTED: dict[type, dict[str, type]] = {
    GithubIssue: {"comments": GithubComment},
    GithubPullRequest: {"files": GithubChangedFile},
    GithubContent: {"entries": GithubContentEntry},
}


def to_type(cls: type[T], data: dict[str, Any]) -> T:
    fields = set(getattr(cls, "__dataclass_fields__", {}))
    kwargs = {k: v for k, v in data.items() if k in fields}
    for key, child in _NESTED.get(cls, {}).items():
        if key in kwargs:
            kwargs[key] = [to_type(child, item) for item in kwargs[key] or []]
    return cls(**kwargs)
