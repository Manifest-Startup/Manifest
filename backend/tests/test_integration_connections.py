"""Starting a partner connection from the app or an agent."""

import pytest

from app.db.database import InMemoryDatabaseClient
from app.services.integrations import connections

SITE = "https://manifeststartup.com"


@pytest.fixture
def db(monkeypatch):
    from app.db import database

    monkeypatch.setattr(database, "_in_memory_store", database.defaultdict(list))
    return InMemoryDatabaseClient()


def _rows(db, user_id="u1"):
    return db.table("integrations").select("*").eq("user_id", user_id).execute().data


def test_partner_without_provider_sign_in_is_recorded(db):
    result = connections.start_connection(db, "u1", "Notion", oauth_ready=False, site_origin=SITE)
    assert result.status == connections.STATUS_CONNECTED
    assert result.connect_url is None
    rows = _rows(db)
    assert [r["service_id"] for r in rows] == ["notion"]
    assert rows[0]["service_name"] == "Notion"
    assert rows[0]["access_token"] is None


def test_custom_partner_keeps_its_name(db):
    result = connections.start_connection(
        db, "u1", "acme-logistics", oauth_ready=False, site_origin=SITE, name="Acme Logistics Co"
    )
    assert result.status == connections.STATUS_CONNECTED
    assert _rows(db)[0]["service_name"] == "Acme Logistics Co"


def test_oauth_partner_returns_a_browser_link(db):
    result = connections.start_connection(db, "u1", "github", oauth_ready=True, site_origin=SITE + "/")
    assert result.status == connections.STATUS_NEEDS_BROWSER
    assert result.connect_url == f"{SITE}/account?focusIntegration=github"
    assert _rows(db) == []


def test_open_media_links_through_sign_in(db):
    result = connections.start_connection(db, "u1", "open_media", oauth_ready=False, site_origin=SITE)
    assert result.status == connections.STATUS_NEEDS_BROWSER
    assert result.connect_url == f"{SITE}/api/auth/open-media/start?next=/account"


def test_already_connected_is_reported_not_duplicated(db):
    connections.start_connection(db, "u1", "stripe", oauth_ready=False, site_origin=SITE)
    again = connections.start_connection(db, "u1", "stripe", oauth_ready=False, site_origin=SITE)
    assert again.status == connections.STATUS_ALREADY_CONNECTED
    assert len(_rows(db)) == 1


@pytest.mark.parametrize("bad", ["", "../etc", "x" * 41, "openai", "<script>"])
def test_rejects_bad_or_reserved_ids(db, bad):
    with pytest.raises(ValueError):
        connections.start_connection(db, "u1", bad, oauth_ready=False, site_origin=SITE)


def test_connected_partner_names_skip_the_openai_key(db, monkeypatch):
    from app.db import database

    monkeypatch.setattr(database, "create_database_client", lambda: db)
    connections.start_connection(db, "u1", "stripe", oauth_ready=False, site_origin=SITE)
    db.table("integrations").insert(
        {"integration_id": "k", "user_id": "u1", "service_id": "openai", "service_name": "OpenAI"}
    ).execute()
    db.table("integrations").insert(
        {"integration_id": "om", "user_id": "u1", "service_id": "open_media", "service_name": ""}
    ).execute()
    assert connections.connected_partner_names("u1") == ["Stripe", "Open Media"]
    assert connections.connected_partner_names(None) == []


def test_section_prompt_carries_connected_partners():
    from app.services.canvas import orchestrator

    seen = {}

    class FakeAI:
        def is_available(self):
            return True

        def generate_structured_response(self, messages):
            seen["user"] = messages[1]["content"]
            return {"section_name": "key_partners", "content": "- Stripe for payments"}

    orchestrator._run_section_agent(
        ai_layer=FakeAI(),
        section_name="key_partners",
        idea_description="Pet transport",
        qualification_summary="",
        sibling_sections={},
        connected_partners=["Stripe", "Open Media"],
    )
    assert "Stripe, Open Media" in seen["user"]
    assert "{{" not in seen["user"]
    assert "not connected any partners" in connections.partners_prompt_block([])


def test_linked_means_the_partners_own_sign_in_completed():
    from app.graphql.resolvers.integrations import _is_linked

    assert _is_linked({"service_id": "notion", "access_token": None}) is False
    assert _is_linked({"service_id": "notion", "access_token_ciphertext": b"x"}) is True
    assert _is_linked({"service_id": "open_media"}) is True
