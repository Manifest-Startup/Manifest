from app.services.canvas.section_base import BaseComponent, component_properties
from app.utils.logger import logger


# Channels Class
@component_properties("Channels", "channel")
class Channels(BaseComponent):
    def __init__(self, channels=None):
        super().__init__(channels)
        logger.info("Channels initialized.")
