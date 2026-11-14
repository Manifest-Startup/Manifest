from app.services.base_component import BaseComponent, component_properties
from app.utils.logger import logger


# Customer Segments Class
@component_properties("CustomerSegments", "segment")
class CustomerSegments(BaseComponent):
    def __init__(self, segments=None):
        """
        Initialize the CustomerSegments with a list of customer segments.
        """
        super().__init__(segments)
        logger.info("CustomerSegments initialized.")  # Log the initialization of the class
