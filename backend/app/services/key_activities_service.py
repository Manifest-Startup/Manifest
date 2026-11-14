from app.services.base_component import BaseComponent, component_properties
from app.utils.logger import logger


# Key Activities Class
@component_properties("KeyActivities", "activity")
class KeyActivities(BaseComponent):
    def __init__(self, activities=None):
        """
        Initialize KeyActivities with an optional list of activities.
        """
        super().__init__(activities)
        logger.info("KeyActivities initialized.")
