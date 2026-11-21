"""Everything a person can do in their own GitHub, through their connected token.

Repositories, issues, pull requests (review and merge), branches, files
(commit straight to a branch), commits, Actions workflows and runs, releases,
and a raw ``api_request`` for anything else in GitHub's REST API. The app,
the ``manifest`` CLI, the agent plugin and voice all reach these through the
``github*`` GraphQL fields, so they stay identical everywhere.

Calls are synchronous (resolvers run them in a thread). Results are plain
dicts shaped for ``app.graphql.types.github``. Every failure raises
:class:`GitHubError` with a sentence a person can act on.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any
from urllib.parse import quote

import httpx
from app.services.integrations.github_account import GITHUB_API, load_github_token

_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_BRANCH_RE = re.compile(r"^(?!/)(?!.*\.\.)(?!.*//)[^\s~^:?*\[\\]{1,250}(?<!/)(?<!\.lock)$")
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
MAX_FILE_BYTES = 1_000_000
MAX_API_RESPONSE_CHARS = 200_000
NOT_CONNECTED = (
    "Connect GitHub first: Settings → Integrations → Connect GitHub in the app, "
    "or run `manifest github connect` in a terminal."
)


class GitHubError(Exception):
    """A GitHub call failed; the message is safe to show the person."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- input checks


def check_repo(repo: str) -> str:
    """``owner/name``; also accepts a github.com URL."""
    value = (repo or "").strip()
    value = (
        re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", value).removesuffix(".git").strip("/")
    )
    if not _REPO_RE.match(value):
        raise GitHubError("Name the repository as owner/name, for example octocat/hello-world.")
    return value


def check_name(name: str, what: str = "Repository name") -> str:
    value = (name or "").strip()
    if not _NAME_RE.match(value):
        raise GitHubError(f"{what} must be 1-100 letters, numbers, dots, hyphens or underscores.")
    return value


def check_branch(branch: str) -> str:
    value = (branch or "").strip()
    if not _BRANCH_RE.match(value):
        raise GitHubError(f"'{value}' isn't a valid branch name.")
    return value


def check_path(path: str) -> str:
    """A file path inside a repository (no leading slash, no '..')."""
    value = (path or "").strip().strip("/")
    parts = value.split("/") if value else []
    if any(p in ("", ".", "..") for p in parts) or "\\" in value or len(value) > 1000:
        raise GitHubError("Give the file path inside the repository, for example docs/README.md.")
    return value


def _quote_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/")) if path else ""


def check_api_path(path: str) -> str:
    """A path on api.github.com, for example /repos/octocat/hello-world/topics."""
    value = (path or "").strip()
    if value.startswith(GITHUB_API):
        value = value[len(GITHUB_API) :]
    if (
        not value.startswith("/")
        or value.startswith("//")
        or "://" in value
        or ".." in value
        or "\\" in value
        or any(c.isspace() for c in value)
        or len(value) > 2000
    ):
        raise GitHubError("Give an api.github.com path starting with /, for example /user/repos.")
    return value


def _clamp(limit: int | None, default: int = 30) -> int:
    return max(1, min(int(limit or default), 100))


def _json_arg(raw: str | None, what: str) -> Any:
    if raw is None or not str(raw).strip():
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise GitHubError(f'{what} must be JSON, for example {{"key": "value"}}.') from exc


# --------------------------------------------------------------------------- client


class GitHubClient:
    """A thin GitHub REST client bound to one person's token."""

    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            base_url=GITHUB_API,
            timeout=30.0,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Manifest",
            },
        )

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def raw(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
    ) -> httpx.Response:
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            return self._client.request(
                method, path, params=clean or None, json=body if body is not None else None
            )
        except httpx.HTTPError as exc:
            raise GitHubError("Could not reach GitHub. Try again in a moment.") from exc

    def call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: Any = None,
        ok: tuple[int, ...] = (200, 201, 202, 204),
    ) -> Any:
        resp = self.raw(method, path, params=params, body=body)
        if resp.status_code not in ok:
            raise _error_from(resp)
        if resp.status_code == 204 or not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text


def _error_from(resp: httpx.Response) -> GitHubError:
    status = resp.status_code
    message = ""
    try:
        data = resp.json()
        if isinstance(data, dict):
            message = str(data.get("message") or "").strip().rstrip(".")
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                details = [
                    str(e.get("message") or e.get("code") or e) if isinstance(e, dict) else str(e)
                    for e in errors[:3]
                ]
                message = f"{message}: {'; '.join(details)}" if message else "; ".join(details)
    except ValueError:
        pass
    if status == 401:
        return GitHubError(
            "GitHub no longer accepts your token. Reconnect GitHub in Account → Integrations "
            "or with `manifest github connect`.",
            status,
        )
    if status == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
        return GitHubError(
            "GitHub's rate limit is used up for now. Try again in a few minutes.", status
        )
    if status == 403:
        hint = (
            " Deleting a repository needs the delete_repo scope "
            "(`gh auth refresh -s delete_repo`, then `manifest github connect`)."
            if resp.request.method == "DELETE"
            and re.fullmatch(r"/repos/[^/]+/[^/]+", resp.request.url.path)
            else " Reconnect GitHub with more access if you need it."
        )
        return GitHubError(
            f"GitHub refused: {message or 'your token lacks permission for this'}.{hint}", status
        )
    if status == 404:
        return GitHubError(
            "GitHub says that doesn't exist, or your token can't see it "
            "(private repositories need the repo scope).",
            status,
        )
    return GitHubError(f"GitHub answered {status}: {message or 'request failed'}.", status)


def client_for(user_id: str, *, transport: httpx.BaseTransport | None = None) -> GitHubClient:
    token = load_github_token(str(user_id))
    if not token:
        raise GitHubError(NOT_CONNECTED)
    return GitHubClient(token, transport=transport)


# --------------------------------------------------------------------------- shapes


def _login(user: Any) -> str | None:
    return user.get("login") if isinstance(user, dict) else None


def repo_shape(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_name": r.get("full_name") or "",
        "name": r.get("name") or "",
        "owner": _login(r.get("owner")) or "",
        "description": r.get("description"),
        "private": bool(r.get("private")),
        "html_url": r.get("html_url") or "",
        "default_branch": r.get("default_branch"),
        "language": r.get("language"),
        "stars": int(r.get("stargazers_count") or 0),
        "forks": int(r.get("forks_count") or 0),
        "open_issues": int(r.get("open_issues_count") or 0),
        "archived": bool(r.get("archived")),
        "fork": bool(r.get("fork")),
        "homepage": r.get("homepage") or None,
        "topics": list(r.get("topics") or []),
        "pushed_at": r.get("pushed_at"),
        "updated_at": r.get("updated_at"),
    }


def comment_shape(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(c.get("id") or ""),
        "author": _login(c.get("user")),
        "body": c.get("body") or "",
        "html_url": c.get("html_url") or "",
        "created_at": c.get("created_at"),
    }


def issue_shape(i: dict[str, Any], comments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "number": int(i.get("number") or 0),
        "title": i.get("title") or "",
        "state": i.get("state") or "",
        "body": i.get("body"),
        "author": _login(i.get("user")),
        "labels": [
            (lbl.get("name") if isinstance(lbl, dict) else str(lbl))
            for lbl in i.get("labels") or []
        ],
        "assignees": [a for a in (_login(u) for u in i.get("assignees") or []) if a],
        "comments_count": int(i.get("comments") or 0),
        "html_url": i.get("html_url") or "",
        "is_pull_request": "pull_request" in i,
        "created_at": i.get("created_at"),
        "updated_at": i.get("updated_at"),
        "closed_at": i.get("closed_at"),
        "comments": [comment_shape(c) for c in comments or []],
    }


def pull_shape(p: dict[str, Any], files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "number": int(p.get("number") or 0),
        "title": p.get("title") or "",
        "state": "merged" if p.get("merged_at") else (p.get("state") or ""),
        "body": p.get("body"),
        "author": _login(p.get("user")),
        "head": (p.get("head") or {}).get("ref") or "",
        "base": (p.get("base") or {}).get("ref") or "",
        "draft": bool(p.get("draft")),
        "merged": bool(p.get("merged") or p.get("merged_at")),
        "mergeable": p.get("mergeable"),
        "mergeable_state": p.get("mergeable_state"),
        "additions": p.get("additions"),
        "deletions": p.get("deletions"),
        "changed_files": p.get("changed_files"),
        "html_url": p.get("html_url") or "",
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
        "files": [
            {
                "filename": f.get("filename") or "",
                "status": f.get("status") or "",
                "additions": int(f.get("additions") or 0),
                "deletions": int(f.get("deletions") or 0),
            }
            for f in files or []
        ],
    }


def commit_shape(c: dict[str, Any]) -> dict[str, Any]:
    inner = c.get("commit") or {}
    author = inner.get("author") or {}
    return {
        "sha": c.get("sha") or "",
        "message": inner.get("message") or "",
        "author": _login(c.get("author")) or author.get("name"),
        "date": author.get("date"),
        "html_url": c.get("html_url") or "",
    }


def run_shape(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r.get("id") or ""),
        "name": r.get("name") or r.get("display_title") or "",
        "workflow_id": str(r.get("workflow_id") or ""),
        "branch": r.get("head_branch"),
        "event": r.get("event"),
        "status": r.get("status"),
        "conclusion": r.get("conclusion"),
        "html_url": r.get("html_url") or "",
        "created_at": r.get("created_at"),
    }


def release_shape(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(r.get("id") or ""),
        "tag": r.get("tag_name") or "",
        "name": r.get("name"),
        "body": r.get("body"),
        "draft": bool(r.get("draft")),
        "prerelease": bool(r.get("prerelease")),
        "html_url": r.get("html_url") or "",
        "published_at": r.get("published_at"),
    }


# --------------------------------------------------------------------------- repositories


def list_repos(
    gh: GitHubClient,
    *,
    query: str | None = None,
    owner: str | None = None,
    limit: int | None = None,
    page: int | None = None,
) -> list[dict[str, Any]]:
    per_page, page = _clamp(limit), max(1, int(page or 1))
    if query and query.strip():
        q = f"{query.strip()} in:name fork:true"
        if owner:
            q += f" user:{check_name(owner, 'Owner')}"
        else:
            me = gh.call("GET", "/user")
            q += f" user:{me.get('login')}"
        data = gh.call(
            "GET", "/search/repositories", params={"q": q, "per_page": per_page, "page": page}
        )
        return [repo_shape(r) for r in (data or {}).get("items") or []]
    if owner:
        name = check_name(owner, "Owner")
        resp = gh.raw(
            "GET",
            f"/orgs/{name}/repos",
            params={"type": "all", "sort": "updated", "per_page": per_page, "page": page},
        )
        if resp.status_code == 404:
            data = gh.call(
                "GET",
                f"/users/{name}/repos",
                params={"sort": "updated", "per_page": per_page, "page": page},
            )
        elif resp.status_code != 200:
            raise _error_from(resp)
        else:
            data = resp.json()
        return [repo_shape(r) for r in data or []]
    data = gh.call(
        "GET",
        "/user/repos",
        params={
            "sort": "updated",
            "affiliation": "owner,collaborator,organization_member",
            "per_page": per_page,
            "page": page,
        },
    )
    return [repo_shape(r) for r in data or []]


def get_repo(gh: GitHubClient, repo: str) -> dict[str, Any]:
    return repo_shape(gh.call("GET", f"/repos/{check_repo(repo)}"))


def create_repo(
    gh: GitHubClient,
    *,
    name: str,
    description: str | None = None,
    private: bool = True,
    org: str | None = None,
    readme: str | None = None,
) -> dict[str, Any]:
    """Create a repository (private by default); seed README.md when ``readme`` is given."""
    payload: dict[str, Any] = {
        "name": check_name(name),
        "private": bool(private),
        "auto_init": readme is None,
    }
    if description:
        payload["description"] = description[:350]
    path = f"/orgs/{check_name(org, 'Organization')}/repos" if org else "/user/repos"
    created = gh.call("POST", path, body=payload)
    if readme is not None and created.get("full_name"):
        gh.call(
            "PUT",
            f"/repos/{created['full_name']}/contents/README.md",
            body={
                "message": "Seed README from Manifest",
                "content": base64.b64encode(readme.encode("utf-8")).decode("ascii"),
            },
        )
    return repo_shape(created)


def update_repo(
    gh: GitHubClient,
    repo: str,
    *,
    name: str | None = None,
    description: str | None = None,
    homepage: str | None = None,
    private: bool | None = None,
    archived: bool | None = None,
    default_branch: str | None = None,
    topics: list[str] | None = None,
) -> dict[str, Any]:
    full = check_repo(repo)
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = check_name(name)
    if description is not None:
        body["description"] = description[:350]
    if homepage is not None:
        body["homepage"] = homepage
    if private is not None:
        body["private"] = bool(private)
    if archived is not None:
        body["archived"] = bool(archived)
    if default_branch is not None:
        body["default_branch"] = check_branch(default_branch)
    updated = (
        gh.call("PATCH", f"/repos/{full}", body=body) if body else gh.call("GET", f"/repos/{full}")
    )
    if topics is not None:
        gh.call(
            "PUT",
            f"/repos/{updated.get('full_name') or full}/topics",
            body={"names": [t.strip().lower() for t in topics if t.strip()]},
        )
        updated["topics"] = [t.strip().lower() for t in topics if t.strip()]
    return repo_shape(updated)


def delete_repo(gh: GitHubClient, repo: str) -> bool:
    gh.call("DELETE", f"/repos/{check_repo(repo)}")
    return True


# --------------------------------------------------------------------------- issues


def list_issues(
    gh: GitHubClient,
    repo: str,
    *,
    state: str | None = None,
    labels: str | None = None,
    assignee: str | None = None,
    limit: int | None = None,
    page: int | None = None,
) -> list[dict[str, Any]]:
    data = gh.call(
        "GET",
        f"/repos/{check_repo(repo)}/issues",
        params={
            "state": (state or "open").lower(),
            "labels": labels,
            "assignee": assignee,
            "per_page": _clamp(limit),
            "page": max(1, int(page or 1)),
        },
    )
    return [issue_shape(i) for i in data or [] if "pull_request" not in i]


def get_issue(gh: GitHubClient, repo: str, number: int) -> dict[str, Any]:
    full = check_repo(repo)
    issue = gh.call("GET", f"/repos/{full}/issues/{int(number)}")
    comments = gh.call(
        "GET", f"/repos/{full}/issues/{int(number)}/comments", params={"per_page": 50}
    )
    return issue_shape(issue, comments or [])


def create_issue(
    gh: GitHubClient,
    repo: str,
    *,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    if not (title or "").strip():
        raise GitHubError("Give the issue a title.")
    payload: dict[str, Any] = {"title": title.strip()[:256]}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees
    return issue_shape(gh.call("POST", f"/repos/{check_repo(repo)}/issues", body=payload))


def update_issue(
    gh: GitHubClient,
    repo: str,
    number: int,
    *,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    state_reason: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    """Edit, close or reopen an issue or pull request (they share numbers)."""
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title[:256]
    if body is not None:
        payload["body"] = body
    if state is not None:
        if state.lower() not in ("open", "closed"):
            raise GitHubError("state is open or closed.")
        payload["state"] = state.lower()
    if state_reason is not None:
        payload["state_reason"] = state_reason
    if labels is not None:
        payload["labels"] = labels
    if assignees is not None:
        payload["assignees"] = assignees
    if not payload:
        raise GitHubError("Say what to change: title, body, state, labels or assignees.")
    return issue_shape(
        gh.call("PATCH", f"/repos/{check_repo(repo)}/issues/{int(number)}", body=payload)
    )


def add_comment(gh: GitHubClient, repo: str, number: int, body: str) -> dict[str, Any]:
    if not (body or "").strip():
        raise GitHubError("The comment is empty.")
    return comment_shape(
        gh.call(
            "POST", f"/repos/{check_repo(repo)}/issues/{int(number)}/comments", body={"body": body}
        )
    )


# --------------------------------------------------------------------------- pull requests


def list_pulls(
    gh: GitHubClient,
    repo: str,
    *,
    state: str | None = None,
    base: str | None = None,
    limit: int | None = None,
    page: int | None = None,
) -> list[dict[str, Any]]:
    data = gh.call(
        "GET",
        f"/repos/{check_repo(repo)}/pulls",
        params={
            "state": (state or "open").lower(),
            "base": base,
            "per_page": _clamp(limit),
            "page": max(1, int(page or 1)),
        },
    )
    return [pull_shape(p) for p in data or []]


def get_pull(gh: GitHubClient, repo: str, number: int) -> dict[str, Any]:
    full = check_repo(repo)
    pull = gh.call("GET", f"/repos/{full}/pulls/{int(number)}")
    files = gh.call("GET", f"/repos/{full}/pulls/{int(number)}/files", params={"per_page": 100})
    return pull_shape(pull, files or [])


def create_pull(
    gh: GitHubClient,
    repo: str,
    *,
    title: str,
    head: str,
    base: str | None = None,
    body: str | None = None,
    draft: bool = False,
) -> dict[str, Any]:
    full = check_repo(repo)
    if not (title or "").strip():
        raise GitHubError("Give the pull request a title.")
    target = base or gh.call("GET", f"/repos/{full}").get("default_branch") or "main"
    payload: dict[str, Any] = {
        "title": title.strip()[:256],
        "head": head.strip(),
        "base": check_branch(target),
        "draft": bool(draft),
    }
    if body:
        payload["body"] = body
    return pull_shape(gh.call("POST", f"/repos/{full}/pulls", body=payload))


def merge_pull(
    gh: GitHubClient,
    repo: str,
    number: int,
    *,
    method: str | None = None,
    commit_title: str | None = None,
    commit_message: str | None = None,
) -> dict[str, Any]:
    full = check_repo(repo)
    merge_method = (method or "squash").lower()
    if merge_method not in ("merge", "squash", "rebase"):
        raise GitHubError("method is merge, squash or rebase.")
    payload: dict[str, Any] = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message
    gh.call("PUT", f"/repos/{full}/pulls/{int(number)}/merge", body=payload)
    return pull_shape(gh.call("GET", f"/repos/{full}/pulls/{int(number)}"))


def review_pull(
    gh: GitHubClient, repo: str, number: int, *, event: str, body: str | None = None
) -> bool:
    verdict = (event or "").strip().upper().replace(" ", "_")
    verdict = {
        "APPROVED": "APPROVE",
        "REQUEST": "REQUEST_CHANGES",
        "CHANGES": "REQUEST_CHANGES",
    }.get(verdict, verdict)
    if verdict not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
        raise GitHubError("event is APPROVE, REQUEST_CHANGES or COMMENT.")
    if verdict != "APPROVE" and not (body or "").strip():
        raise GitHubError("Say what the review comment is.")
    payload: dict[str, Any] = {"event": verdict}
    if body:
        payload["body"] = body
    gh.call("POST", f"/repos/{check_repo(repo)}/pulls/{int(number)}/reviews", body=payload)
    return True


# --------------------------------------------------------------------------- branches and commits


def list_branches(gh: GitHubClient, repo: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    full = check_repo(repo)
    data = gh.call("GET", f"/repos/{full}/branches", params={"per_page": _clamp(limit, 100)})
    return [
        {
            "name": b.get("name") or "",
            "sha": (b.get("commit") or {}).get("sha") or "",
            "protected": bool(b.get("protected")),
        }
        for b in data or []
    ]


def _ref_sha(gh: GitHubClient, full: str, ref: str) -> str:
    commit = gh.call("GET", f"/repos/{full}/commits/{quote(ref, safe='')}")
    sha = (commit or {}).get("sha")
    if not sha:
        raise GitHubError(f"Couldn't find {ref} in {full}.")
    return sha


def create_branch(
    gh: GitHubClient, repo: str, branch: str, *, from_ref: str | None = None
) -> dict[str, Any]:
    full = check_repo(repo)
    name = check_branch(branch)
    source = from_ref or gh.call("GET", f"/repos/{full}").get("default_branch") or "main"
    sha = _ref_sha(gh, full, source)
    gh.call("POST", f"/repos/{full}/git/refs", body={"ref": f"refs/heads/{name}", "sha": sha})
    return {"name": name, "sha": sha, "protected": False}


def delete_branch(gh: GitHubClient, repo: str, branch: str) -> bool:
    gh.call(
        "DELETE", f"/repos/{check_repo(repo)}/git/refs/heads/{_quote_path(check_branch(branch))}"
    )
    return True


def list_commits(
    gh: GitHubClient,
    repo: str,
    *,
    branch: str | None = None,
    path: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    data = gh.call(
        "GET",
        f"/repos/{check_repo(repo)}/commits",
        params={
            "sha": branch,
            "path": check_path(path) if path else None,
            "per_page": _clamp(limit, 20),
        },
    )
    return [commit_shape(c) for c in data or []]


# --------------------------------------------------------------------------- files


def get_contents(
    gh: GitHubClient, repo: str, *, path: str | None = None, ref: str | None = None
) -> dict[str, Any]:
    """A file's text, or a folder's entries."""
    full, clean = check_repo(repo), check_path(path or "")
    data = gh.call("GET", f"/repos/{full}/contents/{_quote_path(clean)}", params={"ref": ref})
    if isinstance(data, list):
        return {
            "type": "dir",
            "path": clean,
            "sha": None,
            "size": None,
            "text": None,
            "html_url": f"https://github.com/{full}/tree/{ref or 'HEAD'}/{clean}".rstrip("/"),
            "entries": [
                {
                    "name": e.get("name") or "",
                    "path": e.get("path") or "",
                    "type": e.get("type") or "",
                    "size": e.get("size"),
                }
                for e in data
            ],
        }
    size = int(data.get("size") or 0)
    text: str | None = None
    note: str | None = None
    if data.get("encoding") == "base64" and data.get("content") and size <= MAX_FILE_BYTES:
        raw = base64.b64decode(data["content"])
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            note = "This is a binary file, so its text isn't shown."
    elif size > MAX_FILE_BYTES:
        note = "This file is over 1 MB, so its text isn't shown."
    return {
        "type": data.get("type") or "file",
        "path": data.get("path") or clean,
        "sha": data.get("sha"),
        "size": size,
        "text": text,
        "note": note,
        "html_url": data.get("html_url") or "",
        "entries": [],
    }


def _existing_sha(gh: GitHubClient, full: str, path: str, branch: str | None) -> str | None:
    resp = gh.raw("GET", f"/repos/{full}/contents/{_quote_path(path)}", params={"ref": branch})
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise _error_from(resp)
    data = resp.json()
    if isinstance(data, list):
        raise GitHubError(f"{path} is a folder, not a file.")
    return data.get("sha")


def put_file(
    gh: GitHubClient,
    repo: str,
    *,
    path: str,
    content: str,
    message: str | None = None,
    branch: str | None = None,
) -> dict[str, Any]:
    """Create or replace a file with one commit."""
    full, clean = check_repo(repo), check_path(path)
    if not clean:
        raise GitHubError("Give the file path inside the repository.")
    sha = _existing_sha(gh, full, clean, branch)
    payload: dict[str, Any] = {
        "message": (message or f"{'Update' if sha else 'Add'} {clean}")[:500],
        "content": base64.b64encode((content or "").encode("utf-8")).decode("ascii"),
    }
    if branch:
        payload["branch"] = check_branch(branch)
    if sha:
        payload["sha"] = sha
    data = gh.call("PUT", f"/repos/{full}/contents/{_quote_path(clean)}", body=payload)
    commit = (data or {}).get("commit") or {}
    return {
        "path": clean,
        "commit_sha": commit.get("sha") or "",
        "html_url": ((data or {}).get("content") or {}).get("html_url")
        or commit.get("html_url")
        or "",
        "created": sha is None,
    }


def delete_file(
    gh: GitHubClient, repo: str, *, path: str, message: str | None = None, branch: str | None = None
) -> dict[str, Any]:
    full, clean = check_repo(repo), check_path(path)
    sha = _existing_sha(gh, full, clean, branch)
    if not sha:
        raise GitHubError(f"{clean} doesn't exist{' on ' + branch if branch else ''}.")
    payload: dict[str, Any] = {"message": (message or f"Delete {clean}")[:500], "sha": sha}
    if branch:
        payload["branch"] = check_branch(branch)
    data = gh.call("DELETE", f"/repos/{full}/contents/{_quote_path(clean)}", body=payload)
    commit = (data or {}).get("commit") or {}
    return {
        "path": clean,
        "commit_sha": commit.get("sha") or "",
        "html_url": commit.get("html_url") or "",
        "created": False,
    }


# --------------------------------------------------------------------------- Actions


def list_workflows(gh: GitHubClient, repo: str) -> list[dict[str, Any]]:
    data = gh.call("GET", f"/repos/{check_repo(repo)}/actions/workflows", params={"per_page": 100})
    return [
        {
            "id": str(w.get("id") or ""),
            "name": w.get("name") or "",
            "path": w.get("path") or "",
            "state": w.get("state") or "",
            "html_url": w.get("html_url") or "",
        }
        for w in (data or {}).get("workflows") or []
    ]


def list_runs(
    gh: GitHubClient,
    repo: str,
    *,
    workflow: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    full = check_repo(repo)
    path = (
        f"/repos/{full}/actions/workflows/{quote(workflow.strip(), safe='')}/runs"
        if workflow
        else f"/repos/{full}/actions/runs"
    )
    data = gh.call(
        "GET", path, params={"branch": branch, "status": status, "per_page": _clamp(limit, 10)}
    )
    return [run_shape(r) for r in (data or {}).get("workflow_runs") or []]


def run_workflow(
    gh: GitHubClient, repo: str, *, workflow: str, ref: str | None = None, inputs: str | None = None
) -> bool:
    """Start a workflow that has a ``workflow_dispatch`` trigger (id or file name like ci.yml)."""
    full = check_repo(repo)
    if not (workflow or "").strip():
        raise GitHubError("Name the workflow: its file name (ci.yml) or id.")
    target = ref or gh.call("GET", f"/repos/{full}").get("default_branch") or "main"
    payload: dict[str, Any] = {"ref": target}
    parsed = _json_arg(inputs, "inputs")
    if parsed:
        if not isinstance(parsed, dict):
            raise GitHubError("inputs must be a JSON object.")
        payload["inputs"] = {k: str(v) for k, v in parsed.items()}
    gh.call(
        "POST",
        f"/repos/{full}/actions/workflows/{quote(workflow.strip(), safe='')}/dispatches",
        body=payload,
    )
    return True


def rerun_run(gh: GitHubClient, repo: str, run_id: str, *, failed_only: bool = False) -> bool:
    suffix = "rerun-failed-jobs" if failed_only else "rerun"
    gh.call("POST", f"/repos/{check_repo(repo)}/actions/runs/{int(run_id)}/{suffix}")
    return True


def cancel_run(gh: GitHubClient, repo: str, run_id: str) -> bool:
    gh.call("POST", f"/repos/{check_repo(repo)}/actions/runs/{int(run_id)}/cancel")
    return True


# --------------------------------------------------------------------------- releases


def list_releases(gh: GitHubClient, repo: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    data = gh.call(
        "GET", f"/repos/{check_repo(repo)}/releases", params={"per_page": _clamp(limit, 10)}
    )
    return [release_shape(r) for r in data or []]


def create_release(
    gh: GitHubClient,
    repo: str,
    *,
    tag: str,
    name: str | None = None,
    body: str | None = None,
    target: str | None = None,
    draft: bool = False,
    prerelease: bool = False,
    generate_notes: bool = True,
) -> dict[str, Any]:
    if not (tag or "").strip():
        raise GitHubError("Give the release a tag, for example v1.0.0.")
    payload: dict[str, Any] = {
        "tag_name": tag.strip(),
        "draft": bool(draft),
        "prerelease": bool(prerelease),
        "generate_release_notes": bool(generate_notes) and not body,
    }
    if name:
        payload["name"] = name
    if body:
        payload["body"] = body
    if target:
        payload["target_commitish"] = target
    return release_shape(gh.call("POST", f"/repos/{check_repo(repo)}/releases", body=payload))


# --------------------------------------------------------------------------- anything else


def api_request(
    gh: GitHubClient, *, method: str, path: str, body: str | None = None
) -> dict[str, Any]:
    """Call any api.github.com endpoint with the person's token (for what the
    named operations don't cover: labels, milestones, collaborators, gists,
    notifications, stars, secrets metadata, …). Returns the status and JSON text."""
    verb = (method or "GET").strip().upper()
    if verb not in _METHODS:
        raise GitHubError("method is GET, POST, PUT, PATCH or DELETE.")
    resp = gh.raw(verb, check_api_path(path), body=_json_arg(body, "body"))
    text = resp.text or ""
    truncated = len(text) > MAX_API_RESPONSE_CHARS
    return {
        "status": resp.status_code,
        "ok": 200 <= resp.status_code < 300,
        "body": text[:MAX_API_RESPONSE_CHARS],
        "truncated": truncated,
    }
