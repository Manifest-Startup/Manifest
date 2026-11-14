"""Keep personal data out of logs."""


def mask(value: object, visible: int = 4) -> str:
    """Show only the last ``visible`` characters: ``mask("123-45-6789") == "*******6789"``."""
    text = "" if value is None else str(value)
    if len(text) <= visible:
        return "*" * len(text)
    return "*" * (len(text) - visible) + text[-visible:]
