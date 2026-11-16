"""
Manifest API Client - HTTP client for communicating with Manifest backend.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ManifestClient:
    """HTTP client for Manifest GraphQL API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        auth_token: str | None = None,
        api_key: str | None = None,
        internal_secret: str | None = None,
        timeout: float = 30.0,
        *,
        user_agent: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.graphql_url = f"{self.base_url}/graphql"
        self.auth_token = auth_token
        self.api_key = api_key
        self.internal_secret = internal_secret
        self.timeout = timeout
        self.user_agent = user_agent
        # A custom transport lets tests (and the CLI end-to-end test) talk to an ASGI app.
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ManifestClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # JSON requests set their own Content-Type; multipart uploads need theirs.
            headers: dict[str, str] = {"Accept": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            if self.user_agent:
                headers["User-Agent"] = self.user_agent
            self._client = httpx.AsyncClient(
                timeout=self.timeout, headers=headers, transport=self.transport
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _build_http_error_message(
        self,
        error: httpx.HTTPStatusError,
        *,
        auth_mode: str,
    ) -> str:
        """Build an actionable HTTP error message for MCP users."""
        response = error.response
        request = getattr(response, "request", None)
        request_url = getattr(request, "url", self.graphql_url)
        reason = getattr(response, "reason_phrase", "") or ""
        status_code = response.status_code

        message = f"Manifest API request to {request_url} failed with HTTP {status_code}"
        if reason:
            message = f"{message} {reason}"

        hints: list[str] = []
        if status_code in (401, 403):
            if auth_mode == "api_key":
                hints.append("Check MANIFEST_API_KEY for this API-key route.")
            else:
                hints.append("Check MANIFEST_API_TOKEN or your session/JWT credentials.")
        elif status_code == 404:
            hints.append(
                f"Check MANIFEST_API_URL ({self.base_url}) and confirm this Manifest deployment exposes the requested route."
            )

        if hints:
            return f"{message}. {' '.join(hints)}"
        return message

    def _build_request_error_message(self, error: httpx.RequestError) -> str:
        """Build an actionable connectivity error message for MCP users."""
        request = getattr(error, "request", None)
        request_url = getattr(request, "url", self.graphql_url)
        return (
            f"Failed to connect to Manifest API at {request_url}. "
            f"Check MANIFEST_API_URL, confirm the backend is reachable, and then retry. "
            f"Original error: {error}"
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Send one authenticated request to ``base_url + path`` and return the raw response.

        Unlike :meth:`execute` this never raises on HTTP status, so callers (the CLI)
        can show the backend's own error body. Connection failures still raise.
        """
        client = await self._ensure_client()
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}{path}"
        try:
            return await client.request(method.upper(), url, json=json, params=params, files=files)
        except httpx.RequestError as e:
            raise Exception(self._build_request_error_message(e)) from e

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST a GraphQL document and return the whole response body (``data`` and ``errors``)."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        response = await self.request("POST", "/graphql", json=payload)
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            response.raise_for_status()
            raise Exception(f"Unexpected response from {self.graphql_url}: {response.text[:200]}")
        if response.status_code >= 400 and not body.get("errors"):
            detail = body.get("detail") or response.reason_phrase
            body = {"errors": [{"message": f"HTTP {response.status_code}: {detail}"}]}
        return body

    async def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GraphQL query/mutation."""
        client = await self._ensure_client()

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await client.post(self.graphql_url, json=payload)
            response.raise_for_status()
            data = response.json()

            if "errors" in data and data["errors"]:
                error_messages = [e.get("message", str(e)) for e in data["errors"]]
                raise Exception(f"GraphQL errors: {'; '.join(error_messages)}")

            return data.get("data", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            raise Exception(self._build_http_error_message(e, auth_mode="token")) from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise Exception(self._build_request_error_message(e)) from e

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        use_api_key: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute an authenticated JSON POST against a REST endpoint."""
        client = await self._ensure_client()
        token = self.api_key if use_api_key and self.api_key else self.auth_token
        headers = dict(extra_headers or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            response = await client.post(f"{self.base_url}{path}", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            auth_mode = "api_key" if use_api_key else "token"
            raise Exception(self._build_http_error_message(e, auth_mode=auth_mode)) from e
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise Exception(self._build_request_error_message(e)) from e

    async def get_ideas(self) -> list[dict[str, Any]]:
        """Get all ideas for the current user."""
        query = """
        query GetIdeas {
            ideas {
                ideaId
                title
                description
                createdAt
                isPublished
                generatedAssetCount
            }
        }
        """
        result = await self.execute(query)
        return result.get("ideas", [])

    async def get_idea(self, idea_id: str) -> dict[str, Any]:
        """Get a specific idea by ID."""
        query = """
        query GetIdea($ideaId: String!) {
            idea(ideaId: $ideaId) {
                ideaId
                title
                description
                createdAt
                pitchDeck
                productRequirementsDocument
                provisionalPatent
                businessModelCanvas
            }
        }
        """
        result = await self.execute(query, {"ideaId": idea_id})
        return result.get("idea", {})

    async def create_idea(self, title: str, description: str | None = None) -> dict[str, Any]:
        """Create a new idea."""
        mutation = """
        mutation CreateIdea($title: String!, $description: String) {
            createIdea(title: $title, description: $description) {
                ideaId
                title
                description
                createdAt
            }
        }
        """
        result = await self.execute(mutation, {"title": title, "description": description})
        return result.get("createIdea", {})

    async def update_idea(
        self, idea_id: str, title: str | None = None, description: str | None = None
    ) -> dict[str, Any]:
        """Update an existing idea."""
        mutation = """
        mutation UpdateIdea($ideaId: String!, $title: String, $description: String) {
            updateIdea(ideaId: $ideaId, title: $title, description: $description) {
                ideaId
                title
                description
            }
        }
        """
        variables = {"ideaId": idea_id}
        if title is not None:
            variables["title"] = title
        if description is not None:
            variables["description"] = description

        result = await self.execute(mutation, variables)
        return result.get("updateIdea", {})

    async def delete_idea(self, idea_id: str) -> bool:
        """Delete an idea."""
        mutation = """
        mutation DeleteIdea($ideaId: String!) {
            deleteIdea(ideaId: $ideaId)
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("deleteIdea", False)

    async def run_background_tasks(self, idea_id: str) -> dict[str, Any]:
        """Run AI background tasks for an idea (generates BMC, etc.)."""
        mutation = """
        mutation RunBackgroundTasks($ideaId: String!) {
            runBackgroundTasks(ideaId: $ideaId) {
                ideaId
                businessModelCanvas
            }
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("runBackgroundTasks", {})

    async def generate_pitch_deck(self, idea_id: str) -> str:
        """Generate a pitch deck for an idea."""
        mutation = """
        mutation GeneratePitchDeck($ideaId: String!) {
            generatePitchDeck(ideaId: $ideaId)
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("generatePitchDeck", "")

    async def generate_prd(self, idea_id: str) -> str:
        """Generate a Product Requirements Document for an idea."""
        mutation = """
        mutation GeneratePRD($ideaId: String!) {
            generateProductRequirementsDocument(ideaId: $ideaId)
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("generateProductRequirementsDocument", "")

    async def generate_patent(self, idea_id: str) -> str:
        """Generate a provisional patent draft for an idea."""
        mutation = """
        mutation GeneratePatent($ideaId: String!) {
            generateProvisionalPatent(ideaId: $ideaId)
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("generateProvisionalPatent", "")

    async def get_public_feed(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """Get the public ideas feed."""
        query = """
        query PublicFeed($limit: Int!, $offset: Int!) {
            publicIdeasFeed(limit: $limit, offset: $offset) {
                ideaId
                title
                description
                createdAt
                upvoteCount
                isUpvoted
                author {
                    userId
                    fullName
                }
            }
        }
        """
        result = await self.execute(query, {"limit": limit, "offset": offset})
        return result.get("publicIdeasFeed", [])

    async def sync_website_issues(
        self,
        target_url: str,
        *,
        max_pages: int = 6,
        max_issues: int = 6,
        create_github_issues: bool = True,
        dry_run: bool = False,
        github_repo: str | None = None,
        extra_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Trigger the internal Manifest website audit and optional GitHub issue sync."""
        payload = {
            "target_url": target_url,
            "max_pages": max_pages,
            "max_issues": max_issues,
            "create_github_issues": create_github_issues,
            "dry_run": dry_run,
            "github_repo": github_repo,
            "extra_labels": extra_labels or [],
        }
        if not self.internal_secret:
            raise Exception("Internal website issue sync requires MANIFEST_AGENT_LOOP_SECRET.")

        return await self.post_json(
            "/api/internal/website-testing/sync-issues",
            payload,
            extra_headers={"X-Manifest-Agent-Key": self.internal_secret},
        )

    async def get_survey_insights(
        self,
        *,
        window_days: int = 90,
        include_issue_candidates: bool = False,
        max_issues: int = 6,
        min_theme_count: int = 2,
    ) -> dict[str, Any]:
        """Fetch aggregate survey insights from the internal survey feedback loop."""
        if not self.internal_secret:
            raise Exception("Internal survey insights require MANIFEST_AGENT_LOOP_SECRET.")

        return await self.post_json(
            "/api/internal/survey-ops/summary",
            {
                "window_days": window_days,
                "include_issue_candidates": include_issue_candidates,
                "max_issues": max_issues,
                "min_theme_count": min_theme_count,
            },
            extra_headers={"X-Manifest-Agent-Key": self.internal_secret},
        )

    async def sync_survey_issues(
        self,
        *,
        window_days: int = 90,
        max_issues: int = 6,
        min_theme_count: int = 2,
        create_github_issues: bool = True,
        dry_run: bool = False,
        github_repo: str | None = None,
        extra_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Trigger the internal survey issue sync workflow and optionally create GitHub issues."""
        if not self.internal_secret:
            raise Exception("Internal survey issue sync requires MANIFEST_AGENT_LOOP_SECRET.")

        return await self.post_json(
            "/api/internal/survey-ops/sync-issues",
            {
                "window_days": window_days,
                "max_issues": max_issues,
                "min_theme_count": min_theme_count,
                "create_github_issues": create_github_issues,
                "dry_run": dry_run,
                "github_repo": github_repo,
                "extra_labels": extra_labels or [],
            },
            extra_headers={"X-Manifest-Agent-Key": self.internal_secret},
        )

    async def post_production_signal(
        self,
        *,
        event_name: str,
        route: str | None = None,
        severity: str = "warn",
        error_code: str | None = None,
        session_id: str | None = None,
        sample: str | None = None,
        create_github_issue: bool = False,
    ) -> dict[str, Any]:
        """Ingest a deduped production signal; optional GitHub issue when thresholds are met."""
        if not self.internal_secret:
            raise Exception("Production signals require MANIFEST_AGENT_LOOP_SECRET.")

        return await self.post_json(
            "/api/internal/production-signals/event",
            {
                "event_name": event_name,
                "route": route,
                "severity": severity,
                "error_code": error_code,
                "session_id": session_id,
                "sample": sample,
                "create_github_issue": create_github_issue,
            },
            extra_headers={"X-Manifest-Agent-Key": self.internal_secret},
        )

    async def upvote_idea(self, idea_id: str) -> dict[str, Any]:
        """Upvote an idea."""
        mutation = """
        mutation UpvoteIdea($ideaId: String!) {
            upvoteIdea(ideaId: $ideaId) {
                success
                isUpvoted
                upvoteCount
            }
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("upvoteIdea", {})

    async def toggle_upvote(self, idea_id: str) -> dict[str, Any]:
        """Toggle upvote on an idea."""
        mutation = """
        mutation ToggleUpvote($ideaId: String!) {
            toggleUpvote(ideaId: $ideaId) {
                success
                isUpvoted
                upvoteCount
            }
        }
        """
        result = await self.execute(mutation, {"ideaId": idea_id})
        return result.get("toggleUpvote", {})

    async def follow_user(self, user_id: str) -> dict[str, Any]:
        """Follow a user."""
        mutation = """
        mutation FollowUser($userId: String!) {
            followUser(userId: $userId) {
                success
                isFollowing
            }
        }
        """
        result = await self.execute(mutation, {"userId": user_id})
        return result.get("followUser", {})

    async def unfollow_user(self, user_id: str) -> dict[str, Any]:
        """Unfollow a user."""
        mutation = """
        mutation UnfollowUser($userId: String!) {
            unfollowUser(userId: $userId) {
                success
                isFollowing
            }
        }
        """
        result = await self.execute(mutation, {"userId": user_id})
        return result.get("unfollowUser", {})

    async def get_portfolio(self) -> list[dict[str, Any]]:
        """Get the current user's investment portfolio."""
        query = """
        query MyPortfolio {
            myPortfolio {
                investmentId
                ideaId
                ideaTitle
                investmentType
                totalAmount
                equityPercentage
                status
                createdAt
            }
        }
        """
        result = await self.execute(query)
        return result.get("myPortfolio", [])

    async def create_investment(
        self, idea_id: str, investment_type: str, amount: float, equity_percentage: float
    ) -> dict[str, Any]:
        """Create an investment in an idea."""
        mutation = """
        mutation CreateInvestment(
            $ideaId: String!,
            $investmentType: String!,
            $amount: Float!,
            $equityPercentage: Float!
        ) {
            createInvestment(
                ideaId: $ideaId,
                investmentType: $investmentType,
                amount: $amount,
                equityPercentage: $equityPercentage
            ) {
                investmentId
                ideaId
                investmentType
                amount
                equityPercentage
                status
            }
        }
        """
        result = await self.execute(
            mutation,
            {
                "ideaId": idea_id,
                "investmentType": investment_type,
                "amount": amount,
                "equityPercentage": equity_percentage,
            },
        )
        return result.get("createInvestment", {})

    async def get_cap_table(self, idea_id: str) -> list[dict[str, Any]]:
        """Get the capitalization table for an idea."""
        query = """
        query IdeaCapTable($ideaId: String!) {
            ideaCapTable(ideaId: $ideaId) {
                userId
                userName
                equityPercentage
                investmentType
            }
        }
        """
        result = await self.execute(query, {"ideaId": idea_id})
        return result.get("ideaCapTable", [])

    async def find_similar_ideas(self, description: str) -> list[dict[str, Any]]:
        """Find ideas similar to a given description."""
        query = """
        query FindSimilarIdeas($description: String!) {
            findSimilarIdeas(description: $description) {
                ideaId
                title
                description
                similarity
            }
        }
        """
        result = await self.execute(query, {"description": description})
        return result.get("findSimilarIdeas", [])
