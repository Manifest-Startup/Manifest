import json
import os

from app.utils.logger import logger


class ProductRequirementsDocument:
    def __init__(self, manifest_manager):
        """
        Initialize the Product Requirements Document service.

        Parameters:
        - manifest_manager: The manifest manager instance that owns this service
        """
        logger.info("[PRD] Initializing ProductRequirementsDocument service")
        self.manifest_manager = manifest_manager
        self._summary = None
        logger.info("[PRD] Successfully initialized ProductRequirementsDocument service")

    def generate(self):
        """
        Generate a product requirements document using the AI layer.
        """
        logger.info("[PRD] Starting product requirements document generation")
        try:
            # Get the idea description from the manifest manager
            idea_description = self.manifest_manager.idea.description
            logger.info(f"[PRD] Using idea description (length: {len(idea_description)})")
            logger.debug(f"[PRD] Idea description preview: {idea_description[:100]}...")

            # Load the MCP file
            mcp_path = os.path.join(
                os.path.dirname(__file__), "../prompts/product_requirements_document.mcp.json"
            )
            logger.info(f"[PRD] Loading MCP file from {mcp_path}")
            with open(mcp_path) as f:
                mcp = json.load(f)
            logger.info("[PRD] Successfully loaded MCP file")

            # Prepare the messages for the AI
            messages = [
                {"role": "system", "content": mcp["prompt"]["system"]},
                {
                    "role": "user",
                    "content": mcp["prompt"]["user"].replace(
                        "{{idea_description}}", idea_description
                    ),
                },
            ]
            logger.info("[PRD] Prepared messages for AI layer")
            logger.debug(f"[PRD] System prompt: {mcp['prompt']['system'][:100]}...")
            logger.debug(f"[PRD] User prompt: {mcp['prompt']['user'][:100]}...")

            # Generate the PRD using the AI layer
            logger.info("[PRD] Sending request to AI layer")
            response = self.manifest_manager.ai_layer.generate_rich_text(
                messages, format_type="markdown"
            )
            logger.info(f"[PRD] Received response from AI layer (length: {len(response)})")
            logger.debug(f"[PRD] Raw AI response preview: {response[:100]}...")

            # Store the markdown response directly
            self._summary = response
            logger.info("[PRD] Successfully stored PRD content")
            return self._summary

        except Exception as e:
            logger.error(f"[PRD] Error generating product requirements document: {str(e)}")
            raise

    @property
    def summary(self):
        """
        Get the current product requirements document summary.
        """
        logger.debug("[PRD] Accessing PRD summary")
        return self._summary

    def update(self):
        """
        Update the product requirements document.
        """
        logger.info("[PRD] Starting PRD update")
        return self.generate()

    def set_parties_involved(self, parties):
        logger.info("[PRD] Setting parties involved")
        logger.debug(f"[PRD] Parties: {json.dumps(parties, indent=2)}")

    def set_terms_and_conditions(self, terms):
        logger.info("[PRD] Setting terms and conditions")
        logger.debug(f"[PRD] Terms: {json.dumps(terms, indent=2)}")

    def display_document(self):
        logger.info("[PRD] Displaying document")
