"""Unit tests for the Manifest voice agent service."""

import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _build_mock_db():
    db = MagicMock()

    user_query = MagicMock()
    user_query.select.return_value = user_query
    user_query.eq.return_value = user_query
    user_query.single.return_value = user_query
    user_query.execute.return_value = MagicMock(
        data={
            "user_id": "user-1",
            "email": "founder@example.com",
            "first_name": "Mihir",
            "last_name": "Patel",
            "country": "United States",
            "bio": "Second-time founder focused on SaaS workflows.",
        }
    )

    idea_query = MagicMock()
    idea_query.select.return_value = idea_query
    idea_query.eq.return_value = idea_query
    idea_query.single.return_value = idea_query
    idea_query.execute.return_value = MagicMock(
        data={
            "idea_id": "idea-1",
            "title": "Workflow OS",
            "description": "<p>Existing context about a workflow operating system for founders.</p>",
        }
    )

    def table(name):
        if name == "users":
            return user_query
        if name == "ideas":
            return idea_query
        raise AssertionError(f"Unexpected table lookup: {name}")

    db.table.side_effect = table
    return db


def _import_voice_agent_module():
    sys.modules.pop("app.services.ai.router", None)
    sys.modules.pop("app.services.voice.agent", None)
    with patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=MagicMock())}):
        return importlib.import_module("app.services.voice.agent")


class TestVoiceAgentService:
    """Service tests for the richer voice qualification flow."""

    @pytest.fixture
    def mock_router(self):
        mock = MagicMock()
        mock.is_available.return_value = True
        mock.chat_stream.return_value = [
            "You have a strong workflow thesis. ",
            "What is the wedge that gets the first users in quickly?",
        ]
        mock.chat_json.return_value = {
            "message": "You have a strong workflow thesis. What is the wedge that gets the first users in quickly?",
            "is_qualified": False,
            "summary": "A workflow operating system for founders that centralizes planning and execution.",
            "suggested_title": "Workflow OS",
            "covered_topics": ["problem", "solution", "target_customer"],
            "missing_topics": ["go_to_market", "business_model"],
            "qualification_confidence": 0.66,
            "context": {
                "problem": "Founders juggle planning and execution across too many disconnected tools.",
                "target_customer": "Seed-stage founders and startup operators",
                "solution": "A single workspace that turns ideas into structured execution plans",
                "current_alternative": "Notion, spreadsheets, and project tools",
                "differentiation": "The system generates startup docs and execution artifacts directly from the note",
                "business_model": None,
                "go_to_market": None,
                "product_scope": "Idea capture, qualification, and execution planning",
                "founder_advantage": "The founder has lived this workflow pain directly",
                "risks": ["Execution can become too broad without a sharp wedge."],
                "open_questions": ["What entry point gets the first users to switch?"],
                "next_step": "Define the first high-frequency workflow and landing customer profile.",
            },
        }
        return mock

    @pytest.fixture
    def mock_db(self):
        return _build_mock_db()

    @pytest.fixture
    def voice_agent_service(self, mock_router):
        voice_agent_module = _import_voice_agent_module()
        with patch.object(voice_agent_module, "AIRouter") as mock_class:
            mock_class.return_value = mock_router
            service = voice_agent_module.VoiceAgentService()
            service.router = mock_router
            return service

    def test_start_conversation_uses_context(self, voice_agent_service, mock_db):
        result = voice_agent_service.start_conversation(user_id="user-1", db=mock_db, idea_id="idea-1")

        assert "conversation_id" in result
        assert result["response"]["message"] == ""
        assert result["response"]["suggested_title"] == "Workflow OS"

    def test_start_conversation_onboarding_mode_greets(self, voice_agent_service, mock_db):
        result = voice_agent_service.start_conversation(
            user_id="user-1", db=mock_db, idea_id=None, onboarding_mode=True
        )

        assert result["response"]["message"]
        assert "guest tryout" in result["response"]["message"].lower()
        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][1]["role"] == "system"
        assert "onboarding" in result["messages"][1]["content"].lower() or "guest" in result["messages"][1]["content"].lower()

    def test_start_conversation_landing_onboarding_script(self, voice_agent_service, mock_db, mock_router):
        mock_router.chat_json.return_value = {
            "message": (
                "Hi there—welcome to Manifest. I'm glad you stopped by. "
                "When you have a moment, how would you describe yourself here—mostly building, exploring ideas as an investor, or something else?"
            ),
        }
        result = voice_agent_service.start_conversation(
            user_id="user-1",
            db=mock_db,
            idea_id=None,
            onboarding_mode=True,
            landing_onboarding=True,
        )

        msg = result["response"]["message"].lower()
        assert "manifest" in msg
        assert "welcome" in msg or "glad" in msg
        assert result["response"].get("landing_onboarding_step") == 1
        assert len(result["messages"]) == 4

    def test_process_message_landing_onboarding_two_turns(self, voice_agent_service, mock_db, mock_router):
        mock_router.chat_json.side_effect = [
            {
                "message": (
                    "Hi—welcome to Manifest. I'm glad you're here. "
                    "How would you describe yourself today—building, investing, or another path?"
                ),
            },
            {
                "message": "Thanks for sharing that. What would you most like Manifest to help you with over the next few weeks?",
                "landing_onboarding_step": 2,
                "landing_complete": False,
            },
            {
                "message": "Starting the Manifest web app for you now.",
                "landing_onboarding_step": 3,
                "landing_complete": True,
            },
        ]
        start = voice_agent_service.start_conversation(
            user_id="user-1",
            db=mock_db,
            idea_id=None,
            onboarding_mode=True,
            landing_onboarding=True,
        )
        messages = start["messages"]

        turn1 = voice_agent_service.process_message(
            conversation_messages=messages,
            user_message="Mostly building as a founder.",
            user_id="user-1",
            db=mock_db,
            idea_id=None,
            onboarding_mode=True,
            landing_onboarding=True,
        )
        assert turn1["response"]["landing_onboarding_step"] == 2
        assert turn1["response"]["landing_complete"] is False
        assert "outcome" in turn1["response"]["message"].lower() or "weeks" in turn1["response"]["message"].lower()

        turn2 = voice_agent_service.process_message(
            conversation_messages=turn1["messages"],
            user_message="I want a pitch deck draft in two weeks.",
            user_id="user-1",
            db=mock_db,
            idea_id=None,
            onboarding_mode=True,
            landing_onboarding=True,
        )
        assert turn2["response"]["landing_complete"] is True
        assert "manifest" in turn2["response"]["message"].lower()

    def test_defaults_to_gpt_4o_mini_for_voice_latency(self, monkeypatch):
        monkeypatch.delenv("VOICE_AGENT_MODEL", raising=False)

        voice_agent_module = _import_voice_agent_module()
        with patch.object(voice_agent_module, "AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = True
            mock_class.return_value = mock_router

            service = voice_agent_module.VoiceAgentService()

            assert service.model == "gpt-4o-mini"
            mock_class.assert_called_with(model="gpt-4o-mini")

    def test_process_message_returns_voice_note_payload(self, voice_agent_service, mock_db):
        messages = [
            {"role": "assistant", "content": json.dumps({"message": "Tell me what changed in the idea.", "is_qualified": False})}
        ]

        result = voice_agent_service.process_message(
            conversation_messages=messages,
            user_message="It should become the workspace where founders drive all execution.",
            user_id="user-1",
            db=mock_db,
            idea_id="idea-1",
        )

        response = result["response"]
        assert response["message"]
        assert response["transcript"] == "It should become the workspace where founders drive all execution."
        assert response["voice_note_html"] is not None
        assert "Transcript" in response["voice_note_html"]
        assert response["covered_topics"]
        assert response["missing_topics"]
        assert voice_agent_service.router.chat_stream.called

    def test_process_message_router_not_available_returns_fallback(self, mock_db):
        voice_agent_module = _import_voice_agent_module()
        with patch.object(voice_agent_module, "AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = False
            mock_class.return_value = mock_router

            service = voice_agent_module.VoiceAgentService()
            result = service.process_message(
                conversation_messages=[],
                user_message="A founder workspace for startup execution.",
                user_id="user-1",
                db=mock_db,
                idea_id="idea-1",
            )

            assert "working note" in result["response"]["message"].lower()
            assert result["response"]["voice_note_html"] is not None

    def test_process_message_ignores_operational_chatter(self, mock_db):
        voice_agent_module = _import_voice_agent_module()
        with patch.object(voice_agent_module, "AIRouter") as mock_class:
            mock_router = MagicMock()
            mock_router.is_available.return_value = False
            mock_class.return_value = mock_router

            service = voice_agent_module.VoiceAgentService()
            result = service.process_message(
                conversation_messages=[],
                user_message="Why can't you open the folder?",
                user_id="user-1",
                db=mock_db,
                idea_id="idea-1",
            )

            assert "not startup context" in result["response"]["message"].lower()
            assert result["response"]["transcript"] is None
            assert result["response"]["summary"] is not None
            assert result["messages"][-1]["role"] == "assistant"

    def test_process_message_adds_user_and_assistant_history(self, voice_agent_service, mock_db):
        result = voice_agent_service.process_message(
            conversation_messages=[],
            user_message="A founder workspace for startup execution.",
            user_id="user-1",
            db=mock_db,
            idea_id="idea-1",
        )

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"

    def test_stream_spoken_turn_yields_model_chunks(self, voice_agent_service, mock_db):
        prepared = voice_agent_service._prepare_turn(
            conversation_messages=[],
            user_message="A founder workspace for startup execution.",
            user_id="user-1",
            db=mock_db,
            idea_id="idea-1",
        )

        chunks = list(
            voice_agent_service.stream_spoken_turn(
                context=prepared["context"],
                normalized_history=prepared["normalized_history"],
                latest_user_message=prepared["cleaned_user_message"],
            )
        )

        assert "".join(chunks).startswith("You have a strong workflow thesis.")

    def test_enrich_structured_turn_preserves_spoken_message(self, voice_agent_service, mock_db):
        prepared = voice_agent_service._prepare_turn(
            conversation_messages=[],
            user_message="A founder workspace for startup execution.",
            user_id="user-1",
            db=mock_db,
            idea_id="idea-1",
        )

        result = voice_agent_service.enrich_structured_turn(
            context=prepared["context"],
            normalized_history=prepared["normalized_history"],
            user_message=prepared["cleaned_user_message"],
            assistant_message="Let's sharpen the wedge first.",
        )

        assert result["message"] == "Let's sharpen the wedge first."

    def test_qualify_idea_merges_voice_note_into_description(self, voice_agent_service, mock_db):
        result = voice_agent_service.qualify_idea(
            conversation_messages=[
                {"role": "user", "content": "I want a workspace for founder execution."},
                {"role": "assistant", "content": json.dumps({"message": "What wedge gets the first users in?"})},
            ],
            user_id="user-1",
            db=mock_db,
            idea_id="idea-1",
        )

        assert result["title"] == "Workflow OS"
        assert "manifest-voice-note:start" in result["description"]
        assert result["summary"] is not None

    def test_strategist_prompts_share_cache_prefix(self, voice_agent_service):
        """Spoken / structured / enrich / finalize must share a byte-identical
        prefix so OpenAI's automatic prompt-prefix cache hits across turns."""
        prompts = [
            voice_agent_service.SPOKEN_STREAM_PROMPT,
            voice_agent_service.SYSTEM_PROMPT,
            voice_agent_service.ENRICH_PROMPT,
            voice_agent_service.FINALIZE_PROMPT,
        ]
        base = voice_agent_service.BASE_VOICE_AGENT_PROMPT
        assert base, "BASE_VOICE_AGENT_PROMPT must not be empty"
        # Each composed prompt must literally begin with the shared base.
        for prompt in prompts:
            assert prompt.startswith(base), "strategist prompts must share BASE prefix bytes"
        # Sanity check: divergence happens only after the shared prefix.
        for prompt in prompts:
            assert prompt[len(base):], "directive tail must be non-empty"

    def test_build_prompt_messages_orders_grounding_by_stability(
        self, voice_agent_service, mock_db, monkeypatch
    ):
        """Stable user_profile precedes volatile main_note_excerpt so the
        cache prefix grows as long as possible across turns."""
        monkeypatch.setenv("VOICE_AGENT_PROMPT_CACHE_ENABLED", "true")
        context = voice_agent_service._load_context(user_id="user-1", db=mock_db, idea_id="idea-1")
        context["onboarding_mode"] = False
        context["landing_onboarding"] = False

        messages = voice_agent_service._build_prompt_messages(
            context=context,
            normalized_history=[],
            latest_user_message="What customer should we focus on?",
            system_prompt=voice_agent_service.SPOKEN_STREAM_PROMPT,
        )
        grounding = messages[1]["content"]
        # user_profile bytes appear before main_note_excerpt bytes.
        assert grounding.find("user_profile") < grounding.find("main_note_excerpt")
        # No cache buster prefix when flag enabled.
        assert "voice-cache-disabled" not in messages[0]["content"]

    def test_cache_disable_flag_breaks_prefix(self, voice_agent_service, mock_db, monkeypatch):
        """When VOICE_AGENT_PROMPT_CACHE_ENABLED=false the system message gets
        a per-request nonce that breaks OpenAI's prefix cache. Required by
        the manifest-pitch-reel-cost-guard skill."""
        monkeypatch.setenv("VOICE_AGENT_PROMPT_CACHE_ENABLED", "false")
        context = voice_agent_service._load_context(user_id="user-1", db=mock_db, idea_id="idea-1")
        context["onboarding_mode"] = False
        context["landing_onboarding"] = False

        first = voice_agent_service._build_prompt_messages(
            context=context,
            normalized_history=[],
            latest_user_message="A",
            system_prompt=voice_agent_service.SPOKEN_STREAM_PROMPT,
        )
        second = voice_agent_service._build_prompt_messages(
            context=context,
            normalized_history=[],
            latest_user_message="B",
            system_prompt=voice_agent_service.SPOKEN_STREAM_PROMPT,
        )
        # Both carry the cache buster, and the nonce differs between calls.
        assert "voice-cache-disabled" in first[0]["content"]
        assert "voice-cache-disabled" in second[0]["content"]
        assert first[0]["content"] != second[0]["content"]


class TestVoiceAgentRoutes:
    """Minimal auth coverage for the FastAPI routes."""

    @pytest.fixture
    def client(self):
        pytest.importorskip("fastapi.testclient")
        from fastapi.testclient import TestClient
        from app.main import fastapi_app

        return TestClient(fastapi_app)

    def test_start_endpoint_requires_auth(self, client):
        response = client.post("/api/voice-agent/start")
        assert response.status_code in [401, 403, 500]

    def test_process_endpoint_requires_auth(self, client):
        response = client.post(
            "/api/voice-agent/process",
            json={"messages": [], "user_message": "test"},
        )
        assert response.status_code in [401, 403, 500]

    def test_process_stream_endpoint_requires_auth(self, client):
        response = client.post(
            "/api/voice-agent/process-stream",
            json={"messages": [], "user_message": "test"},
        )
        assert response.status_code in [401, 403, 500]

    def test_qualify_endpoint_requires_auth(self, client):
        response = client.post(
            "/api/voice-agent/qualify",
            json={"messages": []},
        )
        assert response.status_code in [401, 403, 500]

    def test_transcribe_endpoint_requires_auth(self, client):
        response = client.post(
            "/api/voice-agent/transcribe",
            json={"audio_base64": "dGVzdA=="},
        )
        assert response.status_code in [401, 403, 500]

    def test_capabilities_endpoint_returns_catalog_when_authenticated(self, client):
        from app.routes.dependencies import require_user_id
        from app.main import fastapi_app

        fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
        try:
            response = client.get("/api/voice-agent/capabilities")
            assert response.status_code == 200
            body = response.json()
            assert "navigate the app" in body["summary"].lower()
            assert any(command["id"] == "ideas-manage" for command in body["commands"])
        finally:
            fastapi_app.dependency_overrides.pop(require_user_id, None)

    def test_process_stream_returns_sse_when_authenticated(self, client):
        from app.main import fastapi_app
        from app.routes.dependencies import require_user_id
        from app.routes import voice_agent_routes

        fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
        with patch("app.routes.voice_agent_routes.create_database_client", return_value=_build_mock_db()):
            with patch.object(
                voice_agent_routes.voice_agent_service,
                "stream_spoken_turn",
                return_value=iter(["We should narrow the first customer. "]),
            ):
                with patch.object(
                    voice_agent_routes.voice_agent_service,
                    "enrich_structured_turn",
                    return_value={
                        "message": "We should narrow the first customer.",
                        "is_qualified": False,
                        "summary": "A startup idea.",
                        "suggested_title": "Workflow OS",
                        "transcript": "Help me think through it",
                        "voice_note_html": "<p>Voice note</p>",
                        "covered_topics": ["problem"],
                        "missing_topics": ["business_model"],
                        "qualification_confidence": 0.5,
                        "context": {},
                    },
                ):
                    try:
                        response = client.post(
                            "/api/voice-agent/process-stream",
                            json={"messages": [], "user_message": "Help me think through it"},
                        )
                        assert response.status_code == 200
                        assert response.headers["content-type"].startswith("text/event-stream")
                        assert "event: delta" in response.text
                        assert "event: structured" in response.text
                    finally:
                        fastapi_app.dependency_overrides.pop(require_user_id, None)


class TestVoiceContextCache:
    """_load_context caches the user/idea rows briefly so each voice turn
    stops paying 2 DB round-trips before the first LLM token."""

    @pytest.fixture
    def service(self):
        voice_agent_module = _import_voice_agent_module()
        with patch.object(voice_agent_module, "AIRouter") as mock_class:
            mock_class.return_value = MagicMock()
            return voice_agent_module.VoiceAgentService()

    def test_second_load_hits_cache_not_db(self, service):
        from app.services.shared.cache import _reset_for_tests

        _reset_for_tests()
        db = _build_mock_db()
        first = service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        calls_after_first = db.table.call_count

        second = service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        assert db.table.call_count == calls_after_first, "cached load must not query"
        assert second == first

    def test_cached_context_is_isolated_from_caller_mutation(self, service):
        from app.services.shared.cache import _reset_for_tests

        _reset_for_tests()
        db = _build_mock_db()
        first = service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        first["onboarding_mode"] = True  # callers mutate their copy

        second = service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        assert "onboarding_mode" not in second

    def test_cache_disabled_via_env(self, service, monkeypatch):
        from app.services.shared.cache import _reset_for_tests

        _reset_for_tests()
        monkeypatch.setenv("VOICE_CONTEXT_CACHE_TTL_SECONDS", "0")
        db = _build_mock_db()
        service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        before = db.table.call_count
        service._load_context(user_id="user-1", db=db, idea_id="idea-1")
        assert db.table.call_count > before, "TTL=0 must disable the cache"
