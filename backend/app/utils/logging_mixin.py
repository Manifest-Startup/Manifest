from app.utils.logger import logger


class LoggingMixin:
    """Simple mixin that exposes a per-class `self.log` child logger.

    Usage::
        class MyService(LoggingMixin):
            def do_something(self):
                self.log.info("Hello")

    Creating child loggers keeps the existing formatting/handlers of the root
    ``manifest`` logger while giving helpful component-level names such as
    ``manifest.backend.app.services.MyService``.
    """

    @property
    def log(self):
        # The `logger` defined in app.utils.logger is the root "manifest" logger.
        # ``getChild`` creates (and caches) a hierarchical child logger whose
        # name is "manifest.<ClassName>".  This avoids constructing a new
        # logger each time and keeps configuration DRY.
        return logger.getChild(self.__class__.__name__)
