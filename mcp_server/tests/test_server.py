"""Tests for Manifest MCP Server."""

import os
from unittest.mock import AsyncMock, patch

import pytest
from manifest_mcp.server import (
    audit_website_and_create_github_issues,
    create_idea,
    create_server,
    create_survey_feedback_github_issues,
    delete_idea,
    discover_ideas,
    find_similar_ideas,
    follow_user,
    generate_business_model,
    generate_patent,
    generate_pitch_deck,
    generate_prd,
    get_cap_table,
    get_client,
    get_idea,
    get_portfolio,
    get_server_status,
    invest_in_idea,
    list_ideas,
    summarize_survey_feedback,
    toggle_upvote,
    unfollow_user,
    update_idea,
    upvote_idea,
)


class TestServerConfiguration:
    """Test server configuration and setup."""
    
    def test_create_server_returns_fastmcp_instance(self):
        """Test that create_server returns a FastMCP instance."""
        server = create_server()
        assert server is not None
        assert hasattr(server, 'run')
    
    def test_get_client_uses_environment_variables(self):
        """Test that get_client reads from environment variables."""
        with patch.dict(os.environ, {
            "MANIFEST_API_URL": "http://custom-api.local",
            "MANIFEST_API_TOKEN": "custom-token",
            "MANIFEST_AGENT_LOOP_SECRET": "loop-secret",
        }):
            client = get_client()
            assert client.base_url == "http://custom-api.local"
            assert client.auth_token == "custom-token"
            assert client.internal_secret == "loop-secret"
    
    def test_get_client_default_values(self):
        """Test get_client uses defaults when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MANIFEST_API_URL", None)
            os.environ.pop("MANIFEST_API_TOKEN", None)
            os.environ.pop("MANIFEST_AGENT_LOOP_SECRET", None)
            client = get_client()
            assert client.base_url == "http://localhost:8000"
            assert client.auth_token is None
            assert client.internal_secret is None


class TestIdeaManagementTools:
    """Test idea management MCP tools."""
    
    @pytest.mark.asyncio
    async def test_list_ideas_empty(self):
        """Test list_ideas with no ideas."""
        mock_client = AsyncMock()
        mock_client.get_ideas.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await list_ideas()
        
        assert "No ideas found" in result
        assert "create_idea" in result
    
    @pytest.mark.asyncio
    async def test_list_ideas_with_ideas(self):
        """Test list_ideas with existing ideas."""
        mock_client = AsyncMock()
        mock_client.get_ideas.return_value = [
            {"ideaId": "1", "title": "Idea One", "description": "First idea", "createdAt": "2024-01-01"},
            {"ideaId": "2", "title": "Idea Two", "description": None, "createdAt": "2024-01-02"}
        ]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await list_ideas()
        
        assert "Found 2 idea(s)" in result
        assert "Idea One" in result
        assert "Idea Two" in result
    
    @pytest.mark.asyncio
    async def test_get_idea_found(self):
        """Test get_idea with existing idea."""
        mock_client = AsyncMock()
        mock_client.get_idea.return_value = {
            "ideaId": "123",
            "title": "Test Idea",
            "description": "A test",
            "createdAt": "2024-01-01",
            "businessModelCanvas": "BMC content",
            "pitchDeck": "Pitch deck content..."
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await get_idea("123")
        
        assert "Test Idea" in result
        assert "Business Model Canvas" in result
        assert "BMC content" in result
    
    @pytest.mark.asyncio
    async def test_get_idea_not_found(self):
        """Test get_idea with non-existent idea."""
        mock_client = AsyncMock()
        mock_client.get_idea.return_value = {}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await get_idea("nonexistent")
        
        assert "not found" in result
    
    @pytest.mark.asyncio
    async def test_create_idea_success(self):
        """Test creating a new idea."""
        mock_client = AsyncMock()
        mock_client.create_idea.return_value = {
            "ideaId": "new-123",
            "title": "New Startup",
            "createdAt": "2024-01-01"
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await create_idea("New Startup", "A great idea")
        
        assert "Successfully created" in result
        assert "New Startup" in result
        assert "generate_business_model" in result
    
    @pytest.mark.asyncio
    async def test_create_idea_without_description(self):
        """Test creating idea without description shows tip."""
        mock_client = AsyncMock()
        mock_client.create_idea.return_value = {
            "ideaId": "new-123",
            "title": "New Startup",
            "createdAt": "2024-01-01"
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await create_idea("New Startup")
        
        assert "update_idea" in result
    
    @pytest.mark.asyncio
    async def test_update_idea_success(self):
        """Test updating an idea."""
        mock_client = AsyncMock()
        mock_client.update_idea.return_value = {
            "ideaId": "123",
            "title": "Updated Title"
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await update_idea("123", title="Updated Title")
        
        assert "Successfully updated" in result
    
    @pytest.mark.asyncio
    async def test_update_idea_no_changes(self):
        """Test update_idea with no changes provided."""
        result = await update_idea("123")
        assert "Please provide" in result
    
    @pytest.mark.asyncio
    async def test_delete_idea_success(self):
        """Test deleting an idea."""
        mock_client = AsyncMock()
        mock_client.delete_idea.return_value = True
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await delete_idea("123")
        
        assert "Successfully deleted" in result
    
    @pytest.mark.asyncio
    async def test_delete_idea_failure(self):
        """Test delete_idea when deletion fails."""
        mock_client = AsyncMock()
        mock_client.delete_idea.return_value = False
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await delete_idea("123")
        
        assert "Failed to delete" in result


class TestDocumentGenerationTools:
    """Test AI document generation MCP tools."""
    
    @pytest.mark.asyncio
    async def test_generate_business_model_success(self):
        """Test generating business model canvas."""
        mock_client = AsyncMock()
        mock_client.run_background_tasks.return_value = {
            "ideaId": "123",
            "businessModelCanvas": "# Business Model Canvas\n\n## Value Propositions..."
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await generate_business_model("123")
        
        assert "Successfully generated" in result
        assert "Value Propositions" in result
    
    @pytest.mark.asyncio
    async def test_generate_business_model_pending(self):
        """Test generate_business_model when result is pending."""
        mock_client = AsyncMock()
        mock_client.run_background_tasks.return_value = {"ideaId": "123"}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await generate_business_model("123")
        
        assert "started" in result
        assert "get_idea" in result
    
    @pytest.mark.asyncio
    async def test_generate_pitch_deck_success(self):
        """Test generating pitch deck."""
        mock_client = AsyncMock()
        mock_client.generate_pitch_deck.return_value = "# Pitch Deck\n\n## Problem..."
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await generate_pitch_deck("123")
        
        assert "Successfully generated" in result
        assert "Problem" in result
    
    @pytest.mark.asyncio
    async def test_generate_prd_success(self):
        """Test generating PRD."""
        mock_client = AsyncMock()
        mock_client.generate_prd.return_value = "# Product Requirements\n\n## Overview..."
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await generate_prd("123")
        
        assert "Successfully generated" in result
    
    @pytest.mark.asyncio
    async def test_generate_patent_success(self):
        """Test generating patent draft."""
        mock_client = AsyncMock()
        mock_client.generate_patent.return_value = "# Provisional Patent\n\n## Title..."
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await generate_patent("123")
        
        assert "Successfully generated" in result


class TestMarketplaceTools:
    """Test marketplace and discovery MCP tools."""
    
    @pytest.mark.asyncio
    async def test_discover_ideas_success(self):
        """Test discovering ideas in marketplace."""
        mock_client = AsyncMock()
        mock_client.get_public_feed.return_value = [
            {
                "ideaId": "1",
                "title": "Cool Startup",
                "description": "A cool idea",
                "upvoteCount": 10,
                "isUpvoted": False,
                "author": {"fullName": "John Doe"}
            }
        ]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await discover_ideas(limit=10)
        
        assert "Discovered 1 idea(s)" in result
        assert "Cool Startup" in result
        assert "John Doe" in result
    
    @pytest.mark.asyncio
    async def test_discover_ideas_empty(self):
        """Test discover_ideas with no public ideas."""
        mock_client = AsyncMock()
        mock_client.get_public_feed.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await discover_ideas()
        
        assert "No public ideas found" in result
    
    @pytest.mark.asyncio
    async def test_discover_ideas_limit_capped(self):
        """Test that discover_ideas caps the limit at 50."""
        mock_client = AsyncMock()
        mock_client.get_public_feed.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            await discover_ideas(limit=100)
        
        mock_client.get_public_feed.assert_called_once_with(50, 0)
    
    @pytest.mark.asyncio
    async def test_find_similar_ideas_found(self):
        """Test finding similar ideas."""
        mock_client = AsyncMock()
        mock_client.find_similar_ideas.return_value = [
            {"ideaId": "1", "title": "Similar", "description": "desc", "similarity": 0.9}
        ]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await find_similar_ideas("AI startup")
        
        assert "Found 1 similar idea(s)" in result
        assert "90%" in result
    
    @pytest.mark.asyncio
    async def test_find_similar_ideas_none(self):
        """Test find_similar_ideas with no matches."""
        mock_client = AsyncMock()
        mock_client.find_similar_ideas.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await find_similar_ideas("Unique concept")
        
        assert "unique" in result.lower()

    @pytest.mark.asyncio
    async def test_audit_website_and_create_github_issues(self):
        """Test website audit tool summary output."""
        mock_client = AsyncMock()
        mock_client.sync_website_issues.return_value = {
            "target_url": "https://manifeststartup.com",
            "pages_scanned": 4,
            "issue_candidates": [
                {"title": "Fix onboarding CTA clarity", "severity": "high", "category": "ux"}
            ],
            "github": {
                "created_count": 1,
                "skipped_existing_count": 0,
                "created_issues": [
                    {
                        "title": "Fix onboarding CTA clarity",
                        "number": 42,
                        "url": "https://github.com/Manifest-Startup/Manifest/issues/42",
                    }
                ],
            },
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("manifest_mcp.server.get_client", return_value=mock_client):
            result = await audit_website_and_create_github_issues(max_pages=4, max_issues=3)

        assert "Pages scanned: 4" in result
        assert "created" in result.lower()
        assert "#42" in result

    @pytest.mark.asyncio
    async def test_summarize_survey_feedback(self):
        """Test survey summary tool output."""
        mock_client = AsyncMock()
        mock_client.get_survey_insights.return_value = {
            "window_days": 90,
            "total_responses": 18,
            "research_responses": 10,
            "product_feedback_responses": 8,
            "research_signup_intent_avg": 4.2,
            "research_follow_up_rate": 40.0,
            "product_pmf_very_disappointed_pct": 35.0,
            "product_nps_score": 12,
            "top_research_value_props": [{"label": "Investor- or share-ready outputs without starting from scratch"}],
            "top_research_barriers": [{"label": "Doing market research or finding comparable companies"}],
            "top_product_benefits": [{"label": "It gives shape to rough ideas faster"}],
            "top_action_themes": [{"theme": "Research credibility", "count": 4}],
            "issue_candidates": [{"title": "Add citations and source tracing to Manifest research outputs", "severity": "high", "category": "feature"}],
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("manifest_mcp.server.get_client", return_value=mock_client):
            result = await summarize_survey_feedback()

        assert "Survey feedback summary" in result
        assert "Total responses: 18" in result
        assert "Research credibility" in result
        assert "Add citations and source tracing" in result

    @pytest.mark.asyncio
    async def test_create_survey_feedback_github_issues(self):
        """Test survey issue sync tool output."""
        mock_client = AsyncMock()
        mock_client.sync_survey_issues.return_value = {
            "summary": {"window_days": 90, "total_responses": 24},
            "issue_candidates": [{"title": "Clarify the first-session path from idea capture to a meaningful output", "severity": "high", "category": "ux"}],
            "github": {
                "created_count": 1,
                "skipped_existing_count": 0,
                "created_issues": [{"title": "Clarify the first-session path from idea capture to a meaningful output", "number": 8, "url": "https://github.com/test/8"}],
            },
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("manifest_mcp.server.get_client", return_value=mock_client):
            result = await create_survey_feedback_github_issues()

        assert "Survey issue sync analyzed 24 responses" in result
        assert "1 created" in result
        assert "#8" in result


class TestSocialTools:
    """Test social interaction MCP tools."""
    
    @pytest.mark.asyncio
    async def test_upvote_idea_success(self):
        """Test upvoting an idea."""
        mock_client = AsyncMock()
        mock_client.upvote_idea.return_value = {"success": True, "upvoteCount": 5}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await upvote_idea("123")
        
        assert "Successfully upvoted" in result
        assert "5" in result
    
    @pytest.mark.asyncio
    async def test_upvote_idea_failure(self):
        """Test upvote_idea when already upvoted."""
        mock_client = AsyncMock()
        mock_client.upvote_idea.return_value = {"success": False}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await upvote_idea("123")
        
        assert "Failed" in result
    
    @pytest.mark.asyncio
    async def test_toggle_upvote_add(self):
        """Test toggle_upvote adding upvote."""
        mock_client = AsyncMock()
        mock_client.toggle_upvote.return_value = {"success": True, "isUpvoted": True, "upvoteCount": 10}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await toggle_upvote("123")
        
        assert "upvoted" in result
        assert "10" in result
    
    @pytest.mark.asyncio
    async def test_toggle_upvote_remove(self):
        """Test toggle_upvote removing upvote."""
        mock_client = AsyncMock()
        mock_client.toggle_upvote.return_value = {"success": True, "isUpvoted": False, "upvoteCount": 9}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await toggle_upvote("123")
        
        assert "removed upvote" in result
    
    @pytest.mark.asyncio
    async def test_follow_user_success(self):
        """Test following a user."""
        mock_client = AsyncMock()
        mock_client.follow_user.return_value = {"success": True}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await follow_user("user-123")
        
        assert "Successfully followed" in result
    
    @pytest.mark.asyncio
    async def test_unfollow_user_success(self):
        """Test unfollowing a user."""
        mock_client = AsyncMock()
        mock_client.unfollow_user.return_value = {"success": True}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await unfollow_user("user-123")
        
        assert "Successfully unfollowed" in result


class TestInvestmentTools:
    """Test investment management MCP tools."""
    
    @pytest.mark.asyncio
    async def test_get_portfolio_with_investments(self):
        """Test getting portfolio with investments."""
        mock_client = AsyncMock()
        mock_client.get_portfolio.return_value = [
            {
                "investmentId": "inv-1",
                "ideaTitle": "Startup A",
                "investmentType": "cash",
                "totalAmount": 10000,
                "equityPercentage": 5.0,
                "status": "accepted",
                "createdAt": "2024-01-01"
            }
        ]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await get_portfolio()
        
        assert "1 investment(s)" in result
        assert "Startup A" in result
        assert "$10,000.00" in result
        assert "5.00%" in result
    
    @pytest.mark.asyncio
    async def test_get_portfolio_empty(self):
        """Test getting empty portfolio."""
        mock_client = AsyncMock()
        mock_client.get_portfolio.return_value = []
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await get_portfolio()
        
        assert "empty" in result
        assert "invest_in_idea" in result
    
    @pytest.mark.asyncio
    async def test_invest_in_idea_cash(self):
        """Test making a cash investment."""
        mock_client = AsyncMock()
        mock_client.create_investment.return_value = {
            "investmentId": "new-inv",
            "investmentType": "cash",
            "amount": 5000,
            "equityPercentage": 2.5,
            "status": "pending"
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await invest_in_idea("idea-1", "cash", 5000.0, 2.5)
        
        assert "Successfully created" in result
        assert "pending" in result
    
    @pytest.mark.asyncio
    async def test_invest_in_idea_invalid_type(self):
        """Test invest_in_idea with invalid type."""
        result = await invest_in_idea("idea-1", "invalid", 1000, 1.0)
        assert "Invalid investment type" in result
    
    @pytest.mark.asyncio
    async def test_invest_in_idea_invalid_amount(self):
        """Test invest_in_idea with invalid amount."""
        result = await invest_in_idea("idea-1", "cash", -100, 1.0)
        assert "must be positive" in result
    
    @pytest.mark.asyncio
    async def test_invest_in_idea_invalid_equity(self):
        """Test invest_in_idea with invalid equity percentage."""
        result = await invest_in_idea("idea-1", "cash", 1000, 150.0)
        assert "between 0 and 100" in result
    
    @pytest.mark.asyncio
    async def test_get_cap_table_success(self):
        """Test getting cap table."""
        mock_client = AsyncMock()
        mock_client.get_cap_table.return_value = [
            {"userName": "Founder", "equityPercentage": 80.0, "investmentType": "founder"},
            {"userName": "Investor A", "equityPercentage": 10.0, "investmentType": "cash"}
        ]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        with patch('manifest_mcp.server.get_client', return_value=mock_client):
            result = await get_cap_table("idea-1")
        
        assert "Founder" in result
        assert "80.00%" in result
        assert "Investor A" in result
        assert "Remaining:" in result


class TestResources:
    """Test MCP resources."""
    
    def test_get_server_status(self):
        """Test server status resource."""
        with patch.dict(os.environ, {
            "MANIFEST_API_URL": "http://test.local",
            "MANIFEST_API_TOKEN": "test-token",
            "MANIFEST_AGENT_LOOP_SECRET": "loop-secret",
        }):
            status = get_server_status()
        
        assert "1.0.0" in status
        assert "http://test.local" in status
        assert "Yes" in status
        assert "audit_website_and_create_github_issues" in status
        assert "Internal Agent Loop Secret Configured" in status
    
    def test_get_server_status_unauthenticated(self):
        """Test server status without auth token."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MANIFEST_API_URL", None)
            os.environ.pop("MANIFEST_API_TOKEN", None)
            os.environ.pop("MANIFEST_AGENT_LOOP_SECRET", None)
            status = get_server_status()
        
        assert "No" in status
        assert "set MANIFEST_API_TOKEN" in status
        assert "MANIFEST_AGENT_LOOP_SECRET" in status
