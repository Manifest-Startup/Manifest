"""Tests for the SSRF-safe outbound HTTP helpers (Task #13 / SEC-008)."""

from __future__ import annotations

import socket

import pytest

from app.security import safe_http


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/x",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/loopback",
    ],
)
def test_assert_safe_url_rejects_internal_ips(url):
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com/_test",
        "javascript:alert(1)",
    ],
)
def test_assert_safe_url_rejects_non_http_schemes(url):
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url(url)


def test_assert_safe_url_rejects_credential_in_url():
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url("http://user:pass@example.com/")


def test_assert_safe_url_rejects_metadata_ipv6():
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url("http://[fd00:ec2::254]/")


def test_assert_safe_url_allows_internal_when_explicit():
    # Used by tests / one-off scripts; never set in production code.
    assert safe_http.assert_safe_url("http://127.0.0.1/", allow_internal=True)


def test_assert_safe_url_accepts_public_hostname(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    assert safe_http.assert_safe_url("https://example.com/hello") == "https://example.com/hello"


def test_assert_safe_url_rejects_dns_pointing_to_private(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url("https://internal.example.com/")


def test_assert_safe_url_rejects_unresolvable(monkeypatch):
    def fake_getaddrinfo(host, port):
        raise socket.gaierror("nope")

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(safe_http.SSRFError):
        safe_http.assert_safe_url("https://does-not-exist.invalid/")


def test_pick_safe_resolved_ip_returns_first_safe_address(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    assert safe_http.pick_safe_resolved_ip("example.com") == "93.184.216.34"


def test_pick_safe_resolved_ip_skips_internal_and_picks_safe(monkeypatch):
    def fake_getaddrinfo(host, port):
        # First answer is private (would be the SSRF rebind), second is public.
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0)),
        ]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    assert safe_http.pick_safe_resolved_ip("mixed.example") == "8.8.8.8"


def test_pick_safe_resolved_ip_raises_when_all_internal(monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(safe_http.SSRFError):
        safe_http.pick_safe_resolved_ip("metadata.example")


def test_safe_async_request_enforces_response_size_cap(monkeypatch):
    """Async helper must cap streamed responses at ``max_response_bytes``."""
    import asyncio

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", fake_getaddrinfo)

    class _FakeStreamResponse:
        is_redirect = False
        headers: dict = {}
        next_request = None

        async def aiter_bytes(self):
            for _ in range(10):
                yield b"x" * 1024

        async def aclose(self):
            pass

    class _FakeClient:
        def build_request(self, method, url, **kwargs):
            return ("REQ", method, url)

        async def send(self, request, stream=False):  # noqa: ARG002
            return _FakeStreamResponse()

        async def aclose(self):
            pass

    fake_client = _FakeClient()

    async def _run():
        await safe_http.safe_async_request(
            "GET",
            "https://example.com/big",
            client=fake_client,
            max_response_bytes=2048,  # Cap below the 10 KB stream.
        )

    with pytest.raises(safe_http.SSRFError, match="exceeded"):
        asyncio.run(_run())


def test_dns_pin_blocks_rebinding_at_connect_time(monkeypatch):
    """After preflight, a malicious DNS that flips to internal must be ignored.

    Pinning replaces ``socket.getaddrinfo`` so the connection goes to the
    safe IP we already validated, not to whatever the resolver returns at
    connect time.
    """
    calls = {"n": 0}
    safe_ip = "93.184.216.34"
    rebind_ip = "10.0.0.5"

    def flipping_getaddrinfo(host, port, *args, **kwargs):
        calls["n"] += 1
        # Preflight calls (assert_safe_url + pick_safe_resolved_ip) return
        # the safe IP so validation + pinning succeed. After that, the
        # malicious resolver flips to an internal IP — the pin must override.
        if calls["n"] <= 2:
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (safe_ip, 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (rebind_ip, 0))]

    monkeypatch.setattr(safe_http.socket, "getaddrinfo", flipping_getaddrinfo)

    captured: dict = {}

    def fake_request(method, url, *args, **kwargs):  # noqa: ARG001
        # Record what getaddrinfo would now return: with pinning active
        # we expect the safe IP, not the rebound internal IP.
        infos = socket.getaddrinfo("rebind.example", 443)
        captured["resolved_ip"] = infos[0][4][0]

        class _Resp:
            is_redirect = False
            is_permanent_redirect = False
            headers: dict = {}

            def iter_content(self, chunk_size):
                return iter([b"ok"])

            def close(self):
                pass

        return _Resp()

    monkeypatch.setattr(safe_http.requests, "request", fake_request)
    safe_http.safe_request("GET", "https://rebind.example/")
    assert captured["resolved_ip"] == safe_ip, (
        "DNS pinning should force the connection to the validated IP, "
        f"got {captured['resolved_ip']}"
    )
