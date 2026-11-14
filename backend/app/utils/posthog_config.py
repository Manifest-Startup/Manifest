import os

import posthog
from dotenv import load_dotenv

load_dotenv()

_POSTHOG_API_KEY = os.getenv("POSTHOG_API_KEY") or os.getenv("REACT_APP_PUBLIC_POSTHOG_KEY")
_POSTHOG_HOST = (
    os.getenv("POSTHOG_HOST")
    or os.getenv("REACT_APP_PUBLIC_POSTHOG_HOST")
    or "https://app.posthog.com"
)
_POSTHOG_ENABLED = bool(_POSTHOG_API_KEY)

if _POSTHOG_ENABLED:
    posthog.api_key = _POSTHOG_API_KEY
    posthog.host = _POSTHOG_HOST


def capture_event(distinct_id, event_name, properties=None):
    """
    Capture an event in PostHog

    Args:
        distinct_id (str): The unique identifier for the user
        event_name (str): The name of the event
        properties (dict, optional): Additional properties to include with the event
    """
    if not _POSTHOG_ENABLED or not distinct_id or not event_name:
        return False
    try:
        posthog.capture(distinct_id=distinct_id, event=event_name, properties=properties or {})
        return True
    except Exception as e:
        print(f"Error capturing PostHog event: {e}")
        return False
