import json

from app.prompts import prompt_path
from app.utils.logger import logger


class ProvisionalPatent:
    """Service to generate a provisional patent draft using a prompt template."""

    def __init__(self, model, *args, **kwargs):
        logger.info("[ProvisionalPatent] Initializing ProvisionalPatent service")
        self._model = model
        self._content = None
        self._summary = None
        self._sections = {}
        self._prompt_template = self._load_prompt_template()
        logger.info("[ProvisionalPatent] Successfully initialized ProvisionalPatent service")

    def _load_prompt_template(self):
        logger.info("[ProvisionalPatent] Loading prompt template from file")
        template_path = prompt_path("provisional_patent.mcp.json")
        try:
            with open(template_path) as f:
                data = json.load(f)
                logger.debug(
                    f"[ProvisionalPatent] Successfully loaded prompt template from {template_path}"
                )
                return data["prompt"]
        except Exception as e:
            logger.error(f"[ProvisionalPatent] Failed to load prompt template: {str(e)}")
            default_prompt = {
                "system": "You are a US patent drafting assistant preparing a professional provisional patent draft in Markdown.",
                "user": "Given this idea: {idea_description}, generate a professional provisional patent draft with formal filing sections and attorney-review placeholders.",
            }
            logger.warning("[ProvisionalPatent] Using default prompt template")
            return default_prompt

    def update(self):
        """Update a provisional patent draft using the AI layer and prompt template."""
        logger.info("[ProvisionalPatent] Starting provisional patent update")
        try:
            if hasattr(self._model, "idea"):
                description = self._model.idea.description
                if description:
                    logger.info(
                        f"[ProvisionalPatent] Regenerating provisional patent with current idea description (length: {len(description)})"
                    )
                    logger.debug(
                        f"[ProvisionalPatent] Idea description preview: {description[:100]}..."
                    )
                    self.generate()
                else:
                    logger.warning("[ProvisionalPatent] No idea description available for update")
            else:
                logger.warning("[ProvisionalPatent] No idea component available for update")
        except Exception as e:
            logger.error(f"[ProvisionalPatent] Error updating provisional patent: {str(e)}")
            raise

    def generate(self):
        logger.info("[ProvisionalPatent] Starting provisional patent generation")
        try:
            if hasattr(self._model, "idea") and hasattr(self._model, "ai_layer"):
                description = self._model.idea.description
                logger.info(
                    f"[ProvisionalPatent] Using idea description for generation (length: {len(description)})"
                )
                logger.debug(
                    f"[ProvisionalPatent] Idea description preview: {description[:100]}..."
                )

                # Load prompt template
                template_path = prompt_path("provisional_patent.mcp.json")
                with open(template_path, encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(
                    "[ProvisionalPatent] Successfully loaded provisional patent prompt template"
                )

                # Format and send prompt
                system_prompt = data["prompt"]["system"]
                user_prompt = data["prompt"]["user"].replace("{{idea_description}}", description)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                logger.info("[ProvisionalPatent] Sending formatted prompt to AI layer")
                logger.debug(f"[ProvisionalPatent] System prompt: {system_prompt[:100]}...")
                logger.debug(f"[ProvisionalPatent] User prompt: {user_prompt[:100]}...")

                # Use rich text generation
                patent_draft = self._model.ai_layer.generate_rich_text(
                    messages, format_type="markdown"
                )
                logger.info(
                    f"[ProvisionalPatent] Successfully received patent draft content (length: {len(patent_draft)})"
                )
                logger.debug(f"[ProvisionalPatent] Content preview: {patent_draft[:100]}...")

                self.summary = patent_draft
                logger.info("[ProvisionalPatent] Successfully stored patent draft content")
                return patent_draft
            else:
                logger.error(
                    "[ProvisionalPatent] Missing required model components (idea or ai_layer)"
                )
                raise AttributeError(
                    "ManifestManager is missing Idea or AILayer for provisional patent generation"
                )
        except Exception as e:
            logger.error(f"[ProvisionalPatent] Error generating provisional patent: {str(e)}")
            raise

    @property
    def summary(self):
        """Get the full provisional patent draft as generated by the AI."""
        logger.debug("[ProvisionalPatent] Accessing provisional patent summary")
        return self._summary

    @summary.setter
    def summary(self, value):
        """Set the full provisional patent draft as returned by the AI."""
        logger.info(
            f"[ProvisionalPatent] Setting provisional patent summary (length: {len(value) if value else 0})"
        )
        self._summary = value

    @property
    def value(self):
        logger.debug("[ProvisionalPatent] Accessing provisional patent value")
        return self._content

    @property
    def sections(self):
        logger.debug("[ProvisionalPatent] Accessing provisional patent sections")
        return self._sections
