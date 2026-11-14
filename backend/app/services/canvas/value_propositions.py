from app.services.canvas.section_base import BaseComponent, component_properties
from app.utils.logger import logger


# Class for handling Value Propositions
@component_properties("ValuePropositions", "proposition")
class ValuePropositions(BaseComponent):
    def __init__(self, propositions=None):
        """
        Initialize ValuePropositions with an optional list of propositions.
        """
        super().__init__(propositions)
        logger.info("ValuePropositions initialized.")
