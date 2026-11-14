"""SSRF-safe outbound HTTP helpers (SEC-008).

Every server-side outbound HTTP call SHOULD route through these helpers
so we get consistent protection against:

- Requests to RFC1918 / loopback / link-local / multicast / reserved IPs.
- Requests to cloud metadata services (169.254.169.254, fd00:ec2::254,
  100.100.100.200).
- ``file://`` / ``ftp://`` / ``gopher://`` and other non-HTTP schemes.
- Surprise redirects that escape the allowlist (we re-validate the
  ``Location`` of every hop).

Callers pass either an HTTPS hostname or, for one-off scripts, an
explicit ``allow_internal=True`` to opt out (e.g. integration tests
hitting localhost). Production code never sets that flag.

DNS-rebinding mitigation: ``assert_safe_url`` rejects *any* internal
address the hostname currently resolves to. To close the TOCTOU window
between our resolve and the underlying client's resolve, callers can
opt into ``pin_dns=True`` (default for ``safe_request`` and
``safe_async_request``). When enabled, we resolve once, pick the first
safe address, and pin the underlying connection to it via a custom
``urllib3`` adapter (sync) or ``httpx`` transport (async) — the original
hostname is still sent in the ``Host`` header / TLS SNI, so HTTPS
verification continues to work.
"""

from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
import threading
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.parse import urlparse

import httpx
import requests


class SSRFError(ValueError):
    """Raised when an outbound URL fails the SSRF safety check."""


# Cloud metadata IPs (AWS, GCP, Azure, Alibaba, OpenStack, Oracle).
_METADATA_IPS = frozenset(
    {
        "169.254.169.254",
        "100.100.100.200",
        "fd00:ec2::254",
    }
)

_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Default response/connect cap to avoid slow-loris from compromised hosts.
_DEFAULT_TIMEOUT = float(os.getenv("SAFE_HTTP_TIMEOUT_SECONDS", "20"))
_MAX_REDIRECTS = int(os.getenv("SAFE_HTTP_MAX_REDIRECTS", "3"))
_MAX_RESPONSE_BYTES = int(os.getenv("SAFE_HTTP_MAX_RESPONSE_BYTES", str(25 * 1024 * 1024)))


def _ip_is_disallowed(ip: ipaddress._BaseAddress) -> str | None:
    if str(ip) in _METADATA_IPS:
        return "cloud metadata IP"
    if ip.is_loopback:
        return "loopback IP"
    if ip.is_link_local:
        return "link-local IP"
    if ip.is_multicast:
        return "multicast IP"
    if ip.is_unspecified:
        return "unspecified IP"
    if ip.is_reserved:
        return "reserved IP"
    if ip.is_private:
        return "private IP"
    return None


def _resolve_addresses(hostname: str) -> Iterable[tuple[int, str]]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFError(f"DNS resolution failed for {hostname!r}: {exc}") from exc
    for family, _socktype, _proto, _canonname, sockaddr in infos:
        if family == socket.AF_INET or family == socket.AF_INET6:
            yield family, sockaddr[0]


_DNS_PIN_LOCK = threading.Lock()
_orig_getaddrinfo = socket.getaddrinfo


@contextlib.contextmanager
def _pin_hostname_to_ip(hostname: str, pinned_ip: str) -> Iterator[None]:
    """Process-globally pin ``hostname`` -> ``pinned_ip`` for the duration.

    Both ``requests`` (via ``urllib3``) and ``httpx`` (via ``httpcore``)
    ultimately call :func:`socket.getaddrinfo`. Replacing it inside a
    lock guarantees the connection is established to the IP we already
    validated, closing the DNS-rebinding TOCTOU window. The original
    hostname continues to be used for the ``Host`` header and TLS SNI,
    so HTTPS certificate validation remains intact.
    """
    family = socket.AF_INET6 if ":" in pinned_ip else socket.AF_INET

    def _patched(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host == hostname:
            sock_port = port if isinstance(port, int) else 0
            sockaddr: tuple[Any, ...] = (
                (pinned_ip, sock_port, 0, 0)
                if family == socket.AF_INET6
                else (pinned_ip, sock_port)
            )
            return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
        return _orig_getaddrinfo(host, port, *args, **kwargs)

    with _DNS_PIN_LOCK:
        socket.getaddrinfo = _patched  # type: ignore[assignment]
        try:
            yield
        finally:
            socket.getaddrinfo = _orig_getaddrinfo  # type: ignore[assignment]


def pick_safe_resolved_ip(hostname: str) -> str:
    """Resolve ``hostname`` and return the first IP that passes IP-safety checks.

    Raises :class:`SSRFError` if no resolved address is safe. Used to pin
    the outbound connection so a DNS rebinding race cannot redirect it to
    an internal address after our preflight.
    """
    last_reason = "no addresses resolved"
    for _family, addr in _resolve_addresses(hostname):
        try:
            ip_obj = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            continue
        reason = _ip_is_disallowed(ip_obj)
        if reason is None:
            return str(ip_obj)
        last_reason = reason
    raise SSRFError(f"No safe resolved address for {hostname!r}: {last_reason}")


def assert_safe_url(url: str, *, allow_internal: bool = False) -> str:
    """Validate ``url`` and return the normalized form, or raise SSRFError."""
    if not url or not isinstance(url, str):
        raise SSRFError("URL is required")
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(f"Disallowed URL scheme: {scheme or '(none)'}")
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        raise SSRFError("URL is missing a hostname")
    if "@" in (parsed.netloc or ""):
        raise SSRFError("URL must not embed credentials")

    if allow_internal:
        return url

    # Reject literal IPs that are unsafe even before DNS resolution.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        reason = _ip_is_disallowed(literal)
        if reason:
            raise SSRFError(f"Refusing to fetch {hostname}: {reason}")
        return url

    # Resolve and check every address the hostname maps to.
    for _family, addr in _resolve_addresses(hostname):
        try:
            ip_obj = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            continue
        reason = _ip_is_disallowed(ip_obj)
        if reason:
            raise SSRFError(f"Refusing to fetch {hostname}: resolved {addr} is a {reason}")
    return url


def _validate_with_redirect_chain(
    initial_url: str, history: Iterable[Any], allow_internal: bool
) -> None:
    for response in history:
        next_location = response.headers.get("Location") or response.headers.get("location")
        if not next_location:
            continue
        # httpx/requests resolve relative redirects on the response object
        target = str(getattr(response, "url", next_location) or next_location)
        assert_safe_url(target, allow_internal=allow_internal)


def _hostname_of(url: str) -> str:
    return (urlparse(url).hostname or "").strip()


def _maybe_pin(
    url: str, *, pin_dns: bool, allow_internal: bool
) -> contextlib.AbstractContextManager:
    """Return a context manager that pins DNS for ``url``'s hostname when enabled."""
    if not pin_dns or allow_internal:
        return contextlib.nullcontext()
    host = _hostname_of(url)
    if not host:
        return contextlib.nullcontext()
    # Skip pinning for literal IPs (no DNS lookup possible).
    try:
        ipaddress.ip_address(host)
        return contextlib.nullcontext()
    except ValueError:
        pass
    pinned_ip = pick_safe_resolved_ip(host)
    return _pin_hostname_to_ip(host, pinned_ip)


def safe_request(
    method: str,
    url: str,
    *,
    timeout: float | None = None,
    max_response_bytes: int | None = None,
    allow_internal: bool = False,
    pin_dns: bool = True,
    **kwargs: Any,
) -> requests.Response:
    """``requests``-backed safe HTTP call. Validates URL + every redirect.

    With ``pin_dns=True`` (default) the underlying TCP connection is pinned
    to the IP we already validated, eliminating DNS-rebinding races.
    """
    assert_safe_url(url, allow_internal=allow_internal)
    timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
    cap = max_response_bytes if max_response_bytes is not None else _MAX_RESPONSE_BYTES

    # We follow redirects manually so we can re-validate every hop.
    with _maybe_pin(url, pin_dns=pin_dns, allow_internal=allow_internal):
        response = requests.request(
            method,
            url,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            **kwargs,
        )
    hops = 0
    while response.is_redirect or response.is_permanent_redirect:
        hops += 1
        if hops > _MAX_REDIRECTS:
            response.close()
            raise SSRFError(f"Exceeded redirect limit ({_MAX_REDIRECTS}) for {url}")
        next_url = response.headers.get("Location") or response.headers.get("location")
        if not next_url:
            break
        # `requests` already resolved relative URLs on response.next.url
        next_url_full = str(response.next.url) if getattr(response, "next", None) else next_url
        response.close()
        assert_safe_url(next_url_full, allow_internal=allow_internal)
        with _maybe_pin(next_url_full, pin_dns=pin_dns, allow_internal=allow_internal):
            response = requests.request(
                method,
                next_url_full,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
                **kwargs,
            )

    # Enforce response size cap.
    chunks: list[bytes] = []
    received = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        received += len(chunk)
        if received > cap:
            response.close()
            raise SSRFError(f"Response from {url} exceeded {cap} bytes")
        chunks.append(chunk)
    response._content = b"".join(chunks)  # type: ignore[attr-defined]
    return response


def safe_get(url: str, **kwargs: Any) -> requests.Response:
    return safe_request("GET", url, **kwargs)


def safe_post(url: str, **kwargs: Any) -> requests.Response:
    return safe_request("POST", url, **kwargs)


async def safe_async_request(
    method: str,
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float | None = None,
    max_response_bytes: int | None = None,
    allow_internal: bool = False,
    pin_dns: bool = True,
    **kwargs: Any,
) -> httpx.Response:
    """``httpx`` async helper. Validates URL + every redirect hop.

    With ``pin_dns=True`` (default) DNS is pinned to the validated IP for
    each hop via ``socket.getaddrinfo`` interception, closing the
    DNS-rebinding TOCTOU window. The original hostname is preserved for
    the ``Host`` header and TLS SNI so cert verification keeps working.

    The streamed response is bounded by ``max_response_bytes`` (defaults
    to ``SAFE_HTTP_MAX_RESPONSE_BYTES``) for parity with the sync helper.
    """
    assert_safe_url(url, allow_internal=allow_internal)
    timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
    cap = max_response_bytes if max_response_bytes is not None else _MAX_RESPONSE_BYTES
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        current_url = url
        for _ in range(_MAX_REDIRECTS + 1):
            with _maybe_pin(current_url, pin_dns=pin_dns, allow_internal=allow_internal):
                response = await client.send(
                    client.build_request(method, current_url, **kwargs),
                    stream=True,
                )
            if response.is_redirect:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    return response
                current_url = str(response.next_request.url) if response.next_request else location
                assert_safe_url(current_url, allow_internal=allow_internal)
                continue
            # Enforce the response size cap on the streamed body.
            received = 0
            chunks: list[bytes] = []
            try:
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > cap:
                        await response.aclose()
                        raise SSRFError(f"Response from {url} exceeded {cap} bytes")
                    chunks.append(chunk)
            finally:
                await response.aclose()
            # Re-attach the buffered body so callers can use ``response.content``.
            response._content = b"".join(chunks)  # type: ignore[attr-defined]
            return response
        raise SSRFError(f"Exceeded redirect limit ({_MAX_REDIRECTS}) for {url}")
    finally:
        if owns_client:
            await client.aclose()
