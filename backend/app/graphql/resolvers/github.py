"""GraphQL resolvers for the person's own GitHub: connect it, then control it.

Thin wrappers over ``app.services.integrations.github_api`` (logic) and
``github_account`` (the encrypted token). The CLI, agent plugin, hosted MCP
and voice are generated from these fields, so they all get the same actions.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.github import (
    GithubAccount,
    GithubApiResponse,
    GithubBranch,
    GithubComment,
    GithubCommit,
    GithubContent,
    GithubFileCommit,
    GithubIssue,
    GithubPullRequest,
    GithubRelease,
    GithubRepo,
    GithubWorkflow,
    GithubWorkflowRun,
    to_type,
)
from app.services.integrations import github_api as gh_api
from app.services.integrations.github_account import (
    GitHubConnectError,
    github_identity,
    oauth_available,
    save_github_token,
)
from app.services.integrations.github_account import disconnect_github as _forget_github
from app.services.integrations.github_api import GitHubError


def _user_id(info: strawberry.Info) -> str:
    return str(get_current_user_id(info.context["request"]))


def _site_origin() -> str:
    from app.services.web.agent_content import SITE_ORIGIN

    return os.getenv("PUBLIC_SITE_ORIGIN", SITE_ORIGIN).rstrip("/")


def _account(user_id: str) -> GithubAccount:
    identity = github_identity(user_id)
    available = oauth_available()  # decides what "Connect GitHub" does; there is one connection
    if identity is None:
        return GithubAccount(
            connected=False,
            oauth_available=available,
            connect_url=f"{_site_origin()}/account?focusIntegration=github",
            message=(
                "GitHub isn't connected. Open the link and choose Connect GitHub, or run "
                "`manifest github connect` on a computer already signed in to GitHub (the GitHub "
                "CLI or the GitHub plugin): one connection for the app, the CLI, agents and voice."
            ),
        )
    return GithubAccount(
        connected=True,
        oauth_available=available,
        login=identity.login or None,
        name=identity.name,
        avatar_url=identity.avatar_url,
        html_url=identity.html_url,
        scopes=identity.scopes,
        method=identity.method,
        connected_at=identity.connected_at,
        message=f"GitHub is connected as {identity.login}."
        if identity.login
        else "GitHub is connected.",
    )


async def _run(info: strawberry.Info, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run ``fn(client, *args, **kwargs)`` with the person's GitHub client, off the event loop."""
    user_id = _user_id(info)

    def work() -> Any:
        with gh_api.client_for(user_id) as gh:
            return fn(gh, *args, **kwargs)

    try:
        return await asyncio.to_thread(work)
    except GitHubError as exc:
        raise Exception(str(exc)) from None


@strawberry.type
class GithubQuery:
    @strawberry.field
    async def github_account(self, info: strawberry.Info) -> GithubAccount:
        """Whether your GitHub is connected, as whom and with which scopes; when it isn't,
        connectUrl and message say how to connect it."""
        return await asyncio.to_thread(_account, _user_id(info))

    @strawberry.field
    async def github_repos(
        self,
        info: strawberry.Info,
        query: str | None = None,
        owner: str | None = None,
        limit: int | None = 30,
        page: int | None = 1,
    ) -> list[GithubRepo]:
        """Your GitHub repositories, most recently updated first. `query` searches names;
        `owner` lists an organization's or user's repositories."""
        rows = await _run(info, gh_api.list_repos, query=query, owner=owner, limit=limit, page=page)
        return [to_type(GithubRepo, r) for r in rows]

    @strawberry.field
    async def github_repo(self, info: strawberry.Info, repo: str) -> GithubRepo:
        """One repository (`repo` is owner/name or its github.com URL)."""
        return to_type(GithubRepo, await _run(info, gh_api.get_repo, repo))

    @strawberry.field
    async def github_issues(
        self,
        info: strawberry.Info,
        repo: str,
        state: str | None = "open",
        labels: str | None = None,
        assignee: str | None = None,
        limit: int | None = 30,
        page: int | None = 1,
    ) -> list[GithubIssue]:
        """Issues in a repository (not pull requests). state: open, closed or all;
        labels: comma-separated; assignee: a login, `none` or `*`."""
        rows = await _run(
            info,
            gh_api.list_issues,
            repo,
            state=state,
            labels=labels,
            assignee=assignee,
            limit=limit,
            page=page,
        )
        return [to_type(GithubIssue, r) for r in rows]

    @strawberry.field
    async def github_issue(self, info: strawberry.Info, repo: str, number: int) -> GithubIssue:
        """One issue or pull request conversation, with its comments."""
        return to_type(GithubIssue, await _run(info, gh_api.get_issue, repo, number))

    @strawberry.field
    async def github_pull_requests(
        self,
        info: strawberry.Info,
        repo: str,
        state: str | None = "open",
        base: str | None = None,
        limit: int | None = 30,
        page: int | None = 1,
    ) -> list[GithubPullRequest]:
        """Pull requests in a repository. state: open, closed or all."""
        rows = await _run(
            info, gh_api.list_pulls, repo, state=state, base=base, limit=limit, page=page
        )
        return [to_type(GithubPullRequest, r) for r in rows]

    @strawberry.field
    async def github_pull_request(
        self, info: strawberry.Info, repo: str, number: int
    ) -> GithubPullRequest:
        """One pull request: whether it can merge, its size and the files it changes."""
        return to_type(GithubPullRequest, await _run(info, gh_api.get_pull, repo, number))

    @strawberry.field
    async def github_branches(
        self, info: strawberry.Info, repo: str, limit: int | None = 100
    ) -> list[GithubBranch]:
        """Branches in a repository."""
        rows = await _run(info, gh_api.list_branches, repo, limit=limit)
        return [to_type(GithubBranch, r) for r in rows]

    @strawberry.field
    async def github_commits(
        self,
        info: strawberry.Info,
        repo: str,
        branch: str | None = None,
        path: str | None = None,
        limit: int | None = 20,
    ) -> list[GithubCommit]:
        """Recent commits on a branch (default branch if omitted), optionally for one path."""
        rows = await _run(info, gh_api.list_commits, repo, branch=branch, path=path, limit=limit)
        return [to_type(GithubCommit, r) for r in rows]

    @strawberry.field
    async def github_contents(
        self,
        info: strawberry.Info,
        repo: str,
        path: str | None = None,
        ref: str | None = None,
    ) -> GithubContent:
        """Read a file (its text) or list a folder (entries). Empty path = the repository root."""
        return to_type(
            GithubContent, await _run(info, gh_api.get_contents, repo, path=path, ref=ref)
        )

    @strawberry.field
    async def github_workflows(self, info: strawberry.Info, repo: str) -> list[GithubWorkflow]:
        """GitHub Actions workflows in a repository."""
        rows = await _run(info, gh_api.list_workflows, repo)
        return [to_type(GithubWorkflow, r) for r in rows]

    @strawberry.field
    async def github_workflow_runs(
        self,
        info: strawberry.Info,
        repo: str,
        workflow: str | None = None,
        branch: str | None = None,
        status: str | None = None,
        limit: int | None = 10,
    ) -> list[GithubWorkflowRun]:
        """Recent GitHub Actions (CI) runs: which passed, failed or are still running (all
        workflows, or one by file name like ci.yml or id). status: queued, in_progress,
        completed, success, failure…"""
        rows = await _run(
            info,
            gh_api.list_runs,
            repo,
            workflow=workflow,
            branch=branch,
            status=status,
            limit=limit,
        )
        return [to_type(GithubWorkflowRun, r) for r in rows]

    @strawberry.field
    async def github_releases(
        self, info: strawberry.Info, repo: str, limit: int | None = 10
    ) -> list[GithubRelease]:
        """Releases in a repository, newest first."""
        rows = await _run(info, gh_api.list_releases, repo, limit=limit)
        return [to_type(GithubRelease, r) for r in rows]

    @strawberry.field
    async def github_api(self, info: strawberry.Info, path: str) -> GithubApiResponse:
        """Read anything else from GitHub's REST API with your token (GET only), for example
        /repos/owner/name/labels or /notifications. Use githubApiRequest to change things."""
        return to_type(
            GithubApiResponse, await _run(info, gh_api.api_request, method="GET", path=path)
        )


@strawberry.type
class GithubMutation:
    @strawberry.mutation
    async def connect_github(self, info: strawberry.Info, token: str) -> GithubAccount:
        """Connect your GitHub with a personal access token (classic with repo + workflow
        scopes, or fine-grained). It is checked with GitHub and stored encrypted. Prefer
        `manifest github connect` or the app; never paste a token into a chat."""
        from app.services.identity.guest_workspace import fetch_user_is_guest

        user_id = _user_id(info)
        if await asyncio.to_thread(fetch_user_is_guest, info.context["db"], user_id):
            raise Exception("Claim your account first: guest tryouts can't connect GitHub.")
        try:
            await asyncio.to_thread(save_github_token, user_id, token, method="token")
        except GitHubConnectError as exc:
            raise Exception(str(exc)) from None
        return await asyncio.to_thread(_account, user_id)

    @strawberry.mutation
    async def disconnect_github(self, info: strawberry.Info) -> GithubAccount:
        """Forget your GitHub token in Manifest. Also revoke it on GitHub if you no longer use it."""
        user_id = _user_id(info)
        await asyncio.to_thread(_forget_github, user_id)
        return await asyncio.to_thread(_account, user_id)

    @strawberry.mutation
    async def github_create_repo(
        self,
        info: strawberry.Info,
        name: str,
        description: str | None = None,
        private: bool = True,
        org: str | None = None,
        idea_id: str | None = None,
    ) -> GithubRepo:
        """Create a repository (private unless private=false), under you or an organization.
        With ideaId, its README starts from that idea's title and note."""
        readme: str | None = None
        if idea_id:
            from app.services.integrations.github_bootstrap import idea_readme

            readme = await asyncio.to_thread(
                idea_readme, info.context["db"], _user_id(info), idea_id
            )
            if readme is None:
                raise Exception("Idea not found or you do not have access.")
            if not description:
                description = "Manifest idea: " + readme.splitlines()[0].lstrip("# ").strip()
        row = await _run(
            info,
            gh_api.create_repo,
            name=name,
            description=description,
            private=private,
            org=org,
            readme=readme,
        )
        return to_type(GithubRepo, row)

    @strawberry.mutation
    async def github_update_repo(
        self,
        info: strawberry.Info,
        repo: str,
        name: str | None = None,
        description: str | None = None,
        homepage: str | None = None,
        private: bool | None = None,
        archived: bool | None = None,
        default_branch: str | None = None,
        topics: list[str] | None = None,
    ) -> GithubRepo:
        """Rename a repository, change its description, homepage, topics or default branch,
        make it public or private, or archive it."""
        row = await _run(
            info,
            gh_api.update_repo,
            repo,
            name=name,
            description=description,
            homepage=homepage,
            private=private,
            archived=archived,
            default_branch=default_branch,
            topics=topics,
        )
        return to_type(GithubRepo, row)

    @strawberry.mutation
    async def github_delete_repo(self, info: strawberry.Info, repo: str) -> bool:
        """Permanently delete a repository and everything in it (cannot be undone)."""
        return await _run(info, gh_api.delete_repo, repo)

    @strawberry.mutation
    async def github_create_issue(
        self,
        info: strawberry.Info,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> GithubIssue:
        """Open an issue."""
        row = await _run(
            info,
            gh_api.create_issue,
            repo,
            title=title,
            body=body,
            labels=labels,
            assignees=assignees,
        )
        return to_type(GithubIssue, row)

    @strawberry.mutation
    async def github_update_issue(
        self,
        info: strawberry.Info,
        repo: str,
        number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        state_reason: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> GithubIssue:
        """Edit, close (state=closed) or reopen (state=open) an issue or pull request, or set
        its labels and assignees. state_reason: completed, not_planned or reopened."""
        row = await _run(
            info,
            gh_api.update_issue,
            repo,
            number,
            title=title,
            body=body,
            state=state,
            state_reason=state_reason,
            labels=labels,
            assignees=assignees,
        )
        return to_type(GithubIssue, row)

    @strawberry.mutation
    async def github_comment(
        self, info: strawberry.Info, repo: str, number: int, body: str
    ) -> GithubComment:
        """Comment on an issue or pull request."""
        return to_type(GithubComment, await _run(info, gh_api.add_comment, repo, number, body))

    @strawberry.mutation
    async def github_create_pull_request(
        self,
        info: strawberry.Info,
        repo: str,
        title: str,
        head: str,
        base: str | None = None,
        body: str | None = None,
        draft: bool = False,
    ) -> GithubPullRequest:
        """Open a pull request from branch `head` into `base` (the default branch if omitted)."""
        row = await _run(
            info,
            gh_api.create_pull,
            repo,
            title=title,
            head=head,
            base=base,
            body=body,
            draft=draft,
        )
        return to_type(GithubPullRequest, row)

    @strawberry.mutation
    async def github_merge_pull_request(
        self,
        info: strawberry.Info,
        repo: str,
        number: int,
        method: str | None = "squash",
        commit_title: str | None = None,
        commit_message: str | None = None,
    ) -> GithubPullRequest:
        """Merge a pull request. method: squash (default), merge or rebase."""
        row = await _run(
            info,
            gh_api.merge_pull,
            repo,
            number,
            method=method,
            commit_title=commit_title,
            commit_message=commit_message,
        )
        return to_type(GithubPullRequest, row)

    @strawberry.mutation
    async def github_review_pull_request(
        self, info: strawberry.Info, repo: str, number: int, event: str, body: str | None = None
    ) -> bool:
        """Review a pull request. event: APPROVE, REQUEST_CHANGES or COMMENT (needs a body)."""
        return await _run(info, gh_api.review_pull, repo, number, event=event, body=body)

    @strawberry.mutation
    async def github_create_branch(
        self, info: strawberry.Info, repo: str, branch: str, from_ref: str | None = None
    ) -> GithubBranch:
        """Create a branch from another branch, tag or commit (the default branch if omitted)."""
        return to_type(
            GithubBranch, await _run(info, gh_api.create_branch, repo, branch, from_ref=from_ref)
        )

    @strawberry.mutation
    async def github_delete_branch(self, info: strawberry.Info, repo: str, branch: str) -> bool:
        """Delete a branch."""
        return await _run(info, gh_api.delete_branch, repo, branch)

    @strawberry.mutation
    async def github_put_file(
        self,
        info: strawberry.Info,
        repo: str,
        path: str,
        content: str,
        message: str | None = None,
        branch: str | None = None,
    ) -> GithubFileCommit:
        """Create or replace a text file with one commit (on `branch`, or the default branch)."""
        row = await _run(
            info, gh_api.put_file, repo, path=path, content=content, message=message, branch=branch
        )
        return to_type(GithubFileCommit, row)

    @strawberry.mutation
    async def github_delete_file(
        self,
        info: strawberry.Info,
        repo: str,
        path: str,
        message: str | None = None,
        branch: str | None = None,
    ) -> GithubFileCommit:
        """Delete a file with one commit."""
        row = await _run(info, gh_api.delete_file, repo, path=path, message=message, branch=branch)
        return to_type(GithubFileCommit, row)

    @strawberry.mutation
    async def github_run_workflow(
        self,
        info: strawberry.Info,
        repo: str,
        workflow: str,
        ref: str | None = None,
        inputs: str | None = None,
    ) -> bool:
        """Start an Actions workflow that has a workflow_dispatch trigger (file name like
        deploy.yml, or its id). inputs: a JSON object of the workflow's inputs."""
        return await _run(
            info, gh_api.run_workflow, repo, workflow=workflow, ref=ref, inputs=inputs
        )

    @strawberry.mutation
    async def github_rerun_workflow_run(
        self, info: strawberry.Info, repo: str, run_id: str, failed_only: bool = False
    ) -> bool:
        """Re-run an Actions run (or only its failed jobs)."""
        return await _run(info, gh_api.rerun_run, repo, run_id, failed_only=failed_only)

    @strawberry.mutation
    async def github_cancel_workflow_run(
        self, info: strawberry.Info, repo: str, run_id: str
    ) -> bool:
        """Cancel an Actions run that is queued or in progress."""
        return await _run(info, gh_api.cancel_run, repo, run_id)

    @strawberry.mutation
    async def github_create_release(
        self,
        info: strawberry.Info,
        repo: str,
        tag: str,
        name: str | None = None,
        body: str | None = None,
        target: str | None = None,
        draft: bool = False,
        prerelease: bool = False,
    ) -> GithubRelease:
        """Publish a release for a tag (created from `target` if it doesn't exist).
        Without a body, GitHub writes the release notes."""
        row = await _run(
            info,
            gh_api.create_release,
            repo,
            tag=tag,
            name=name,
            body=body,
            target=target,
            draft=draft,
            prerelease=prerelease,
        )
        return to_type(GithubRelease, row)

    @strawberry.mutation
    async def github_api_request(
        self, info: strawberry.Info, method: str, path: str, body: str | None = None
    ) -> GithubApiResponse:
        """Do anything else in GitHub's REST API with your token: labels, milestones,
        collaborators, stars, gists, notifications, branch protection… method: GET, POST,
        PUT, PATCH or DELETE; path on api.github.com; body: JSON."""
        row = await _run(info, gh_api.api_request, method=method, path=path, body=body)
        return to_type(GithubApiResponse, row)
