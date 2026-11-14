from typing import Any

from app.utils.logger import logger
from app.utils.logging_mixin import LoggingMixin


def component_properties(component_name: str, item_name: str = "item"):
    """
    Decorator that automatically adds standard properties and methods to component classes.

    Args:
        component_name: The name of the component for logging (e.g., "CustomerSegments")
        item_name: The name of individual items for the add method (e.g., "segment", "activity")
    """

    def decorator(cls):
        # Add the add_item method
        def add_item(self, item):
            """Add a new item to the list."""
            self._value.append(item)
            logger.info(f"Added {item_name}: {item}")

        # Add the value property
        def get_value(self):
            """Return the current list of items."""
            logger.debug(f"Accessing {component_name.lower()} value.")
            return self._value

        def set_value(self, items):
            """Update the items list."""
            logger.info(f"Updating {component_name.lower()}.")
            self._value = items

        # Add the summary property
        def get_summary(self):
            """Get the summary for the component."""
            logger.debug(f"Accessing {component_name.lower()} summary.")
            return self._summary

        def set_summary(self, value):
            """Set the summary for the component."""
            logger.info(f"Setting {component_name.lower()} summary.")
            self._summary = value

        # Add methods to the class
        setattr(cls, f"add_{item_name}", add_item)
        cls.value = property(get_value, set_value)
        cls.summary = property(get_summary, set_summary)

        return cls

    return decorator


class BaseComponent(LoggingMixin):
    """
    Base class for all component models (e.g., CostStructure, IntellectualProperty, etc.).
    Provides shared methods like update, show, and reusable summary/value properties.
    """

    def __init__(self, value: list[Any] | None = None):
        """
        Initialize the base component with an optional list value and summary.
        """
        self._value = value if value is not None else []
        self._summary = None
        self.log.debug(f"{self.__class__.__name__} initialized with value: {self._value}")

    @property
    def value(self):
        self.log.debug("Accessing value.")
        return self._value

    @value.setter
    def value(self, v):
        self.log.info("Updating value.")
        self._value = v

    @property
    def summary(self):
        self.log.debug("Accessing summary.")
        return self._summary

    @summary.setter
    def summary(self, value):
        self.log.info("Setting summary.")
        self._summary = value

    def update(self):
        if hasattr(self, "idea_description") and self.idea_description:
            self.log.info("Updating with existing idea.")
            self._generate()  # Calls subclass-implemented method
        else:
            self.log.debug("No idea description found.")

    def show(self):
        self.log.info(f"Value: {self._value}")

    def _generate(self):
        raise NotImplementedError(f"{self.__class__.__name__} must implement the _generate method.")
