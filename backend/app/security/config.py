import os
from collections.abc import Iterable

# setup_project.py used to create .env with this value; it must not disable demo mode
_PLACEHOLDER_DATABASE_URLS = frozenset(
    {
        "your_database_url_here",
    }
)

from app.utils.logger import logger
from fastapi import Request

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default


def runtime_environment() -> str:
    for key in ("APP_ENV", "ENVIRONMENT", "PYTHON_ENV", "NODE_ENV"):
        value = (os.getenv(key, "") or "").strip().lower()
        if value:
            return value
    return "development"


def is_test_environment() -> bool:
    return runtime_environment() == "test" or bool(os.getenv("PYTEST_CURRENT_TEST"))


def is_production_environment() -> bool:
    env = runtime_environment()
    return env in {"prod", "production", "staging"}


def configured_database_url() -> str | None:
    """Return a real PostgreSQL URL, or None if unset, empty, or a known template placeholder.

    If .env was generated from a template, DATABASE_URL=your_database_url_here must be treated
    the same as unset so local demo (in-memory) mode works.
    """
    raw = (os.getenv("DATABASE_URL") or "").strip()
    if not raw or raw in _PLACEHOLDER_DATABASE_URLS:
        return None
    return raw


def session_secret() -> str:
    secret = (os.getenv("SESSION_SECRET") or "").strip()
    if secret:
        return secret
    if is_production_environment():
        raise RuntimeError("SESSION_SECRET must be configured in production-like environments.")
    logger.warning(
        "[security_config] SESSION_SECRET is not set; using a development-only fallback. "
        "Set SESSION_SECRET before exposing this service publicly."
    )
    return "dev-session-secret-INSECURE"


def demo_mode_enabled() -> bool:
    raw = (os.getenv("DEMO_MODE") or "").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    if is_production_environment():
        return False
    return configured_database_url() is None


def request_is_secure(request: Request | None) -> bool:
    if request is None:
        return False
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if forwarded_proto:
        return forwarded_proto == "https"
    return request.url.scheme == "https"


def secure_cookies_enabled(request: Request | None = None) -> bool:
    if env_flag("FORCE_SECURE_COOKIES", default=False):
        return True
    if is_test_environment():
        return False
    if request_is_secure(request):
        return True
    return is_production_environment()


def _hostname_from_url(raw: str) -> str | None:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(raw.strip())
        return parsed.hostname
    except Exception:
        return None


def _add_host_value(hosts: set[str], value: str) -> None:
    cleaned = value.strip()
    if not cleaned:
        return
    if cleaned.startswith("http"):
        hostname = _hostname_from_url(cleaned)
        cleaned = hostname or cleaned
    if cleaned:
        hosts.add(cleaned)


def trusted_hosts() -> list[str]:
    hosts = {
        "localhost",
        "127.0.0.1",
        "manifeststartup.com",
        "www.manifeststartup.com",
    }
    for env_key in ("APP_BASE_URL", "REACT_APP_GRAPHQL_URL"):
        hostname = _hostname_from_url(os.getenv(env_key) or "")
        if hostname:
            hosts.add(hostname)
    for env_key in ("REPLIT_DEV_DOMAIN", "REPLIT_DOMAINS", "ALLOWED_HOSTS"):
        raw = (os.getenv(env_key) or "").strip()
        if not raw:
            continue
        for value in raw.split(","):
            _add_host_value(hosts, value)
    for origin in frontend_origins_from_env():
        hostname = _hostname_from_url(origin)
        if hostname:
            hosts.add(hostname)
    return sorted(hosts)


def merge_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        out.append(cleaned)
        seen.add(cleaned)
    return out


def _origin_from_env_value(value: str) -> str | None:
    """Normalize a FRONTEND_ORIGINS entry to a full origin URL for CORS."""
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned.rstrip("/")
    return f"https://{cleaned.rstrip('/')}"


def frontend_origins_from_env() -> list[str]:
    """Comma-separated frontend origins (Vercel preview/prod). Used for CORS + trusted hosts."""
    raw = (os.getenv("FRONTEND_ORIGINS") or "").strip()
    if not raw:
        return []
    origins: list[str] = []
    for part in raw.split(","):
        origin = _origin_from_env_value(part)
        if origin:
            origins.append(origin)
    return merge_unique(origins)
