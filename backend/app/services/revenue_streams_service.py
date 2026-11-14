from app.services.base_component import BaseComponent, component_properties
from app.utils.logger import logger


@component_properties("RevenueStreams", "stream")
class RevenueStreams(BaseComponent):
    def __init__(self, streams=None):
        """
        Initialize RevenueStreams with an optional list of revenue streams.
        """
        super().__init__(streams)
        logger.info("RevenueStreams initialized.")
