import os
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from app.main import app


client = TestClient(app)

UNIVERSAL_SEARCH_QUERY = """
query UniversalSearch($query: String!, $includeWeb: Boolean) {
  universalSearch(query: $query, includeWeb: $includeWeb) {
    query
    assistantSummary
    webSummary
    myIdeas {
      title
      matchedIn
      snippet
    }
    publishedIdeas {
      title
      creatorName
      matchedIn
      snippet
    }
    webSources {
      title
      url
      hostname
    }
  }
}
"""


def _build_response(data):
    response = MagicMock()
    response.data = data
    return response


def _build_table(data):
    table = MagicMock()
    table.select.return_value = table
    table.eq.return_value = table
    table.neq.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.single.return_value = table
    table.execute.return_value = _build_response(data)
    return table


def _build_user_table(users_by_id):
    table = MagicMock()
    table.select.return_value = table
    table.single.return_value = table
    table.in_.return_value = table

    state = {"user_id": None, "user_ids": None}

    def eq_side_effect(field, value):
        if field == "user_id":
            state["user_id"] = value
        return table

    def in__side_effect(field, values):
        if field == "user_id":
            state["user_ids"] = list(values) if values is not None else None
        return table

    def execute_side_effect():
        if state.get("user_ids") is not None:
            rows = [users_by_id[uid] for uid in state["user_ids"] if uid in users_by_id]
            return _build_response(rows)
        return _build_response(users_by_id.get(state["user_id"]))

    table.eq.side_effect = eq_side_effect
    table.in_.side_effect = in__side_effect
    table.execute.side_effect = execute_side_effect
    return table


@contextmanager
def _override_request_db(mock_db):
    import tests.conftest as shared_conftest

    sentinel = object()
    previous = getattr(shared_conftest, "mock_database_client", sentinel)
    shared_conftest.mock_database_client = mock_db
    try:
        yield
    finally:
        if previous is sentinel:
            delattr(shared_conftest, "mock_database_client")
        else:
            shared_conftest.mock_database_client = previous


def test_universal_search_returns_internal_and_published_matches():
    my_ideas = [
        {
            "idea_id": "idea-1",
            "user_id": "test_user_id",
            "title": "AI Supply Chain Copilot",
            "description": "Predicts inventory shortages and vendor delays for manufacturers.",
            "business_model_canvas": "Customer segments include mid-market factories.",
            "pitch_deck": "",
            "product_requirements_document": "",
            "provisional_patent": "",
            "similar_ideas": "",
            "is_published": False,
            "created_at": "2026-03-13T18:00:00Z",
        },
        {
            "idea_id": "idea-2",
            "user_id": "test_user_id",
            "title": "Consumer photo app",
            "description": "Social memories for families.",
            "business_model_canvas": "",
            "pitch_deck": "",
            "product_requirements_document": "",
            "provisional_patent": "",
            "similar_ideas": "",
            "is_published": False,
            "created_at": "2026-03-10T18:00:00Z",
        },
    ]
    published_ideas = [
        {
            "idea_id": "public-1",
            "user_id": "founder-2",
            "title": "Factory Forecast Network",
            "description": "Operations intelligence for procurement and warehouse planning.",
            "business_model_canvas": "Distribution partners and procurement teams.",
            "pitch_deck": "",
            "product_requirements_document": "",
            "provisional_patent": "",
            "similar_ideas": "",
            "is_published": True,
            "created_at": "2026-03-12T12:00:00Z",
        }
    ]
    users_by_id = {
        "founder-2": {
            "user_id": "founder-2",
            "first_name": "Public",
            "last_name": "Founder",
            "username": "publicfounder",
            "profile_picture_url": "https://example.com/public-founder.png",
            "email": "public@example.com",
        }
    }

    my_ideas_table = _build_table(my_ideas)
    public_ideas_table = _build_table(published_ideas)
    users_table = _build_user_table(users_by_id)
    table_calls = {"ideas": 0}

    def table_side_effect(name):
        if name == "ideas":
            table_calls["ideas"] += 1
            return my_ideas_table if table_calls["ideas"] == 1 else public_ideas_table
        if name == "users":
            return users_table
        raise AssertionError(f"Unexpected table requested: {name}")

    search_db = MagicMock()
    search_db.table.side_effect = table_side_effect

    with _override_request_db(search_db):
        with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"), patch(
            "app.graphql.resolvers.search.get_current_user_id", return_value="test_user_id"
        ):
            response = client.post(
                "/graphql",
                json={
                    "query": UNIVERSAL_SEARCH_QUERY,
                    "variables": {"query": "inventory factory", "includeWeb": False},
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert "errors" not in payload

    data = payload["data"]["universalSearch"]
    assert data["query"] == "inventory factory"
    assert data["myIdeas"][0]["title"] == "AI Supply Chain Copilot"
    assert data["myIdeas"][0]["matchedIn"] in {"Description", "Business model", "Title"}
    assert "manufacturers" in data["myIdeas"][0]["snippet"]
    assert data["publishedIdeas"][0]["title"] == "Factory Forecast Network"
    assert data["publishedIdeas"][0]["creatorName"] == "Public Founder"
    assert data["assistantSummary"] is None
    assert data["webSources"] == []


def test_universal_search_includes_web_results_and_ai_summary():
    from app.managers.manifest_manager import manifest_manager

    my_ideas_table = _build_table([])
    public_ideas_table = _build_table([])
    table_calls = {"ideas": 0}

    def table_side_effect(name):
        if name == "ideas":
            table_calls["ideas"] += 1
            return my_ideas_table if table_calls["ideas"] == 1 else public_ideas_table
        raise AssertionError(f"Unexpected table requested: {name}")

    search_db = MagicMock()
    search_db.table.side_effect = table_side_effect

    with _override_request_db(search_db):
        with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"), \
             patch("app.graphql.resolvers.search.get_current_user_id", return_value="test_user_id"), \
             patch.object(manifest_manager.ai_layer, "is_available", return_value=True), \
             patch.object(
                 manifest_manager.ai_layer,
                 "perform_web_search",
                 return_value={
                     "similar_ideas": "Enterprise workflow search is growing as teams centralize research and note-taking.",
                     "sources": [
                         "https://example.com/enterprise-search-report",
                         "https://news.site/notes-app-market-map",
                     ],
                 },
             ), \
             patch.object(
                 manifest_manager.ai_layer,
                 "generate_text",
                 return_value="Search interest is strongest around AI-assisted research and unified note retrieval.",
             ):
            response = client.post(
                "/graphql",
                json={
                    "query": UNIVERSAL_SEARCH_QUERY,
                    "variables": {"query": "ai note search", "includeWeb": True},
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert "errors" not in payload

    data = payload["data"]["universalSearch"]
    assert data["assistantSummary"] == "Search interest is strongest around AI-assisted research and unified note retrieval."
    assert data["webSummary"] == "Enterprise workflow search is growing as teams centralize research and note-taking."
    assert len(data["webSources"]) == 2
    assert data["webSources"][0]["url"] == "https://example.com/enterprise-search-report"
    assert data["webSources"][0]["hostname"] == "example.com"


MESSAGES_SEARCH_QUERY = """
query UniversalSearch($query: String!) {
  universalSearch(query: $query) {
    messages { conversationId kind title preview ideaTitle }
  }
}
"""


def _search_messages(query, inbox, linked=True):
    search_db = MagicMock()
    search_db.table.side_effect = lambda name: _build_table([])
    with _override_request_db(search_db):
        with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"), patch(
            "app.graphql.resolvers.search.get_current_user_id", return_value="test_user_id"
        ), patch(
            "app.services.integrations.open_media.inbox.identity.om_user_id_for",
            return_value="om-1" if linked else None,
        ), patch(
            "app.services.integrations.open_media.inbox.list_inbox", return_value=inbox
        ) as listed:
            response = client.post(
                "/graphql", json={"query": MESSAGES_SEARCH_QUERY, "variables": {"query": query}}
            )
    payload = response.json()
    assert "errors" not in payload, payload
    return payload["data"]["universalSearch"]["messages"], listed


INBOX = [
    {"id": "c1", "kind": "chat", "title": "Priya Shah", "preview": "Loved the pitch deck"},
    {"id": "c2", "kind": "email", "title": "Acme Ventures", "preview": "Term sheet attached"},
    {
        "id": "c3",
        "kind": "chat",
        "title": "Sam Lee",
        "preview": "hi",
        "context": {"app": "manifest", "title": "Factory Forecast"},
    },
]


def test_universal_search_finds_messages_by_person_message_and_idea():
    assert [m["conversationId"] for m in _search_messages("priya", INBOX)[0]] == ["c1"]
    assert [m["conversationId"] for m in _search_messages("TERM sheet", INBOX)[0]] == ["c2"]
    found = _search_messages("factory forecast", INBOX)[0]
    assert found[0]["conversationId"] == "c3" and found[0]["ideaTitle"] == "Factory Forecast"
    assert _search_messages("nobody", INBOX)[0] == []


def test_universal_search_skips_messages_without_open_media_link():
    messages, listed = _search_messages("priya", INBOX, linked=False)
    assert messages == []
    listed.assert_not_called()


def test_universal_search_survives_open_media_failure():
    search_db = MagicMock()
    search_db.table.side_effect = lambda name: _build_table([])
    with _override_request_db(search_db):
        with patch("app.graphql.schema.get_current_user_id", return_value="test_user_id"), patch(
            "app.graphql.resolvers.search.get_current_user_id", return_value="test_user_id"
        ), patch(
            "app.services.integrations.open_media.inbox.search_inbox",
            side_effect=RuntimeError("down"),
        ):
            response = client.post(
                "/graphql", json={"query": MESSAGES_SEARCH_QUERY, "variables": {"query": "x"}}
            )
    assert response.json()["data"]["universalSearch"]["messages"] == []
