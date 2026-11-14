import asyncio

from app.security.edge_guard import EdgeGuardMiddleware


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _run(mw, path, headers=(), scope_type="http"):
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request"}

    scope = {"type": scope_type, "path": path, "headers": list(headers)}
    asyncio.run(mw(scope, receive, send))
    return sent


def test_guard_disabled_without_secret():
    assert _run(EdgeGuardMiddleware(_ok_app, secret=""), "/graphql")[0]["status"] == 200


def test_guard_rejects_missing_or_wrong_secret():
    mw = EdgeGuardMiddleware(_ok_app, secret="s3cret")
    assert _run(mw, "/graphql")[0]["status"] == 403
    assert _run(mw, "/graphql", [(b"x-manifest-edge", b"nope")])[0]["status"] == 403


def test_guard_accepts_edge_secret_and_open_health_paths():
    mw = EdgeGuardMiddleware(_ok_app, secret="s3cret")
    assert _run(mw, "/graphql", [(b"x-manifest-edge", b"s3cret")])[0]["status"] == 200
    for path in ("/ping", "/health", "/healthz"):
        assert _run(mw, path)[0]["status"] == 200


def test_guard_closes_unauthenticated_websockets():
    mw = EdgeGuardMiddleware(_ok_app, secret="s3cret")
    assert _run(mw, "/socket.io/", scope_type="websocket") == [
        {"type": "websocket.close", "code": 4403}
    ]


def test_guard_passes_lifespan_events():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(EdgeGuardMiddleware(app, secret="s3cret")({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]
