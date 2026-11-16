"""``manifest login``: approve the CLI in the browser (loopback redirect + PKCE, ADR 0003)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import socket
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

LOGIN_TIMEOUT_SECONDS = 300

_DONE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Manifest CLI</title></head>
<body style="font-family:system-ui,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<main style="max-width:26rem;text-align:center;padding:1rem"><h1 style="letter-spacing:-.03em">{title}</h1>
<p style="color:#57534e">{message}</p></main></body></html>"""


class LoginError(Exception):
    pass


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str
    state: str


def new_pkce() -> Pkce:
    verifier = secrets.token_urlsafe(64)  # 86 URL-safe characters (RFC 7636: 43-128)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return Pkce(verifier=verifier, challenge=challenge, state=secrets.token_urlsafe(24))


def authorize_url(base_url: str, redirect_uri: str, pkce: Pkce) -> str:
    query = urlencode(
        {
            "redirect_uri": redirect_uri,
            "state": pkce.state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{base_url.rstrip('/')}/api/cli/authorize?{query}"


class _CallbackServer(HTTPServer):
    result: dict[str, str] | None = None
    done: threading.Event


class _Handler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parts = urlsplit(self.path)
        if parts.path != "/callback":
            self.send_error(404)
            return
        params = {k: v[0] for k, v in parse_qs(parts.query).items()}
        ok = "code" in params and "error" not in params
        title = "Manifest CLI is signed in" if ok else "Manifest CLI was not signed in"
        message = (
            "You can close this tab and return to your terminal."
            if ok
            else "Return to your terminal for details."
        )
        body = _DONE_PAGE.format(title=title, message=message).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if self.server.result is None:
            self.server.result = params
            self.server.done.set()

    def log_message(self, *args: Any) -> None:  # keep the terminal quiet
        return


def wait_for_callback(
    pkce: Pkce,
    open_url,
    *,
    base_url: str,
    timeout: float = LOGIN_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """Serve ``http://127.0.0.1:<random port>/callback``, open the approval page,
    and return ``(code, redirect_uri)`` once the browser comes back."""
    server = _CallbackServer(("127.0.0.1", 0), _Handler)
    server.done = threading.Event()
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/callback"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        open_url(authorize_url(base_url, redirect_uri, pkce))
        if not server.done.wait(timeout):
            raise LoginError("Timed out waiting for the browser. Run `manifest login` again.")
    finally:
        server.shutdown()
        server.server_close()
    params = server.result or {}
    if params.get("state") != pkce.state:
        raise LoginError("The browser returned a different state; refusing to continue.")
    if params.get("error"):
        raise LoginError(
            "You cancelled the sign-in." if params["error"] == "access_denied" else params["error"]
        )
    code = params.get("code")
    if not code:
        raise LoginError("The browser did not return a sign-in code.")
    return code, redirect_uri


def open_in_browser(url: str, *, launch: bool = True, out=None) -> None:
    import sys

    stream = out or sys.stderr
    print("Opening Manifest in your browser to approve this computer…", file=stream)
    print(f"If it does not open, visit:\n  {url}", file=stream)
    if launch:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - the printed URL still works
            pass


def hostname() -> str:
    return socket.gethostname() or "unknown host"
