"""Tests for submit_survey GraphQL mutation."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def mock_request():
    return MagicMock()


def _mutation_db():
    db = MagicMock()
    chain = MagicMock()
    chain.insert.return_value = chain
    chain.execute.return_value = MagicMock()
    db.table.return_value = chain
    return db, chain


@pytest.mark.asyncio
async def test_submit_survey_research_inserts_row(mock_request):
    from app.graphql.schema import Mutation, SubmitSurveyInput

    db, chain = _mutation_db()
    answers = {"consent_required": True, "role": "Founder"}
    inp = SubmitSurveyInput(
        survey_type="research",
        answers_json=json.dumps(answers),
        contact_email="a@b.com",
    )
    info = SimpleNamespace(context={"request": mock_request, "db": db})

    ok = await Mutation().submit_survey(info, inp)
    assert ok is True
    db.table.assert_called_with("survey_responses")
    payload = chain.insert.call_args[0][0]
    assert payload["survey_type"] == "research"
    assert payload["contact_email"] == "a@b.com"
    assert json.loads(payload["answers"])["role"] == "Founder"


@pytest.mark.asyncio
async def test_submit_survey_research_requires_consent(mock_request):
    from app.graphql.schema import Mutation, SubmitSurveyInput

    db, _ = _mutation_db()
    inp = SubmitSurveyInput(survey_type="research", answers_json=json.dumps({"role": "x"}))
    info = SimpleNamespace(context={"request": mock_request, "db": db})

    with pytest.raises(Exception, match="must agree"):
        await Mutation().submit_survey(info, inp)


@pytest.mark.asyncio
async def test_submit_survey_product_feedback_requires_auth(mock_request):
    from app.graphql.schema import Mutation, SubmitSurveyInput

    db, _ = _mutation_db()
    mock_request.cookies.get.return_value = None
    mock_request.headers.get.return_value = None

    inp = SubmitSurveyInput(
        survey_type="product_feedback",
        answers_json=json.dumps({"nps": 8}),
    )
    info = SimpleNamespace(context={"request": mock_request, "db": db})

    with pytest.raises(Exception, match="Sign in"):
        await Mutation().submit_survey(info, inp)


@pytest.mark.asyncio
async def test_submit_survey_product_feedback_serializes_answers_when_authenticated(mock_request):
    from app.graphql.schema import Mutation, SubmitSurveyInput
    from app.auth.current_user import generate_demo_token

    db, chain = _mutation_db()
    token = generate_demo_token("user-123", "hello@example.com")
    mock_request.cookies.get.return_value = None
    mock_request.headers.get.return_value = f"Bearer {token}"

    inp = SubmitSurveyInput(
        survey_type="product_feedback",
        answers_json=json.dumps({"nps": 8, "top_fix": "Improve research quality"}),
    )
    info = SimpleNamespace(context={"request": mock_request, "db": db})

    ok = await Mutation().submit_survey(info, inp)

    assert ok is True
    payload = chain.insert.call_args[0][0]
    assert payload["survey_type"] == "product_feedback"
    assert payload["user_id"] == "user-123"
    assert json.loads(payload["answers"])["top_fix"] == "Improve research quality"
