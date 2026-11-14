from app.services.canvas.section_base import BaseComponent, component_properties
from app.utils.logger import logger


# Key Partners Class
@component_properties("KeyPartners", "partner")
class KeyPartners(BaseComponent):
    def __init__(self, partners=None):
        """
        Initialize KeyPartners with an optional list of partner entities.
        """
        super().__init__(partners)
        logger.info("KeyPartners initialized.")
