import logging
from app.utils.logger import log_exception

def test_log_exception(caplog):
    """
    Test that log_exception correctly logs an error with exception info.
    """
    try:
        # Raise an exception to be caught and logged
        raise ValueError("This is a test exception")
    except ValueError:
        # Use caplog to capture the log output
        with caplog.at_level(logging.ERROR, logger="manifest"):
            log_exception("An exception occurred")
            
    # Assert that one log record was created
    assert len(caplog.records) == 1
    # Assert that the log message is correct
    assert "An exception occurred" in caplog.text
    # Assert that the log record has exception info
    record = caplog.records[0]
    assert record.exc_info is not None
    assert "ValueError: This is a test exception" in caplog.text

def test_logger_initialization(caplog):
    """
    Test that the logger is initialized correctly and handlers are not duplicated.
    """
    # The logger is already initialized when the module is imported.
    # We can check its properties.
    import logging
    import importlib
    from app.utils import logger as logger_module

    # Capture logs to verify handler is working
    with caplog.at_level(logging.INFO, logger="manifest"):
        logging.getLogger("manifest").info("Initial log message.")
    
    assert "Initial log message." in caplog.text
    initial_handler_count = len(logging.getLogger("manifest").handlers)

    # Reloading the module will execute the setup code again.
    importlib.reload(logger_module)

    logger = logging.getLogger("manifest")
    # The number of handlers should not increase after reload.
    assert len(logger.handlers) == initial_handler_count, "Handlers should not be duplicated on re-import"

    # Verify logging still works as expected after reload
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="manifest"):
        logger.info("Log message after reload.")
    assert "Log message after reload." in caplog.text 
