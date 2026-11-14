"""
Tests for Investment Service
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.social.investments import InvestmentService, create_investment_service


def create_mock_db():
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_response = MagicMock()
    
    mock_db.table.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.neq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.single.return_value = mock_query
    mock_query.upsert.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.delete.return_value = mock_query
    mock_query.execute.return_value = mock_response
    
    return mock_db, mock_query, mock_response


@pytest.fixture
def mock_db():
    db, _, _ = create_mock_db()
    return db


@pytest.fixture
def investment_service(mock_db):
    return InvestmentService(mock_db)


class TestInvestmentService:
    @pytest.mark.asyncio
    async def test_create_investment_cash(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "investment_id": "inv-123",
            "idea_id": "idea-456",
            "investor_id": "user-789",
            "cash_amount": 10000,
            "sweat_equity_hours": 0,
            "sweat_equity_value": 0,
            "equity_percentage": 5,
            "investment_type": "cash",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        service = InvestmentService(mock_db)
        result = await service.create_investment(
            idea_id="idea-456",
            investor_id="user-789",
            cash_amount=10000,
            equity_percentage=5,
            investment_type="cash"
        )

        assert result["investment_id"] == "inv-123"
        assert result["cash_amount"] == 10000
        assert result["investment_type"] == "cash"

    @pytest.mark.asyncio
    async def test_create_investment_sweat_equity(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "investment_id": "inv-124",
            "idea_id": "idea-456",
            "investor_id": "user-789",
            "cash_amount": 0,
            "sweat_equity_hours": 100,
            "sweat_equity_value": 5000,
            "equity_percentage": 5,
            "investment_type": "sweat",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }

        service = InvestmentService(mock_db)
        result = await service.create_investment(
            idea_id="idea-456",
            investor_id="user-789",
            sweat_equity_hours=100,
            hourly_rate=50,
            equity_percentage=5,
            investment_type="sweat"
        )

        assert result["investment_id"] == "inv-124"
        assert result["sweat_equity_hours"] == 100
        assert result["sweat_equity_value"] == 5000
        assert result["investment_type"] == "sweat"

    @pytest.mark.asyncio
    async def test_get_idea_investments(self, investment_service, mock_db):
        mock_response = MagicMock()
        mock_response.data = [
            {"investment_id": "inv-1", "investor_id": "user-1", "cash_amount": 5000},
            {"investment_id": "inv-2", "investor_id": "user-2", "cash_amount": 10000}
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_response

        result = await investment_service.get_idea_investments("idea-456")

        assert len(result) == 2
        assert result[0]["investment_id"] == "inv-1"

    @pytest.mark.asyncio
    async def test_get_user_investments_portfolio(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"investment_id": "inv-1", "idea_id": "idea-1", "cash_amount": 5000},
            {"investment_id": "inv-2", "idea_id": "idea-2", "cash_amount": 10000}
        ]

        service = InvestmentService(mock_db)
        result = await service.get_user_investments("user-789")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_update_investment_status(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "investment_id": "inv-123",
            "status": "approved"
        }

        service = InvestmentService(mock_db)
        result = await service.update_investment_status("inv-123", "approved")

        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_calculate_total_investment(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = [
            {"cash_amount": 5000, "sweat_equity_value": 2000},
            {"cash_amount": 10000, "sweat_equity_value": 3000}
        ]

        service = InvestmentService(mock_db)
        result = await service.get_idea_investments("idea-456")
        total_cash = sum(inv.get("cash_amount", 0) for inv in result)
        total_sweat = sum(inv.get("sweat_equity_value", 0) for inv in result)

        assert total_cash == 15000
        assert total_sweat == 5000


class TestCreateInvestmentServiceFactory:
    def test_create_investment_service(self):
        mock_db = MagicMock()
        service = create_investment_service(mock_db)
        
        assert isinstance(service, InvestmentService)
        assert service.db == mock_db


class TestInvestmentServiceEdgeCases:
    @pytest.mark.asyncio
    async def test_create_investment_with_notes(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "investment_id": "inv-125",
            "notes": "Test investment notes",
            "status": "pending"
        }

        service = InvestmentService(mock_db)
        result = await service.create_investment(
            idea_id="idea-456",
            investor_id="user-789",
            cash_amount=5000,
            equity_percentage=2,
            investment_type="cash",
            notes="Test investment notes"
        )

        assert result["notes"] == "Test investment notes"

    @pytest.mark.asyncio
    async def test_create_investment_with_role(self):
        mock_db, mock_query, mock_response = create_mock_db()
        mock_response.data = {
            "investment_id": "inv-126",
            "role": "Technical Advisor",
            "status": "pending"
        }

        service = InvestmentService(mock_db)
        result = await service.create_investment(
            idea_id="idea-456",
            investor_id="user-789",
            sweat_equity_hours=50,
            hourly_rate=100,
            equity_percentage=3,
            investment_type="sweat",
            role="Technical Advisor"
        )

        assert result["role"] == "Technical Advisor"

    @pytest.mark.asyncio
    async def test_get_empty_investments(self, investment_service, mock_db):
        mock_response = MagicMock()
        mock_response.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_response

        result = await investment_service.get_idea_investments("idea-empty")

        assert result == []
        assert len(result) == 0
