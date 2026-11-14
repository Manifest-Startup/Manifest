from app.services.canvas.section_base import BaseComponent, component_properties
from app.utils.logger import logger


# Customer Relationships Class
@component_properties("CustomerRelationships", "relationship")
class CustomerRelationships(BaseComponent):
    def __init__(self, relationships=None):
        """
        Initialize the CustomerRelationships with a list of relationships.
        """
        super().__init__(relationships)
        logger.info("CustomerRelationships initialized.")
