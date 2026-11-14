"""
Voice Agent Service for Manifest.

The voice agent is responsible for running a professional, context-aware
qualification conversation and rendering a durable note block that can be
persisted into an idea's main note.
"""

import copy
import json
import os
import re
import uuid
from collections.abc import Generator
from html import escape
from typing import Any

from app.services.ai_router import AIRouter
from app.utils.logger import logger

VOICE_NOTE_START = "<!-- manifest-voice-note:start -->"
VOICE_NOTE_END = "<!-- manifest-voice-note:end -->"


class VoiceAgentService:
    """Profile-aware voice ideation and qualification service."""

    ONBOARDING_GROUNDING_HINT = (
        "Session type: guest or home-page voice onboarding. When helpful, briefly clarify that Manifest turns notes into "
        "startup artifacts (canvas, pitch, PRD, research). Publishing to the feed, direct messages, and invest flows "
        "require a full account after signup. Stay concise; one question at a time."
    )

    LANDING_ONBOARDING_GROUNDING_HINT = (
        "Session type: voice-first marketing landing. After your opening, have two conversational beats: "
        "learn how they see themselves (building, investing, scouting, other), then their near-term goal with Manifest. "
        "Then hand off to the web app—no further questions. Stay spoken, concise, one question at a time. "
        "Guest tryouts cannot publish, message, or invest until they create a full account."
    )

    LANDING_QUESTION_TWO = "What is the main outcome you want from Manifest in the next few weeks? One sentence is enough."

    LANDING_CLOSING_MESSAGE = "Starting the Manifest web app for you now."

    LANDING_OPENING_SYSTEM = """You write the first spoken line for Manifest's voice assistant on the public landing page.
Return JSON with a single key: "message" (string).

Voice and tone:
- Warm, unhurried, welcoming—like greeting someone who stepped into a calm, thoughtful workspace.
- Curious and helpful; plain spoken English; no bullets, markdown, or lists.
- Never mention shops, retail, or metaphors about stores to the listener.
- About 35–55 words.
- Invite them naturally to share, in a short phrase, whether they're mainly building, exploring startups as an investor or scout, or here another way—one gentle question.
- Do not list product features; you may say you're glad they're here and that you'll help when they're ready.

If the user prompt includes a first name, use it once naturally."""

    LANDING_TURN_JSON_SYSTEM = """You produce spoken replies for Manifest's voice-first landing onboarding.
Return JSON only with keys: "message" (string, plain spoken English, max 55 words), "landing_onboarding_step" (integer),
"landing_complete" (boolean).

Tone: curious, helpful, calm; acknowledge what they shared.

The user prompt describes the phase and required step/complete flags—follow it exactly."""

    # Shared strategist body. The voice agent's strategist prompts (spoken
    # stream, structured turn, enrichment, finalize) all share this prefix
    # so OpenAI's automatic prompt-prefix cache hits across consecutive
    # turns within a session. Per-call directives are appended at the END
    # — the cache prefix is the BYTE-IDENTICAL portion at the start. Do
    # not edit BASE_VOICE_AGENT_PROMPT without updating
    # `test_voice_agent_prompt_cache_prefix_stable`.
    BASE_VOICE_AGENT_PROMPT = """You are Manifest Voice Strategist, a polished startup advisor for live voice conversations.

Your job:
- Sound like a calm, high-agency operator helping a founder think clearly out loud.
- Be professional, conversational, and concise. Use plain spoken sentences, not bullets or presentation language.
- Use the supplied user profile, current idea note, and prior turns before asking anything.
- Ask at most one question at a time, and only if the answer will materially improve one or more core startup docs:
  pitch deck, PRD, business model canvas, provisional patent, and go-to-market plan.
- Never ask for information that is already known from the profile, current note, or transcript.
- Do not ask routine filler questions once enough context exists. Synthesize instead.
- Briefly acknowledge what matters before asking the next question when helpful, but do not pad the response.
- Prefer high-leverage gaps in this order: target user, painful problem, solution, wedge/MVP, distribution, business model, differentiation, founder edge, major operational or regulatory risk when relevant.
- If the idea is already well-formed, summarize crisply and push toward execution instead of interrogating.
- Use contractions where they sound natural.
"""

    _STRUCTURED_SCHEMA = """{
  "message": "Spoken response",
  "is_qualified": false,
  "summary": "2-4 sentence executive summary",
  "suggested_title": "Short idea title",
  "covered_topics": ["problem", "target_customer"],
  "missing_topics": ["go_to_market", "business_model"],
  "qualification_confidence": 0.0,
  "context": {
    "problem": null,
    "target_customer": null,
    "solution": null,
    "current_alternative": null,
    "differentiation": null,
    "business_model": null,
    "go_to_market": null,
    "product_scope": null,
    "founder_advantage": null,
    "risks": [],
    "open_questions": [],
    "next_step": null
  }
}"""

    SPOKEN_STREAM_DIRECTIVE = """- Keep the spoken reply natural and tight. Maximum 70 words.
- Return plain spoken text only. Do not use JSON, markdown, bullets, labels, or quotation marks around the answer.
"""

    STRUCTURED_DIRECTIVE = (
        """- Keep the spoken reply natural and tight. Maximum 60 words.

Return valid JSON with exactly these top-level keys:
"""
        + _STRUCTURED_SCHEMA
        + """

If a field is unknown, use null or an empty array.
Set "is_qualified" to true only when there is enough clarity to generate strong first drafts of the core startup docs without asking more routine qualification questions.
"""
    )

    ENRICH_DIRECTIVE = (
        """- This is a structured follow-up pass. Ask no new questions.
- Set "message" to the exact spoken assistant reply supplied in the prompt, unchanged.
- Extract the most useful structured startup context for Manifest.

Return valid JSON with exactly these top-level keys:
"""
        + _STRUCTURED_SCHEMA
        + """

If a field is unknown, use null or an empty array.
Set "is_qualified" to true only when there is enough clarity to generate strong first drafts of the core startup docs without asking more routine qualification questions.
"""
    )

    FINALIZE_DIRECTIVE = """- Do not ask questions. Produce a final synthesis from the supplied context and conversation.
- Set "message" to a short spoken completion message in a polished, conversational tone.

Return valid JSON with the same schema as the structured directive.
"""

    # Composed strategist prompts. The byte sequence up to the directive tail
    # is identical across these four — that's the cache prefix. Names kept for
    # backward compat with anything that imported them directly.
    SPOKEN_STREAM_PROMPT = BASE_VOICE_AGENT_PROMPT + SPOKEN_STREAM_DIRECTIVE
    SYSTEM_PROMPT = BASE_VOICE_AGENT_PROMPT + STRUCTURED_DIRECTIVE
    ENRICH_PROMPT = BASE_VOICE_AGENT_PROMPT + ENRICH_DIRECTIVE
    FINALIZE_PROMPT = BASE_VOICE_AGENT_PROMPT + FINALIZE_DIRECTIVE

    REQUIRED_TOPICS = (
        "problem",
        "target_customer",
        "solution",
        "differentiation",
        "go_to_market",
        "business_model",
        "product_scope",
    )

    TOPIC_LABELS = {
        "problem": "Problem",
        "target_customer": "Target customer",
        "solution": "Solution",
        "current_alternative": "Current alternative",
        "differentiation": "Differentiation",
        "business_model": "Business model",
        "go_to_market": "Go-to-market",
        "product_scope": "Product scope",
        "founder_advantage": "Founder advantage",
    }

    def __init__(self):
        logger.info("[VoiceAgent] Initializing voice agent service")
        self.model = os.getenv("VOICE_AGENT_MODEL", "gpt-4o-mini")
        self.router = AIRouter(model=self.model)

        if self.router.is_available():
            logger.info("[VoiceAgent] AIRouter initialized successfully")
        else:
            logger.warning("[VoiceAgent] AIRouter not configured")

    def start_conversation(
        self,
        user_id: str,
        db,
        idea_id: str | None = None,
        onboarding_mode: bool = False,
        landing_onboarding: bool = False,
    ) -> dict[str, Any]:
        """Start a new conversation with profile and idea context loaded."""
        logger.info(
            "[VoiceAgent] Starting conversation for user=%s idea_id=%s onboarding=%s landing=%s",
            user_id,
            idea_id,
            onboarding_mode,
            landing_onboarding,
        )

        context = self._load_context(user_id=user_id, db=db, idea_id=idea_id)
        context["onboarding_mode"] = bool(onboarding_mode)
        use_landing = bool(landing_onboarding) and bool(onboarding_mode)
        context["landing_onboarding"] = use_landing
        initial_message = self._build_initial_response(context)

        msg_list: list[dict[str, str]] = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        if onboarding_mode:
            msg_list.append(
                {
                    "role": "system",
                    "content": self.ONBOARDING_GROUNDING_HINT,
                }
            )
        if use_landing:
            msg_list.append(
                {
                    "role": "system",
                    "content": self.LANDING_ONBOARDING_GROUNDING_HINT,
                }
            )
        msg_list.append(
            {
                "role": "assistant",
                "content": json.dumps(self._assistant_history_payload(initial_message)),
            }
        )

        return {
            "conversation_id": str(uuid.uuid4()),
            "response": initial_message,
            "messages": msg_list,
        }

    def process_message(
        self,
        conversation_messages: list[dict[str, str]],
        user_message: str,
        user_id: str,
        db,
        idea_id: str | None = None,
        onboarding_mode: bool = False,
        landing_onboarding: bool = False,
    ) -> dict[str, Any]:
        """Process a user turn and return a structured qualification update."""
        prepared = self._prepare_turn(
            conversation_messages=conversation_messages,
            user_message=user_message,
            user_id=user_id,
            db=db,
            idea_id=idea_id,
            onboarding_mode=onboarding_mode,
            landing_onboarding=landing_onboarding,
        )
        cleaned_user_message = prepared["cleaned_user_message"]
        logger.info("[VoiceAgent] Processing user turn (chars=%s)", len(cleaned_user_message))

        if not cleaned_user_message:
            return {
                "response": self._error_response(
                    "I didn't catch anything usable there. Give me the idea again in one sentence."
                ),
                "messages": conversation_messages,
            }

        context = prepared["context"]
        normalized_history = prepared["normalized_history"]

        if context.get("landing_onboarding"):
            landing_reply = self._process_landing_onboarding_turn(
                conversation_messages=conversation_messages,
                user_message=cleaned_user_message,
                context=context,
                normalized_history=normalized_history,
            )
            updated_messages = list(conversation_messages)
            updated_messages.append({"role": "user", "content": cleaned_user_message})
            updated_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(self._assistant_history_payload(landing_reply)),
                }
            )
            return {"response": landing_reply, "messages": updated_messages}

        if self._looks_like_operational_message(cleaned_user_message):
            redirect = self._operational_redirect_response(context)
            updated_messages = list(conversation_messages)
            updated_messages.append({"role": "user", "content": cleaned_user_message})
            updated_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(self._assistant_history_payload(redirect)),
                }
            )
            return {"response": redirect, "messages": updated_messages}

        if not self.router.is_available():
            logger.error("[VoiceAgent] AIRouter not available")
            fallback = self._fallback_structured_response(
                context, normalized_history, cleaned_user_message
            )
            updated_messages = list(conversation_messages)
            updated_messages.append({"role": "user", "content": cleaned_user_message})
            updated_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(self._assistant_history_payload(fallback)),
                }
            )
            return {"response": fallback, "messages": updated_messages}

        try:
            spoken_message = "".join(
                self.stream_spoken_turn(
                    context=context,
                    normalized_history=normalized_history,
                    latest_user_message=cleaned_user_message,
                )
            )
            parsed_response = self.enrich_structured_turn(
                context=context,
                normalized_history=normalized_history,
                user_message=cleaned_user_message,
                assistant_message=spoken_message,
            )
        except Exception as exc:
            logger.error("[VoiceAgent] Error processing message: %s", exc)
            parsed_response = self._fallback_structured_response(
                context, normalized_history, cleaned_user_message
            )

        updated_messages = list(conversation_messages)
        updated_messages.append({"role": "user", "content": cleaned_user_message})
        updated_messages.append(
            {
                "role": "assistant",
                "content": json.dumps(self._assistant_history_payload(parsed_response)),
            }
        )

        return {
            "response": parsed_response,
            "messages": updated_messages,
        }

    def stream_spoken_turn(
        self,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
        latest_user_message: str,
    ) -> Generator[str, None, None]:
        """Stream the spoken assistant reply for a live voice turn."""
        if not self.router.is_available():
            raise RuntimeError("AIRouter not configured for streaming voice turns.")

        prompt_messages = self._build_prompt_messages(
            context=context,
            normalized_history=normalized_history,
            latest_user_message=latest_user_message,
            system_prompt=self.SPOKEN_STREAM_PROMPT,
        )

        yielded_any = False
        for chunk in self.router.chat_stream(
            prompt=prompt_messages,
            model=self.model,
            temperature=0.55,
            max_tokens=220,
        ):
            if not chunk:
                continue
            yielded_any = True
            yield chunk

        if not yielded_any:
            raise RuntimeError("Voice stream returned no spoken content.")

    def enrich_structured_turn(
        self,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
        user_message: str,
        assistant_message: str,
    ) -> dict[str, Any]:
        """Produce the structured note payload after the spoken reply is known."""
        cleaned_assistant_message = self._normalize_text(assistant_message)
        if not cleaned_assistant_message:
            return self._fallback_structured_response(context, normalized_history, user_message)

        if not self.router.is_available():
            return self._fallback_structured_response(context, normalized_history, user_message)

        prompt_messages = self._build_prompt_messages(
            context=context,
            normalized_history=normalized_history,
            latest_user_message=user_message,
            system_prompt=self.ENRICH_PROMPT,
        )
        prompt_messages.append(
            {
                "role": "system",
                "content": "Exact spoken assistant reply (copy into message unchanged):\n"
                + cleaned_assistant_message,
            }
        )

        ai_result = self.router.chat_json(
            prompt=prompt_messages,
            model=self.model,
            temperature=0.2,
        )
        ai_result["message"] = cleaned_assistant_message
        return self._normalize_model_response(
            raw=ai_result,
            user_message=user_message,
            context=context,
            normalized_history=normalized_history,
        )

    def qualify_idea(
        self,
        conversation_messages: list[dict[str, str]],
        user_id: str,
        db,
        idea_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a finalized idea snapshot from the conversation."""
        logger.info("[VoiceAgent] Finalizing idea for user=%s idea_id=%s", user_id, idea_id)

        context = self._load_context(user_id=user_id, db=db, idea_id=idea_id)
        normalized_history = self._normalize_conversation(conversation_messages)

        if self.router.is_available():
            try:
                ai_result = self.router.chat_json(
                    prompt=self._build_prompt_messages(
                        context=context,
                        normalized_history=normalized_history,
                        latest_user_message=None,
                        system_prompt=self.FINALIZE_PROMPT,
                    ),
                    model=self.model,
                    temperature=0.2,
                )
                structured = self._normalize_model_response(
                    raw=ai_result,
                    user_message="",
                    context=context,
                    normalized_history=normalized_history,
                )
            except Exception as exc:
                logger.error("[VoiceAgent] Error finalizing idea: %s", exc)
                structured = self._fallback_structured_response(context, normalized_history, "")
        else:
            structured = self._fallback_structured_response(context, normalized_history, "")

        description = self._merge_voice_note(
            context.get("idea_description"),
            structured.get("voice_note_html"),
        )

        return {
            "title": structured.get("suggested_title") or self._fallback_title(context, ""),
            "description": description
            or structured.get("voice_note_html")
            or "<p>Voice session captured.</p>",
            "summary": structured.get("summary"),
        }

    def _build_initial_response(self, context: dict[str, Any]) -> dict[str, Any]:
        """Initial turn: empty spoken line by default; guest/home onboarding gets a short spoken greeting."""
        idea_title = (context.get("idea_title") or "").strip()
        has_idea_context = bool(context.get("idea_note_excerpt"))

        if context.get("onboarding_mode"):
            if context.get("landing_onboarding"):
                spoken = self._landing_opening_message(context)
            else:
                spoken = (
                    "Welcome to Manifest. I help turn rough ideas into structured startup material like a canvas, pitch, and research context. "
                    "You are on a guest tryout, so publishing, messaging, and investing stay locked until you create a full account. "
                    "In one sentence, what problem or idea is on your mind?"
                )
            base = {
                "message": spoken,
                "is_qualified": False,
                "summary": self._existing_summary(context),
                "suggested_title": idea_title or None,
                "transcript": None,
                "voice_note_html": context.get("idea_voice_note_html"),
                "covered_topics": [],
                "missing_topics": list(self.REQUIRED_TOPICS),
                "qualification_confidence": 0.05,
                "landing_onboarding_step": 1 if context.get("landing_onboarding") else None,
                "landing_complete": False,
                "context": {
                    "problem": None,
                    "target_customer": None,
                    "solution": None,
                    "current_alternative": None,
                    "differentiation": None,
                    "business_model": None,
                    "go_to_market": None,
                    "product_scope": None,
                    "founder_advantage": None,
                    "risks": [],
                    "open_questions": [],
                    "next_step": None,
                },
            }
            return base

        return {
            "message": "",
            "is_qualified": False,
            "summary": self._existing_summary(context),
            "suggested_title": idea_title or None,
            "transcript": None,
            "voice_note_html": context.get("idea_voice_note_html"),
            "covered_topics": [],
            "missing_topics": list(self.REQUIRED_TOPICS),
            "qualification_confidence": 0.15 if has_idea_context else 0.05,
            "landing_onboarding_step": None,
            "landing_complete": False,
            "context": {
                "problem": None,
                "target_customer": None,
                "solution": None,
                "current_alternative": None,
                "differentiation": None,
                "business_model": None,
                "go_to_market": None,
                "product_scope": None,
                "founder_advantage": None,
                "risks": [],
                "open_questions": [],
                "next_step": None,
            },
        }

    def _load_context(self, user_id: str, db, idea_id: str | None) -> dict[str, Any]:
        # Voice turns hit this on every request (2 DB round-trips before the
        # first LLM token can stream). The profile/idea rows are effectively
        # static within a conversation, so a short shared cache trims
        # 100-500ms off time-to-first-audio per turn. TTL is deliberately
        # small: a stale idea title/description self-corrects within a
        # minute, and the conversation history carries the live state.
        from app.services.cache_service import cache_get, cache_set

        ttl_seconds = int(os.getenv("VOICE_CONTEXT_CACHE_TTL_SECONDS", "60") or 0)
        cache_key = f"voice:context:{user_id}:{idea_id or '-'}"
        if ttl_seconds > 0:
            cached = cache_get(cache_key)
            if isinstance(cached, dict):
                # Deep-copy: the in-process cache backend returns the stored
                # object itself, and callers mutate the context (onboarding
                # flags). Redis already round-trips through JSON.
                return copy.deepcopy(cached)

        user_record: dict[str, Any] = {}
        idea_record: dict[str, Any] = {}

        try:
            user_response = (
                db.table("users")
                .select("user_id, email, username, first_name, last_name, country, state, bio")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            user_record = user_response.data or {}
        except Exception as exc:
            logger.warning("[VoiceAgent] Failed to load user context: %s", exc)

        if idea_id:
            try:
                idea_response = (
                    db.table("ideas")
                    .select("idea_id, title, description")
                    .eq("idea_id", idea_id)
                    .eq("user_id", user_id)
                    .single()
                    .execute()
                )
                idea_record = idea_response.data or {}
            except Exception as exc:
                logger.warning("[VoiceAgent] Failed to load idea context: %s", exc)

        idea_description = idea_record.get("description") or ""
        context = {
            "user": user_record,
            "idea_id": idea_record.get("idea_id"),
            "idea_title": idea_record.get("title"),
            "idea_description": idea_description,
            "idea_note_excerpt": self._truncate(
                self._normalize_text(self._strip_voice_note(idea_description)), 2400
            ),
            "idea_voice_note_html": self._extract_voice_note(idea_description),
        }
        if ttl_seconds > 0 and (user_record or idea_record):
            # Never cache a fully-empty context: a transient DB error would
            # otherwise pin "no user / no idea" for the TTL window.
            cache_set(cache_key, copy.deepcopy(context), ttl_seconds)
        return context

    def _landing_onboarding_base_context(self) -> dict[str, Any]:
        return {
            "problem": None,
            "target_customer": None,
            "solution": None,
            "current_alternative": None,
            "differentiation": None,
            "business_model": None,
            "go_to_market": None,
            "product_scope": None,
            "founder_advantage": None,
            "risks": [],
            "open_questions": [],
            "next_step": None,
        }

    def _landing_opening_message(self, context: dict[str, Any]) -> str:
        user = context.get("user") or {}
        first_name = self._optional_text(user.get("first_name"))
        personalize = ""
        if first_name:
            personalize = f"The visitor's first name is {first_name}; use it once in the greeting if it sounds natural.\n"

        if self.router.is_available():
            try:
                raw = self.router.chat_json(
                    prompt=personalize
                    + "Write only the opening spoken message for the landing voice session.",
                    system_prompt=self.LANDING_OPENING_SYSTEM,
                    model=self.model,
                    temperature=0.55,
                )
                msg = self._optional_text(raw.get("message"))
                if msg and len(msg.strip()) > 20:
                    return msg.strip()
            except Exception as exc:
                logger.warning("[VoiceAgent] landing opening LLM failed: %s", exc)

        return self._landing_opening_fallback(first_name)

    def _landing_opening_fallback(self, first_name: str | None = None) -> str:
        if first_name:
            return (
                f"Hi {first_name}, welcome to Manifest—I'm really glad you're here. "
                "I'm here to help you shape an idea when you're ready. "
                "In a few words, would you say you're mainly building something, exploring startups as an investor or scout, "
                "or here in another way?"
            )
        return (
            "Hi, welcome to Manifest—I'm glad you're here. "
            "I'm here to help you turn a rough idea into something concrete when you're ready. "
            "In a short phrase, how would you describe yourself here—mostly building, exploring opportunities, or something else?"
        )

    def _validate_landing_turn_payload(
        self, raw: Any, prior_user_count: int
    ) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        msg = self._optional_text(raw.get("message"))
        if not msg or len(msg.strip()) < 8:
            return None

        if prior_user_count == 0:
            step, complete = 2, False
        elif prior_user_count == 1:
            step, complete = 3, True
        else:
            return None

        return {
            "message": msg.strip(),
            "landing_onboarding_step": step,
            "landing_complete": complete,
        }

    def _fetch_landing_turn_via_llm(
        self,
        prior_user_count: int,
        user_message: str,
        normalized_history: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        lines: list[str] = []
        for message in normalized_history[-12:]:
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if role and content:
                lines.append(f"{role}: {content}")
        transcript = "\n".join(lines)

        if prior_user_count == 0:
            phase = (
                "Phase: The visitor just answered your opening question.\n"
                "JSON requirements: Thank them briefly. Ask ONE new question about what they most want Manifest "
                "to help them achieve in the next few weeks.\n"
                "Set landing_onboarding_step to 2 and landing_complete to false."
            )
        elif prior_user_count == 1:
            phase = (
                "Phase: They answered your question about near-term goals.\n"
                "JSON requirements: Thank them warmly in one or two short sentences. Say you're opening the Manifest "
                "workspace for them now. No follow-up questions.\n"
                "Set landing_onboarding_step to 3 and landing_complete to true."
            )
        else:
            return None

        prompt = f"Conversation transcript:\n{transcript}\n\nTheir latest message:\n{user_message}\n\n{phase}"
        raw = self.router.chat_json(
            prompt=prompt,
            system_prompt=self.LANDING_TURN_JSON_SYSTEM,
            model=self.model,
            temperature=0.65,
        )
        return self._validate_landing_turn_payload(raw, prior_user_count)

    def _landing_turn_fallback(self, prior_user_count: int, user_message: str) -> dict[str, Any]:
        if prior_user_count == 0:
            spoken = (
                "Thank you—that helps. "
                "What would you most like Manifest to help you produce or clarify in the next couple of weeks?"
            )
            return {"message": spoken, "landing_onboarding_step": 2, "landing_complete": False}

        return {
            "message": self.LANDING_CLOSING_MESSAGE,
            "landing_onboarding_step": 3,
            "landing_complete": True,
        }

    def _process_landing_onboarding_turn(
        self,
        conversation_messages: list[dict[str, str]],
        user_message: str,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Landing flow: opening from start_conversation; two user turns via LLM with deterministic fallback."""
        prior_user_count = sum(1 for m in conversation_messages if m.get("role") == "user")

        if prior_user_count >= 2:
            msg = "You are set. Open the workspace from the screen if you need anything else."
            payload = {
                "message": msg,
                "is_qualified": False,
                "summary": self._existing_summary(context),
                "suggested_title": context.get("idea_title") or None,
                "transcript": user_message or None,
                "voice_note_html": context.get("idea_voice_note_html"),
                "covered_topics": [],
                "missing_topics": list(self.REQUIRED_TOPICS),
                "qualification_confidence": 0.1,
                "landing_onboarding_step": 3,
                "landing_complete": True,
                "context": self._landing_onboarding_base_context(),
            }
            transcript_entries = self._build_transcript_entries(
                normalized_history=normalized_history,
                latest_user_message=user_message,
                latest_assistant_message=msg,
            )
            payload["voice_note_html"] = self._render_voice_note(
                context, payload, transcript_entries
            )
            return payload

        core: dict[str, Any] | None = None
        if self.router.is_available() and prior_user_count < 2:
            try:
                core = self._fetch_landing_turn_via_llm(
                    prior_user_count, user_message, normalized_history
                )
            except Exception as exc:
                logger.warning("[VoiceAgent] landing turn LLM failed: %s", exc)

        if not core:
            fb = self._landing_turn_fallback(prior_user_count, user_message)
            core = {
                "message": fb["message"],
                "landing_onboarding_step": fb["landing_onboarding_step"],
                "landing_complete": fb["landing_complete"],
            }

        spoken = core["message"]
        if prior_user_count == 0:
            summary = f"Landing intent: {user_message}"
            confidence = 0.12
        else:
            summary = f"Landing goals: {user_message}"
            confidence = 0.2

        payload = {
            "message": spoken,
            "is_qualified": False,
            "summary": summary,
            "suggested_title": context.get("idea_title")
            or self._fallback_title(context, user_message),
            "transcript": user_message or None,
            "voice_note_html": None,
            "covered_topics": [],
            "missing_topics": list(self.REQUIRED_TOPICS),
            "qualification_confidence": confidence,
            "landing_onboarding_step": core["landing_onboarding_step"],
            "landing_complete": core["landing_complete"],
            "context": self._landing_onboarding_base_context(),
        }
        transcript_entries = self._build_transcript_entries(
            normalized_history=normalized_history,
            latest_user_message=user_message,
            latest_assistant_message=spoken,
        )
        payload["voice_note_html"] = self._render_voice_note(context, payload, transcript_entries)
        return payload

    def _prepare_turn(
        self,
        conversation_messages: list[dict[str, str]],
        user_message: str,
        user_id: str,
        db,
        idea_id: str | None,
        onboarding_mode: bool = False,
        landing_onboarding: bool = False,
    ) -> dict[str, Any]:
        """Load the shared context used by both spoken and structured turn phases."""
        cleaned_user_message = self._normalize_text(user_message)
        context = self._load_context(user_id=user_id, db=db, idea_id=idea_id)
        context["onboarding_mode"] = bool(onboarding_mode)
        use_landing = bool(landing_onboarding) and bool(onboarding_mode)
        context["landing_onboarding"] = use_landing
        normalized_history = self._normalize_conversation(conversation_messages)
        return {
            "cleaned_user_message": cleaned_user_message,
            "context": context,
            "normalized_history": normalized_history,
        }

    def _cache_bust_prefix(self) -> str:
        """When VOICE_AGENT_PROMPT_CACHE_ENABLED=false, return a per-request
        nonce that breaks OpenAI's prompt-prefix cache. Default empty string
        (cache enabled). Required by the manifest-pitch-reel-cost-guard skill
        as an explicit kill switch for AI cost behaviour."""
        flag = os.getenv("VOICE_AGENT_PROMPT_CACHE_ENABLED", "true").strip().lower()
        if flag in {"false", "0", "no", "off"}:
            return f"<!-- voice-cache-disabled {uuid.uuid4()} -->\n"
        return ""

    def _build_prompt_messages(
        self,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
        latest_user_message: str | None,
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        # Grounding context is keyed by stability so OpenAI's prompt-prefix
        # cache can match the largest possible prefix across turns within a
        # session. user_profile is stable per-session and goes first;
        # current_idea metadata is semi-stable; main_note_excerpt is volatile
        # mid-session so it sits at the tail of the grounding block.
        grounding_context: dict[str, Any] = {
            "user_profile": self._build_profile_context(context.get("user") or {}),
        }
        if context.get("onboarding_mode"):
            grounding_context["voice_onboarding"] = self.ONBOARDING_GROUNDING_HINT
        grounding_context["current_idea"] = {
            "idea_id": context.get("idea_id"),
            "title": context.get("idea_title"),
            "main_note_excerpt": context.get("idea_note_excerpt"),
        }

        cache_bust = self._cache_bust_prefix()

        prompt_messages: list[dict[str, Any]] = [
            {"role": "system", "content": cache_bust + system_prompt},
            {
                "role": "system",
                "content": "Use this grounding context before you decide what to ask or summarize:\n"
                + json.dumps(grounding_context, indent=2),
            },
        ]
        prompt_messages.extend(normalized_history[-12:])

        if latest_user_message:
            prompt_messages.append({"role": "user", "content": latest_user_message})

        return prompt_messages

    def _normalize_conversation(
        self, conversation_messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in conversation_messages:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue

            content = message.get("content") or ""
            if role == "assistant":
                parsed = self._parse_assistant_content(content)
                content = parsed.get("message") or parsed.get("summary") or ""

            cleaned = self._normalize_text(content)
            if cleaned:
                normalized.append({"role": role, "content": cleaned})
        return normalized

    def _normalize_model_response(
        self,
        raw: dict[str, Any],
        user_message: str,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        model_context = raw.get("context")
        if not isinstance(model_context, dict):
            model_context = {}

        normalized_context = {
            "problem": self._optional_text(model_context.get("problem")),
            "target_customer": self._optional_text(model_context.get("target_customer")),
            "solution": self._optional_text(model_context.get("solution")),
            "current_alternative": self._optional_text(model_context.get("current_alternative")),
            "differentiation": self._optional_text(model_context.get("differentiation")),
            "business_model": self._optional_text(model_context.get("business_model")),
            "go_to_market": self._optional_text(model_context.get("go_to_market")),
            "product_scope": self._optional_text(model_context.get("product_scope")),
            "founder_advantage": self._optional_text(model_context.get("founder_advantage")),
            "risks": self._clean_list(model_context.get("risks")),
            "open_questions": self._clean_list(model_context.get("open_questions")),
            "next_step": self._optional_text(model_context.get("next_step")),
        }

        covered_topics = self._dedupe_topics(
            self._clean_list(raw.get("covered_topics"))
            + [topic for topic in self.REQUIRED_TOPICS if normalized_context.get(topic)]
        )

        inferred_missing = [topic for topic in self.REQUIRED_TOPICS if topic not in covered_topics]
        missing_topics = self._dedupe_topics(
            self._clean_list(raw.get("missing_topics")) + inferred_missing
        )

        qualification_confidence = self._clamp_float(
            raw.get("qualification_confidence"), default=0.55
        )

        summary = self._optional_text(raw.get("summary")) or self._build_summary(
            normalized_context, context
        )
        suggested_title = (
            self._optional_text(raw.get("suggested_title"))
            or context.get("idea_title")
            or self._fallback_title(context, user_message)
        )

        is_qualified = bool(raw.get("is_qualified"))
        if not is_qualified:
            is_qualified = qualification_confidence >= 0.78 and len(missing_topics) <= 2

        if not normalized_context["open_questions"]:
            normalized_context["open_questions"] = [
                f"Clarify {self.TOPIC_LABELS.get(topic, topic.replace('_', ' ')).lower()}."
                for topic in missing_topics[:3]
            ]

        transcript_entries = self._build_transcript_entries(
            normalized_history=normalized_history,
            latest_user_message=user_message,
            latest_assistant_message=self._optional_text(raw.get("message"))
            or "I captured that. Keep going.",
        )

        parsed = {
            "message": self._optional_text(raw.get("message")) or "I captured that. Keep going.",
            "is_qualified": is_qualified,
            "summary": summary,
            "suggested_title": suggested_title,
            "transcript": user_message or None,
            "covered_topics": covered_topics,
            "missing_topics": missing_topics,
            "qualification_confidence": qualification_confidence,
            "context": normalized_context,
        }
        parsed["voice_note_html"] = self._render_voice_note(context, parsed, transcript_entries)
        return parsed

    def _fallback_structured_response(
        self,
        context: dict[str, Any],
        normalized_history: list[dict[str, str]],
        user_message: str,
    ) -> dict[str, Any]:
        summary = self._existing_summary(context)
        if user_message:
            summary = summary or f"The founder is exploring: {user_message}"

        message = (
            "I captured that and updated the working note. "
            "If you want to sharpen it further, give me the customer, the pain, or the initial wedge."
        )

        fallback = {
            "message": message,
            "is_qualified": False,
            "summary": summary,
            "suggested_title": context.get("idea_title")
            or self._fallback_title(context, user_message),
            "transcript": user_message or None,
            "covered_topics": [],
            "missing_topics": list(self.REQUIRED_TOPICS),
            "qualification_confidence": 0.35,
            "context": {
                "problem": None,
                "target_customer": None,
                "solution": None,
                "current_alternative": None,
                "differentiation": None,
                "business_model": None,
                "go_to_market": None,
                "product_scope": None,
                "founder_advantage": None,
                "risks": [],
                "open_questions": [
                    "Clarify the user and pain point.",
                    "Clarify the initial solution wedge.",
                ],
                "next_step": "Capture the core customer pain and first product wedge.",
            },
        }

        transcript_entries = self._build_transcript_entries(
            normalized_history=normalized_history,
            latest_user_message=user_message,
            latest_assistant_message=message,
        )
        fallback["voice_note_html"] = self._render_voice_note(context, fallback, transcript_entries)
        return fallback

    def _operational_redirect_response(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "message": (
                "That sounded like an app-control comment, not startup context. "
                "I am not adding it to the idea note. Use the built-in voice commands for app control, "
                "or give me the user, pain, solution, or wedge."
            ),
            "is_qualified": False,
            "summary": self._existing_summary(context),
            "suggested_title": context.get("idea_title") or None,
            "transcript": None,
            "voice_note_html": context.get("idea_voice_note_html"),
            "covered_topics": [],
            "missing_topics": list(self.REQUIRED_TOPICS),
            "qualification_confidence": 0.15 if context.get("idea_note_excerpt") else 0.05,
            "context": {
                "problem": None,
                "target_customer": None,
                "solution": None,
                "current_alternative": None,
                "differentiation": None,
                "business_model": None,
                "go_to_market": None,
                "product_scope": None,
                "founder_advantage": None,
                "risks": [],
                "open_questions": [
                    "Clarify the user and pain point.",
                    "Clarify the initial solution wedge.",
                ],
                "next_step": "Capture the core customer pain and first product wedge.",
            },
        }

    def _render_voice_note(
        self,
        context: dict[str, Any],
        response: dict[str, Any],
        transcript_entries: list[dict[str, str]],
    ) -> str:
        structured_context = response.get("context") or {}
        open_questions = self._clean_list(structured_context.get("open_questions"))
        risks = self._clean_list(structured_context.get("risks"))
        covered_topics = self._clean_list(response.get("covered_topics"))
        missing_topics = self._clean_list(response.get("missing_topics"))

        summary_html = ""
        if response.get("summary"):
            summary_html = f"<p>{escape(response['summary'])}</p>"

        details_items = []
        for key in (
            "problem",
            "target_customer",
            "solution",
            "current_alternative",
            "differentiation",
            "business_model",
            "go_to_market",
            "product_scope",
            "founder_advantage",
        ):
            value = structured_context.get(key)
            if value:
                details_items.append(
                    f"<li><strong>{escape(self.TOPIC_LABELS.get(key, key.replace('_', ' ').title()))}:</strong> {escape(value)}</li>"
                )

        risk_html = ""
        if risks:
            risk_html = (
                "<h3>Risks To Watch</h3><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in risks)
                + "</ul>"
            )

        missing_html = ""
        if missing_topics:
            missing_html = (
                "<h3>Open Qualification Areas</h3><ul>"
                + "".join(
                    f"<li>{escape(self.TOPIC_LABELS.get(topic, topic.replace('_', ' ').title()))}</li>"
                    for topic in missing_topics
                )
                + "</ul>"
            )

        questions_html = ""
        if open_questions:
            questions_html = (
                "<h3>Open Questions</h3><ul>"
                + "".join(f"<li>{escape(item)}</li>" for item in open_questions)
                + "</ul>"
            )

        transcript_html = (
            "<ol>"
            + "".join(
                f"<li><strong>{'Founder' if entry['role'] == 'user' else 'Manifest AI'}:</strong> {escape(entry['content'])}</li>"
                for entry in transcript_entries
            )
            + "</ol>"
        )

        # NOTE (#21): the previous implementation emitted
        #     <p><em>Profile context used: ...</em></p>
        # into the user-visible Voice Strategy Session note. That string is
        # internal prompt-context for the model and should never be rendered
        # in the founder transcript. We still build the profile context above
        # via `_build_profile_context` for use by spoken-stream prompts (see
        # `user_profile` in the spoken stream payload), but it must not leak
        # into the persisted note HTML.
        profile_line = ""

        covered_html = ""
        if covered_topics:
            covered_html = (
                "<p><strong>Coverage:</strong> "
                + escape(", ".join(self.TOPIC_LABELS.get(topic, topic) for topic in covered_topics))
                + "</p>"
            )

        status = (
            "Qualified for first-pass docs" if response.get("is_qualified") else "Still qualifying"
        )
        title = response.get("suggested_title") or context.get("idea_title") or "Voice Session"
        next_step = self._optional_text(structured_context.get("next_step"))
        next_step_html = (
            f"<p><strong>Next step:</strong> {escape(next_step)}</p>" if next_step else ""
        )

        return (
            f"{VOICE_NOTE_START}"
            '<section data-manifest-voice-note="true">'
            "<h2>Voice Strategy Session</h2>"
            f"<p><strong>Working title:</strong> {escape(title)}</p>"
            f"<p><strong>Status:</strong> {escape(status)} "
            f"(confidence {int(round((response.get('qualification_confidence') or 0) * 100))}%)</p>"
            f"{summary_html}"
            f"{covered_html}"
            "<h3>Working Brief</h3>"
            f"<ul>{''.join(details_items) or '<li>Context is still being gathered.</li>'}</ul>"
            f"{missing_html}"
            f"{questions_html}"
            f"{risk_html}"
            f"{next_step_html}"
            "<h3>Transcript</h3>"
            f"{transcript_html}"
            f"{profile_line}"
            "</section>"
            f"{VOICE_NOTE_END}"
        )

    def _build_transcript_entries(
        self,
        normalized_history: list[dict[str, str]],
        latest_user_message: str,
        latest_assistant_message: str,
    ) -> list[dict[str, str]]:
        entries = list(normalized_history)
        if latest_user_message:
            entries.append({"role": "user", "content": latest_user_message})
        if latest_assistant_message:
            entries.append({"role": "assistant", "content": latest_assistant_message})
        return entries[-24:]

    def _assistant_history_payload(self, response: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "message": response.get("message"),
            "is_qualified": response.get("is_qualified", False),
            "summary": response.get("summary"),
            "suggested_title": response.get("suggested_title"),
            "covered_topics": response.get("covered_topics") or [],
            "missing_topics": response.get("missing_topics") or [],
            "qualification_confidence": response.get("qualification_confidence", 0.0),
        }
        if response.get("landing_onboarding_step") is not None:
            payload["landing_onboarding_step"] = response.get("landing_onboarding_step")
        if response.get("landing_complete") is not None:
            payload["landing_complete"] = bool(response.get("landing_complete"))
        return payload

    def _build_profile_context(self, user: dict[str, Any]) -> str:
        parts = []
        first_name = self._optional_text(user.get("first_name"))
        last_name = self._optional_text(user.get("last_name"))
        if first_name or last_name:
            parts.append("name: " + " ".join(part for part in [first_name, last_name] if part))
        if user.get("username"):
            parts.append(f"username: {self._normalize_text(str(user['username']))}")
        if user.get("country"):
            parts.append(f"country: {self._normalize_text(str(user['country']))}")
        if user.get("state"):
            parts.append(f"state: {self._normalize_text(str(user['state']))}")
        if user.get("bio"):
            parts.append(f"bio: {self._truncate(self._normalize_text(str(user['bio'])), 280)}")
        return "; ".join(parts)

    def _build_summary(
        self, structured_context: dict[str, Any], context: dict[str, Any]
    ) -> str | None:
        parts = []
        problem = structured_context.get("problem")
        target_customer = structured_context.get("target_customer")
        solution = structured_context.get("solution")
        differentiation = structured_context.get("differentiation")

        if target_customer and problem:
            parts.append(f"{target_customer} face {problem}.")
        elif problem:
            parts.append(f"The startup addresses {problem}.")

        if solution:
            parts.append(f"The proposed solution is {solution}.")
        if differentiation:
            parts.append(f"It stands out through {differentiation}.")

        if parts:
            return " ".join(parts)
        return self._existing_summary(context)

    def _existing_summary(self, context: dict[str, Any]) -> str | None:
        excerpt = context.get("idea_note_excerpt")
        if excerpt:
            return self._truncate(excerpt, 220)
        return None

    def _fallback_title(self, context: dict[str, Any], user_message: str) -> str:
        if context.get("idea_title"):
            return context["idea_title"]

        cleaned = self._normalize_text(user_message)
        if cleaned:
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", cleaned)
            if words:
                return " ".join(word.capitalize() for word in words[:4])
        return "Voice Idea"

    def _looks_like_operational_message(self, text: str) -> bool:
        cleaned = self._normalize_text(text).lower()
        if not cleaned:
            return False

        operational_targets = (
            "folder",
            "file",
            "browser",
            "tab",
            "screen",
            "window",
            "terminal",
            "screenshot",
        )
        operational_actions = (
            "open",
            "close",
            "show",
            "click",
            "scroll",
            "navigate",
            "browse",
        )

        if "why can't you" in cleaned and any(target in cleaned for target in operational_targets):
            return True

        has_target = any(target in cleaned for target in operational_targets)
        has_action = any(
            re.search(rf"\b{re.escape(action)}\b", cleaned) for action in operational_actions
        )
        return has_target and has_action

    def _merge_voice_note(
        self, existing_description: str | None, voice_note_html: str | None
    ) -> str | None:
        if not voice_note_html:
            return existing_description

        current = existing_description or ""
        if VOICE_NOTE_START in current and VOICE_NOTE_END in current:
            pattern = re.compile(
                rf"{re.escape(VOICE_NOTE_START)}[\s\S]*?{re.escape(VOICE_NOTE_END)}",
                re.MULTILINE,
            )
            return pattern.sub(voice_note_html, current, count=1)

        if current.strip():
            return current.rstrip() + "\n\n" + voice_note_html
        return voice_note_html

    def _extract_voice_note(self, description: str) -> str | None:
        if (
            not description
            or VOICE_NOTE_START not in description
            or VOICE_NOTE_END not in description
        ):
            return None
        match = re.search(
            rf"{re.escape(VOICE_NOTE_START)}[\s\S]*?{re.escape(VOICE_NOTE_END)}",
            description,
            re.MULTILINE,
        )
        return match.group(0) if match else None

    def _strip_voice_note(self, description: str) -> str:
        if not description:
            return ""
        return re.sub(
            rf"{re.escape(VOICE_NOTE_START)}[\s\S]*?{re.escape(VOICE_NOTE_END)}",
            "",
            description,
            flags=re.MULTILINE,
        )

    def _parse_assistant_content(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"message": content}

    def _error_response(self, message: str) -> dict[str, Any]:
        return {
            "message": message,
            "is_qualified": False,
            "summary": None,
            "suggested_title": None,
            "transcript": None,
            "voice_note_html": None,
            "covered_topics": [],
            "missing_topics": list(self.REQUIRED_TOPICS),
            "qualification_confidence": 0.0,
            "context": {
                "problem": None,
                "target_customer": None,
                "solution": None,
                "current_alternative": None,
                "differentiation": None,
                "business_model": None,
                "go_to_market": None,
                "product_scope": None,
                "founder_advantage": None,
                "risks": [],
                "open_questions": [],
                "next_step": None,
            },
        }

    def _clean_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [
                self._normalize_text(str(item)) for item in value if self._normalize_text(str(item))
            ]
        if isinstance(value, str):
            cleaned = self._normalize_text(value)
            return [cleaned] if cleaned else []
        return []

    def _dedupe_topics(self, topics: list[str]) -> list[str]:
        seen = set()
        normalized: list[str] = []
        for topic in topics:
            key = self._normalize_text(topic).lower().replace(" ", "_")
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append(key)
        return normalized

    def _normalize_text(self, value: str) -> str:
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        text = re.sub(r"&nbsp;|&#160;", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = self._normalize_text(str(value))
        return cleaned or None

    def _clamp_float(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(1.0, number))

    def _truncate(self, value: str | None, limit: int) -> str | None:
        if not value:
            return value
        if len(value) <= limit:
            return value
        return value[: max(limit - 3, 0)].rstrip() + "..."


voice_agent_service = VoiceAgentService()
