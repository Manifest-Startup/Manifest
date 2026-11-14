import json
import os
from typing import Any

from app.prompts import prompt_path
from app.utils.logger import logger


def _pitch_deck_web_research_enabled() -> bool:
    return os.getenv("PITCH_DECK_WEB_RESEARCH", "").strip().lower() in ("1", "true", "yes")


def _truncate_text(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def _idea_snippet(description: str, max_len: int = 320) -> str:
    return _truncate_text(description.replace("\n", " "), max_len)


def _gather_pitch_deck_research(ai_layer: Any, description: str) -> str | None:
    """
    Optional web-grounded JSON snippets (OpenAI web search) appended to the user prompt.
    Fails open: any error or empty result yields None.
    """
    if not _pitch_deck_web_research_enabled():
        return None
    if not getattr(ai_layer, "perform_web_search_json", None):
        logger.info("[PitchDeck] Web research skipped: ai_layer has no perform_web_search_json")
        return None

    snippet = _idea_snippet(description, 360)
    queries = [
        f"Startup idea: {snippet}. Summarize market size, growth, and key customer segments. Flag uncertainty.",
        f"Startup idea: {snippet}. List likely competitors or substitutes and how a new entrant could differ.",
        f"Startup idea: {snippet}. Note regulatory, trust, or operational risks to validate early.",
    ]
    system_prompt = (
        'Reply with JSON only: {"takeaways": ["..."], "confidence": "high|medium|low"}. '
        "At most 4 takeaways, each under 220 characters. No URLs in strings; avoid definitive claims without evidence."
    )

    parts: list[str] = []
    per_query_cap = 2000
    for i, q in enumerate(queries, start=1):
        try:
            out = ai_layer.perform_web_search_json(q, system_prompt=system_prompt)
            data = out.get("data")
            if isinstance(data, dict | list):
                piece = json.dumps(data, ensure_ascii=False)
            else:
                piece = str(data) if data is not None else ""
            piece = piece.strip()
            if piece:
                parts.append(f"Query {i} result: {_truncate_text(piece, per_query_cap)}")
        except Exception as exc:
            logger.warning("[PitchDeck] Web research query %s failed: %s", i, exc)

    if not parts:
        return None

    body = "\n".join(parts)
    body = _truncate_text(body, 6500)
    return (
        "\n\n---\nResearch notes (verify externally; snippets are incomplete and may be wrong):\n"
        f"{body}\n---"
    )


class PitchDeck:
    """Service to generate a pitch deck outline using a prompt template."""

    def __init__(self, model, *args, **kwargs):
        logger.info("[PitchDeck] Initializing PitchDeck service")
        self._model = model
        self._content = None
        self._sections = {}
        self._summary = None
        self._prompt_template = self._load_prompt_template()
        logger.info("[PitchDeck] Successfully initialized PitchDeck service")

    def _load_prompt_template(self):
        logger.info("[PitchDeck] Loading prompt template from file")
        template_path = prompt_path("pitch_deck.mcp.json")
        try:
            with open(template_path) as f:
                data = json.load(f)
                logger.debug(
                    f"[PitchDeck] Successfully loaded prompt template from {template_path}"
                )
                return data["prompt"]
        except Exception as e:
            logger.error(f"[PitchDeck] Failed to load prompt template: {str(e)}")
            default_prompt = {
                "system": "You are an experienced startup operator and investor preparing a polished seed-stage pitch deck in Markdown.",
                "user": "Given this idea: {idea_description}, generate a professional 12-slide pitch deck with clear slide headings, concise narrative, and investor-ready bullets.",
            }
            logger.warning("[PitchDeck] Using default prompt template")
            return default_prompt

    def update(self):
        """Update a pitch deck outline using the AI layer and prompt template."""
        logger.info("[PitchDeck] Starting pitch deck update")
        try:
            if hasattr(self._model, "idea"):
                description = self._model.idea.description
                if description:
                    logger.info(
                        f"[PitchDeck] Regenerating pitch deck with current idea description (length: {len(description)})"
                    )
                    logger.debug(f"[PitchDeck] Idea description preview: {description[:100]}...")
                    self.generate()
                else:
                    logger.warning("[PitchDeck] No idea description available for update")
            else:
                logger.warning("[PitchDeck] No idea component available for update")
        except Exception as e:
            logger.error(f"[PitchDeck] Error updating pitch deck: {str(e)}")
            raise

    def generate(self):
        logger.info("[PitchDeck] Starting pitch deck generation")
        try:
            if hasattr(self._model, "idea") and hasattr(self._model, "ai_layer"):
                description = self._model.idea.description
                logger.info(
                    f"[PitchDeck] Using idea description for generation (length: {len(description)})"
                )
                logger.debug(f"[PitchDeck] Idea description preview: {description[:100]}...")

                # Load prompt template
                template_path = prompt_path("pitch_deck.mcp.json")
                with open(template_path, encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("[PitchDeck] Successfully loaded pitch deck prompt template")

                # Format and send prompt
                system_prompt = data["prompt"]["system"]
                user_prompt = data["prompt"]["user"].replace("{{idea_description}}", description)
                research_notes = _gather_pitch_deck_research(self._model.ai_layer, description)
                if research_notes:
                    user_prompt = f"{user_prompt}{research_notes}"
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                logger.info("[PitchDeck] Sending formatted prompt to AI layer")
                logger.debug(f"[PitchDeck] System prompt: {system_prompt[:100]}...")
                logger.debug(f"[PitchDeck] User prompt: {user_prompt[:100]}...")

                # Use rich text generation
                pitch_deck = self._model.ai_layer.generate_rich_text(
                    messages, format_type="markdown"
                )
                logger.info(
                    f"[PitchDeck] Successfully received pitch deck content (length: {len(pitch_deck)})"
                )
                logger.debug(f"[PitchDeck] Content preview: {pitch_deck[:100]}...")

                self.summary = pitch_deck
                logger.info("[PitchDeck] Successfully stored pitch deck content")
                return pitch_deck
            else:
                logger.error("[PitchDeck] Missing required model components (idea or ai_layer)")
                raise AttributeError(
                    "ManifestManager is missing Idea or AILayer for pitch deck generation"
                )
        except Exception as e:
            logger.error(f"[PitchDeck] Error generating pitch deck: {str(e)}")
            raise

    @property
    def summary(self):
        """Get the full Pitch Deck summary as generated by the AI."""
        logger.debug("[PitchDeck] Accessing pitch deck summary")
        return self._summary

    @summary.setter
    def summary(self, value):
        """Set the full Pitch Deck summary as returned by the AI."""
        logger.info(
            f"[PitchDeck] Setting pitch deck summary (length: {len(value) if value else 0})"
        )
        self._summary = value

    @property
    def value(self):
        logger.debug("[PitchDeck] Accessing pitch deck value")
        return self._content

    @property
    def sections(self):
        logger.debug("[PitchDeck] Accessing pitch deck sections")
        return self._sections
