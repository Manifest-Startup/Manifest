import app.main as main_module
from app.main import _set_cache_control_headers
from starlette.requests import Request
from starlette.responses import Response


def _request_for_path(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})


def test_framework_docs_and_openapi_are_not_public_in_default_production_mode():
    previous = main_module._IS_NON_PROD
    try:
        main_module._IS_NON_PROD = False
        kwargs = main_module._fastapi_docs_kwargs()
    finally:
        main_module._IS_NON_PROD = previous

    assert kwargs["openapi_url"] is None
    assert kwargs["docs_url"] is None
    assert kwargs["redoc_url"] is None


def test_static_asset_cache_headers_are_long_lived_and_immutable():
    response = Response(media_type="application/javascript")

    _set_cache_control_headers(_request_for_path("/assets/app.abc123.js"), response)

    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


def test_spa_html_cache_headers_revalidate_on_deploy():
    response = Response(media_type="text/html")

    _set_cache_control_headers(_request_for_path("/ideas"), response)

    assert response.headers["Cache-Control"] == "no-cache"
