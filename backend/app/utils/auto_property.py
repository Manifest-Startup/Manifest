"""Shared descriptor that exposes ``_<name>`` private attributes as plain properties."""

from typing import Any


class AutoProperty:
    """Descriptor that gets and sets the private attribute ``_<attr_name>``.

    ``business_name = AutoProperty("business_name")`` reads and writes
    ``self._business_name``.
    """

    def __init__(self, attr_name: str) -> None:
        self.attr_name = attr_name

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        return getattr(obj, f"_{self.attr_name}")

    def __set__(self, obj: Any, value: Any) -> None:
        setattr(obj, f"_{self.attr_name}", value)
