"""
AILayer Service - Unified AI text generation layer using AIRouter.
Provides rich text generation, summaries, and structured responses.
"""

import os

from app.services.ai_credentials import MissingOpenAIKeyError
from app.services.ai_router import AIRouter
from app.utils.logger import logger


class AILayer:
    """AI Layer for text generation using AIRouter."""

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model=None, max_retries=3):
        """Initialize AILayer with AIRouter backend."""
        self.model = os.getenv("AI_MODEL", model or self.DEFAULT_MODEL)
        self.max_retries = max_retries

        logger.info(f"[AILayer] Initializing with model: {self.model}")

        self.router = AIRouter(model=self.model, max_retries=max_retries)

        if self.router.is_available():
            logger.info("[AILayer] Successfully initialized with AIRouter")
        else:
            logger.warning("[AILayer] AIRouter not configured. AI features disabled.")

    def is_available(self) -> bool:
        """Return whether AI-backed document generation can run."""
        return self.router.is_available()

    def generate_text(self, messages):
        """
        Generate rich text from a given list of role-based messages.
        Returns markdown-formatted rich text.
        """
        if not self.router.is_available():
            logger.warning("[AILayer] AIRouter not available.")
            raise Exception("AI API key is not configured. AI features are disabled.")

        logger.info(f"[AILayer] Starting text generation with {len(messages)} messages")

        try:
            content = self.router.chat(prompt=messages, model=self.model)
            logger.info(f"[AILayer] Response received (length: {len(content)})")
            return content
        except Exception as e:
            logger.error(f"[AILayer] Text generation failed: {e}")
            raise Exception(f"Failed to generate text: {e}") from e

    def generate_rich_text(self, messages, format_type="markdown"):
        """
        Generate formatted rich text with specific formatting instructions.

        Args:
            messages: List of role-based messages
            format_type: Type of formatting to request (markdown, html, etc.)

        Returns:
            str: Formatted rich text ready for TipTap editor
        """
        logger.info(f"[AILayer] Starting rich text generation with format_type: {format_type}")

        formatted_messages = messages.copy()
        formatting_instruction = f"\nPlease format your response in {format_type} with proper headings, lists, and emphasis where appropriate."

        if formatted_messages and formatted_messages[0]["role"] == "system":
            formatted_messages[0]["content"] += formatting_instruction
        else:
            formatted_messages.insert(
                0, {"role": "system", "content": formatting_instruction.strip()}
            )

        return self.generate_text(formatted_messages)

    def generate_summary(self, idea_description):
        """Generate a concise summary for a given idea description."""
        logger.info(f"[AILayer] Generating summary (length: {len(idea_description)})")

        prompt = f"""
        Summarize the following startup idea in 3-4 concise sentences suitable for a pitch:
        "{idea_description}"
        """

        content = self.generate_text([{"role": "user", "content": prompt}])
        logger.info(f"[AILayer] Summary generated (length: {len(content)})")
        return content

    def health_check(self):
        """Perform a health check to ensure AI is reachable."""
        try:
            logger.info("[AILayer] Starting health check...")
            return self.router.health_check()
        except Exception as e:
            logger.error(f"[AILayer] Health check failed: {e}")
            return False

    def perform_web_search(self, query):
        """
        Perform a web search using AIRouter with OpenAI search-preview models.
        """
        logger.info(f"[AILayer] Starting web search for query: {query}")

        if not self.router.is_available():
            logger.error("[AILayer] AIRouter not available for web search")
            raise MissingOpenAIKeyError()

        try:
            result = self.router.web_search(query)

            logger.info(f"[AILayer] Web search completed (length: {len(result['content'])})")

            return {"similar_ideas": result["content"], "sources": result.get("citations", [])}

        except Exception as e:
            logger.error(f"[AILayer] Web search failed: {e}")
            raise Exception(f"Web search failed: {e}") from e

    def perform_web_search_json(self, query, system_prompt=None):
        """
        Perform a grounded web search and request structured JSON output.
        """
        logger.info("[AILayer] Starting structured web search")

        if not self.router.is_available():
            logger.error("[AILayer] AIRouter not available for structured web search")
            raise MissingOpenAIKeyError()

        try:
            result = self.router.web_search_json(query, system_prompt=system_prompt)
            logger.info("[AILayer] Structured web search completed")
            return {
                "data": result["content"],
                "sources": result.get("citations", []),
                "source_details": result.get("citation_details", []),
            }
        except Exception as e:
            logger.error(f"[AILayer] Structured web search failed: {e}")
            raise Exception(f"Structured web search failed: {e}") from e

    def generate_structured_response(self, messages, expected_schema=None):
        """
        Generate a structured JSON response.

        Args:
            messages: List of role-based messages
            expected_schema: Optional JSON schema to validate against

        Returns:
            dict: Parsed and validated JSON response
        """
        logger.info("[AILayer] Starting structured response generation")

        try:
            parsed_response = self.router.chat_json(
                prompt=messages, model=self.model, temperature=0.3
            )

            logger.info("[AILayer] Successfully parsed JSON response")
            return parsed_response

        except Exception as e:
            logger.error(f"[AILayer] Structured response failed: {e}")
            raise Exception(f"Failed to generate structured response: {e}") from e
