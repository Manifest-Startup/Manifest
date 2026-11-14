from app.services.canvas.section_base import BaseComponent, component_properties
from app.utils.logger import logger


# Key Resources Class
@component_properties("KeyResources", "resource")
class KeyResources(BaseComponent):
    def __init__(self, resources=None):
        """
        Initialize KeyResources with an optional list of key resources.
        """
        super().__init__(resources)
        logger.info("KeyResources initialized.")
