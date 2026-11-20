"""Tests for Manifest API Client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from manifest_mcp.client import ManifestClient


class TestManifestClient:
    """Test suite for ManifestClient."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return ManifestClient(base_url="http://test-api.local", auth_token="test-token")

    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test client initializes with correct configuration."""
        client = ManifestClient(
            base_url="http://localhost:8000",
            auth_token="my-token",
            api_key="manifest_sk_test",
            internal_secret="loop-secret",
            timeout=60.0,
        )
        assert client.base_url == "http://localhost:8000"
        assert client.graphql_url == "http://localhost:8000/graphql"
        assert client.auth_token == "my-token"
        assert client.api_key == "manifest_sk_test"
        assert client.internal_secret == "loop-secret"
        assert client.timeout == 60.0

    @pytest.mark.asyncio
    async def test_client_strips_trailing_slash(self):
        """Test client strips trailing slash from base URL."""
        client = ManifestClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    @pytest.mark.asyncio
    async def test_execute_success(self, client):
        """Test successful GraphQL query execution."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"ideas": []}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.execute("query { ideas { ideaId } }")

            assert result == {"ideas": []}

    @pytest.mark.asyncio
    async def test_execute_with_variables(self, client):
        """Test GraphQL query execution with variables."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"idea": {"ideaId": "123"}}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.execute(
                    "query GetIdea($id: String!) { idea(ideaId: $id) { ideaId } }",
                    variables={"id": "123"},
                )

            assert result == {"idea": {"ideaId": "123"}}
            call_args = mock_post.call_args
            assert call_args[1]["json"]["variables"] == {"id": "123"}

    @pytest.mark.asyncio
    async def test_execute_graphql_errors(self, client):
        """Test handling of GraphQL errors."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": None,
            "errors": [{"message": "Not found"}, {"message": "Invalid ID"}],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                with pytest.raises(Exception) as exc_info:
                    await client.execute("query { idea { ideaId } }")

            assert "Not found" in str(exc_info.value)
            assert "Invalid ID" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_ideas(self, client):
        """Test fetching ideas list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "ideas": [{"ideaId": "1", "title": "Idea 1"}, {"ideaId": "2", "title": "Idea 2"}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                ideas = await client.get_ideas()

            assert len(ideas) == 2
            assert ideas[0]["ideaId"] == "1"
            assert ideas[1]["title"] == "Idea 2"

    @pytest.mark.asyncio
    async def test_get_idea(self, client):
        """Test fetching a single idea."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "idea": {
                    "ideaId": "123",
                    "title": "Test Idea",
                    "description": "A test description",
                    "businessModelCanvas": "BMC content",
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                idea = await client.get_idea("123")

            assert idea["ideaId"] == "123"
            assert idea["title"] == "Test Idea"
            assert idea["businessModelCanvas"] == "BMC content"

    @pytest.mark.asyncio
    async def test_create_idea(self, client):
        """Test creating a new idea."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "createIdea": {
                    "ideaId": "new-id",
                    "title": "New Idea",
                    "description": "Description",
                    "createdAt": "2024-01-01T00:00:00Z",
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                idea = await client.create_idea("New Idea", "Description")

            assert idea["ideaId"] == "new-id"
            assert idea["title"] == "New Idea"

    @pytest.mark.asyncio
    async def test_update_idea(self, client):
        """Test updating an idea."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "updateIdea": {
                    "ideaId": "123",
                    "title": "Updated Title",
                    "description": "Updated Description",
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                idea = await client.update_idea("123", title="Updated Title")

            assert idea["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_idea(self, client):
        """Test deleting an idea."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"deleteIdea": True}}
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                success = await client.delete_idea("123")

            assert success is True

    @pytest.mark.asyncio
    async def test_run_background_tasks(self, client):
        """Test running background tasks to generate BMC."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "runBackgroundTasks": {
                    "ideaId": "123",
                    "businessModelCanvas": "Generated BMC content",
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.run_background_tasks("123")

            assert result["businessModelCanvas"] == "Generated BMC content"

    @pytest.mark.asyncio
    async def test_get_public_feed(self, client):
        """Test fetching public ideas feed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"publicIdeasFeed": [{"ideaId": "1", "title": "Public Idea", "upvoteCount": 5}]}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                feed = await client.get_public_feed(limit=10, offset=0)

            assert len(feed) == 1
            assert feed[0]["upvoteCount"] == 5

    @pytest.mark.asyncio
    async def test_sync_website_issues(self):
        """Test calling the website issue sync REST endpoint."""
        client = ManifestClient(
            base_url="http://localhost:8000",
            internal_secret="loop-secret",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "target_url": "https://manifeststartup.com",
            "github": {"created_count": 2},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.sync_website_issues(
                    "https://manifeststartup.com",
                    max_pages=3,
                    max_issues=2,
                    dry_run=True,
                )

            assert result["github"]["created_count"] == 2
            call_args = mock_post.call_args
            assert (
                call_args[0][0] == "http://localhost:8000/api/internal/website-testing/sync-issues"
            )
            assert call_args[1]["headers"]["X-Manifest-Agent-Key"] == "loop-secret"

    @pytest.mark.asyncio
    async def test_sync_website_issues_requires_internal_secret(self):
        """Test website issue sync refuses to run without the internal agent secret."""
        client = ManifestClient(base_url="http://localhost:8000")

        async with client:
            with pytest.raises(Exception) as exc_info:
                await client.sync_website_issues("https://manifeststartup.com")

        assert "MANIFEST_AGENT_LOOP_SECRET" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_survey_insights(self):
        """Test calling the survey insights REST endpoint."""
        client = ManifestClient(
            base_url="http://localhost:8000",
            internal_secret="loop-secret",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"total_responses": 14, "window_days": 90}
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.get_survey_insights(
                    window_days=90, include_issue_candidates=True
                )

            call_args = mock_post.call_args
            assert call_args[0][0] == "http://localhost:8000/api/internal/survey-ops/summary"
            assert call_args[1]["json"]["include_issue_candidates"] is True
            assert call_args[1]["headers"]["X-Manifest-Agent-Key"] == "loop-secret"
            assert result["total_responses"] == 14

    @pytest.mark.asyncio
    async def test_sync_survey_issues(self):
        """Test calling the survey issue sync REST endpoint."""
        client = ManifestClient(
            base_url="http://localhost:8000",
            internal_secret="loop-secret",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"github": {"created_count": 2}, "issue_candidates": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.sync_survey_issues(window_days=30, max_issues=4, dry_run=True)

            call_args = mock_post.call_args
            assert call_args[0][0] == "http://localhost:8000/api/internal/survey-ops/sync-issues"
            assert call_args[1]["json"]["window_days"] == 30
            assert call_args[1]["json"]["max_issues"] == 4
            assert call_args[1]["json"]["dry_run"] is True
            assert call_args[1]["headers"]["X-Manifest-Agent-Key"] == "loop-secret"
            assert result["github"]["created_count"] == 2

    @pytest.mark.asyncio
    async def test_post_production_signal(self):
        """Test calling the production signal ingest endpoint."""
        client = ManifestClient(
            base_url="http://localhost:8000",
            internal_secret="loop-secret",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "fingerprint": "graphql_mutation_failed:/idea:ERR",
            "window_start": "2026-04-04T12:00:00+00:00",
            "event_count": 3,
            "github_eligible": False,
            "github_issue_created": False,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.post_production_signal(
                    event_name="graphql_mutation_failed",
                    route="/idea",
                    severity="error",
                    error_code="ERR",
                )

            call_args = mock_post.call_args
            assert call_args[0][0] == "http://localhost:8000/api/internal/production-signals/event"
            assert call_args[1]["json"]["event_name"] == "graphql_mutation_failed"
            assert call_args[1]["headers"]["X-Manifest-Agent-Key"] == "loop-secret"
            assert result["event_count"] == 3

    @pytest.mark.asyncio
    async def test_upvote_idea(self, client):
        """Test upvoting an idea."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"upvoteIdea": {"success": True, "isUpvoted": True, "upvoteCount": 10}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.upvote_idea("123")

            assert result["success"] is True
            assert result["upvoteCount"] == 10

    @pytest.mark.asyncio
    async def test_follow_user(self, client):
        """Test following a user."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"followUser": {"success": True, "isFollowing": True}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.follow_user("user-123")

            assert result["success"] is True
            assert result["isFollowing"] is True

    @pytest.mark.asyncio
    async def test_get_portfolio(self, client):
        """Test fetching investment portfolio."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "myPortfolio": [
                    {
                        "investmentId": "inv-1",
                        "ideaId": "idea-1",
                        "ideaTitle": "Startup A",
                        "investmentType": "cash",
                        "totalAmount": 10000,
                        "equityPercentage": 5.0,
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                portfolio = await client.get_portfolio()

            assert len(portfolio) == 1
            assert portfolio[0]["totalAmount"] == 10000

    @pytest.mark.asyncio
    async def test_create_investment(self, client):
        """Test creating an investment."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "createInvestment": {
                    "investmentId": "new-inv",
                    "ideaId": "idea-1",
                    "investmentType": "cash",
                    "amount": 5000,
                    "equityPercentage": 2.5,
                    "status": "pending",
                }
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                result = await client.create_investment(
                    idea_id="idea-1", investment_type="cash", amount=5000, equity_percentage=2.5
                )

            assert result["investmentId"] == "new-inv"
            assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_find_similar_ideas(self, client):
        """Test finding similar ideas."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "findSimilarIdeas": [{"ideaId": "1", "title": "Similar Idea", "similarity": 0.85}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            async with client:
                ideas = await client.find_similar_ideas("AI-powered analytics")

            assert len(ideas) == 1
            assert ideas[0]["similarity"] == 0.85

    @pytest.mark.asyncio
    async def test_http_error_handling(self, client):
        """Test handling of HTTP errors."""
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_request = MagicMock()
            mock_request.url = "http://test-api.local/graphql"
            mock_post.side_effect = httpx.HTTPStatusError(
                message="Server Error",
                request=mock_request,
                response=MagicMock(
                    status_code=500, request=mock_request, reason_phrase="Internal Server Error"
                ),
            )

            async with client:
                with pytest.raises(Exception) as exc_info:
                    await client.execute("query { me { userId } }")

            assert "500" in str(exc_info.value)
            assert "http://test-api.local/graphql" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_error_auth_hint_for_graphql_routes(self, client):
        """GraphQL auth failures should tell the user which token to check."""
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_request = MagicMock()
            mock_request.url = "http://test-api.local/graphql"
            mock_post.side_effect = httpx.HTTPStatusError(
                message="Unauthorized",
                request=mock_request,
                response=MagicMock(
                    status_code=401, request=mock_request, reason_phrase="Unauthorized"
                ),
            )

            async with client:
                with pytest.raises(Exception) as exc_info:
                    await client.execute("query { me { userId } }")

            assert "MANIFEST_API_TOKEN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_http_error_route_hint_for_not_found(self, client):
        """Missing routes should hint that the API base URL or deployment may be wrong."""
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_request = MagicMock()
            mock_request.url = "http://test-api.local/api/internal/missing"
            mock_post.side_effect = httpx.HTTPStatusError(
                message="Not Found",
                request=mock_request,
                response=MagicMock(
                    status_code=404, request=mock_request, reason_phrase="Not Found"
                ),
            )

            async with client:
                with pytest.raises(Exception) as exc_info:
                    await client.post_json("/api/internal/missing", {})

            assert "MANIFEST_API_URL" in str(exc_info.value)
            assert "requested route" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, client):
        """Test handling of connection errors."""
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_request = MagicMock()
            mock_request.url = "http://test-api.local/graphql"
            mock_post.side_effect = httpx.RequestError("Connection refused", request=mock_request)

            async with client:
                with pytest.raises(Exception) as exc_info:
                    await client.execute("query { me { userId } }")

            assert "Failed to connect" in str(exc_info.value)
            assert "MANIFEST_API_URL" in str(exc_info.value)
