"""HTTP client for the Open Media API (``docs/OPEN_MEDIA_CONTRACT.md``).

- Short timeouts (10 s; 120 s for video uploads).
- Retries with backoff on connection failures (always safe: nothing was sent)
  and on 429/502/503/504 for idempotent requests (GET, PUT, DELETE, or a POST
  that carries an idempotency key).
- ``connected(user_id, ...)`` calls ``/v1/connected/me/*`` as that user. It
  refreshes the access token one minute before expiry, or once after a 401,
  under a per-user lock so a rotated refresh token is never used twice.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from app.services.integrations.open_media import settings, store
from app.utils.logger import logger

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
UPLOAD_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
RETRY_STATUSES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
_SAFE_METHODS = {"GET", "HEAD", "PUT", "DELETE"}
_REFRESH_MARGIN = timedelta(seconds=60)

UNAVAILABLE_MESSAGE = "Open Media is unavailable right now. Try again in a moment."
NOT_LINKED_MESSAGE = "Connect your Open Media account in Account settings to use this."
RECONNECT_MESSAGE = "Your Open Media connection expired. Reconnect it in Account settings."
DISABLED_MESSAGE = "Messages and Pitch Shorts are not available on this server."


class OpenMediaError(Exception):
    """An Open Media request failed. ``str(exc)`` is safe to show to the user."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class OpenMediaUnavailable(OpenMediaError):
    """Network trouble or a 5xx after retries."""


class OpenMediaNotLinked(OpenMediaError):
    """The Manifest user has no usable Open Media link."""

    def __init__(self, *, reconnect: bool = False) -> None:
        super().__init__(
            RECONNECT_MESSAGE if reconnect else NOT_LINKED_MESSAGE,
            status=401,
            code="reconnect_open_media" if reconnect else "open_media_not_linked",
        )
        self.reconnect = reconnect


class OpenMediaDisabled(OpenMediaError):
    def __init__(self) -> None:
        super().__init__(DISABLED_MESSAGE, code="open_media_disabled")


def require_enabled() -> None:
    if not settings.enabled():
        raise OpenMediaDisabled()


def pick(record: Any, *names: str, default: Any = None) -> Any:
    """First present key. The contract uses snake_case; current Open Media RPCs return
    camelCase (``createdAt``, ``displayName``), so readers accept both."""
    if not isinstance(record, dict):
        return default
    for name in names:
        value = record.get(name)
        if value is not None:
            return value
    return default


def person(record: Any) -> dict[str, Any]:
    """Normalise an Open Media profile (``{id, handle, display_name, avatar_url}``)."""
    record = record if isinstance(record, dict) else {}
    handle = str(pick(record, "handle", default="") or "")
    return {
        "id": str(pick(record, "id", "user_id", "userId", default="") or ""),
        "handle": handle,
        "display_name": str(pick(record, "display_name", "displayName", default="") or handle),
        "avatar_url": pick(record, "avatar_url", "avatarUrl"),
    }


def _error_from_response(response: httpx.Response) -> OpenMediaError:
    code = None
    description = None
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):  # public /v1/posts and /v1/feed: {error: {code, message}}
                code = error.get("code")
                description = error.get("message")
            else:  # /v1/connected and /token: {error, error_description}
                code = error
                description = body.get("error_description") or body.get("message")
    except ValueError:
        pass
    if response.status_code >= 500:
        return OpenMediaUnavailable(UNAVAILABLE_MESSAGE, status=response.status_code, code=code)
    message = str(description or code or f"Open Media request failed ({response.status_code}).")
    return OpenMediaError(message[:300], status=response.status_code, code=code)


class OpenMediaClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._http_client: httpx.Client | None = None
        self._http_base: str | None = None
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # -- plumbing ---------------------------------------------------------

    def _http(self) -> httpx.Client:
        base = settings.api_base()
        if self._http_client is None or self._http_base != base:
            self._http_client = httpx.Client(
                base_url=base,
                timeout=DEFAULT_TIMEOUT,
                transport=self._transport,
                headers={"User-Agent": "Manifest/1 (+https://manifeststartup.com)"},
            )
            self._http_base = base
        return self._http_client

    def _lock_for(self, user_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(str(user_id), threading.Lock())

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json: Any = None,
        data: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        timeout: httpx.Timeout | None = None,
        idempotent: bool | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        safe = idempotent if idempotent is not None else method in _SAFE_METHODS
        all_headers = dict(headers or {})
        all_headers.setdefault("Accept", "application/json")
        if token:
            all_headers["Authorization"] = f"Bearer {token}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http().request(
                    method,
                    path,
                    json=json,
                    data=data,
                    content=content,
                    headers=all_headers,
                    params=clean_params or None,
                    timeout=timeout or DEFAULT_TIMEOUT,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                retry = attempt < MAX_ATTEMPTS
                self._log_retry(method, path, attempt, type(exc).__name__, retry)
                if retry:
                    self._backoff(attempt, None)
                    continue
                raise OpenMediaUnavailable(UNAVAILABLE_MESSAGE) from None
            except httpx.TransportError as exc:
                retry = safe and attempt < MAX_ATTEMPTS
                self._log_retry(method, path, attempt, type(exc).__name__, retry)
                if retry:
                    self._backoff(attempt, None)
                    continue
                raise OpenMediaUnavailable(UNAVAILABLE_MESSAGE) from None

            if response.status_code in RETRY_STATUSES and safe and attempt < MAX_ATTEMPTS:
                self._log_retry(method, path, attempt, str(response.status_code), True)
                self._backoff(attempt, response.headers.get("retry-after"))
                continue
            if response.status_code >= 400:
                raise _error_from_response(response)
            if not response.content:
                return {}
            try:
                body = response.json()
            except ValueError:
                return {}
            return body if isinstance(body, dict) else {"data": body}
        raise OpenMediaUnavailable(UNAVAILABLE_MESSAGE)  # pragma: no cover - loop always returns

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = 0.3 * (2 ** (attempt - 1))
        if retry_after:
            try:
                delay = min(2.0, max(delay, float(retry_after)))
            except ValueError:
                pass
        self._sleep(delay)

    @staticmethod
    def _log_retry(method: str, path: str, attempt: int, reason: str, retry: bool) -> None:
        logger.warning(
            "[open_media] %s %s attempt %d failed (%s)%s",
            method,
            path.split("?")[0],
            attempt,
            reason,
            "; retrying" if retry else "",
        )

    # -- OAuth token endpoint -------------------------------------------

    def token(self, form: dict[str, str]) -> dict[str, Any]:
        """``POST /token`` (authorization_code or refresh_token grant)."""
        return self.request(
            "POST",
            "/token",
            data={**form, "client_id": settings.client_id()},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            idempotent=False,
        )

    # -- calls made as a linked Manifest user ----------------------------

    def access_token(self, user_id: str, *, stale_token: str | None = None) -> str:
        """A valid access token for ``user_id``, refreshing it when needed."""
        with self._lock_for(user_id):
            link = store.load_link(user_id)
            if link is None:
                raise OpenMediaNotLinked()
            if link.needs_reconnect or not link.refresh_token:
                raise OpenMediaNotLinked(reconnect=True)
            fresh = (
                link.access_token
                and link.expires_at is not None
                and link.expires_at - _REFRESH_MARGIN > datetime.now(UTC)
            )
            if fresh and link.access_token != stale_token:
                return str(link.access_token)
            try:
                tokens = self.token(
                    {"grant_type": "refresh_token", "refresh_token": link.refresh_token}
                )
            except OpenMediaUnavailable:
                raise
            except OpenMediaError as exc:
                if exc.status in (400, 401, 403):
                    logger.info("[open_media] refresh rejected; user must reconnect")
                    store.mark_needs_reconnect(user_id)
                    raise OpenMediaNotLinked(reconnect=True) from None
                raise
            access = str(tokens.get("access_token") or "")
            if not access:
                raise OpenMediaUnavailable(UNAVAILABLE_MESSAGE)
            store.update_tokens(
                user_id,
                access_token=access,
                refresh_token=tokens.get("refresh_token"),
                expires_in=tokens.get("expires_in"),
            )
            return access

    def connected(self, user_id: str, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Call ``/v1/connected/me<path>`` as ``user_id`` (``path`` starts with ``/``)."""
        require_enabled()
        full_path = f"/v1/connected/me{path}"
        token = self.access_token(user_id)
        try:
            return self.request(method, full_path, token=token, **kwargs)
        except OpenMediaError as exc:
            if exc.status != 401 or isinstance(exc, OpenMediaNotLinked):
                raise
        token = self.access_token(user_id, stale_token=token)
        try:
            return self.request(method, full_path, token=token, **kwargs)
        except OpenMediaError as exc:
            if exc.status == 401 and not isinstance(exc, OpenMediaNotLinked):
                raise OpenMediaNotLinked(reconnect=True) from None
            raise

    def public(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Unauthenticated read (``/v1/posts``, ``/v1/feed``)."""
        require_enabled()
        return self.request("GET", path, params=params)


_client: OpenMediaClient | None = None
_client_guard = threading.Lock()


def get_client() -> OpenMediaClient:
    global _client
    with _client_guard:
        if _client is None:
            _client = OpenMediaClient()
        return _client


def set_client(client: OpenMediaClient | None) -> None:
    """Swap the process client (tests use an ``httpx.MockTransport``)."""
    global _client
    with _client_guard:
        _client = client
