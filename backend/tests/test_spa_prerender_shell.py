"""Tests for route-specific SPA HTML shells."""

from app.services.web.spa_prerender_shell import apply_spa_shell, normalize_path, resolve_route_shell

SAMPLE_HTML = """<!DOCTYPE html>
<html><head>
<title>Default</title>
<meta name="description" content="Default description" />
<link rel="canonical" href="https://manifeststartup.com/" />
</head><body>
<noscript>You need to enable JavaScript to run this app.</noscript>
<div id="root"></div>
</body></html>"""


def test_normalize_path():
    assert normalize_path("/") == "/"
    assert normalize_path("/login/") == "/login"
    assert normalize_path("/pitch-reels?x=1") == "/pitch-reels"


def test_resolve_route_shell_login():
    shell = resolve_route_shell("/login")
    assert shell is not None
    assert shell.h1 == "Sign in to Manifest"
    assert shell.canonical_path == "/auth"


def test_apply_spa_shell_injects_h1_and_metadata():
    html = apply_spa_shell(SAMPLE_HTML, "/signup")
    assert "<h1>Create your Manifest account</h1>" in html
    assert "Create a Manifest account" in html
    assert 'rel="canonical" href="https://manifeststartup.com/auth"' in html
    assert "manifest-noscript-fallback" in html
    assert 'id="manifest-static-shell"' in html


def test_apply_spa_shell_unknown_path_is_unchanged():
    html = apply_spa_shell(SAMPLE_HTML, "/ideas")
    assert html == SAMPLE_HTML


def test_distinct_shell_signatures_for_public_routes():
    home = apply_spa_shell(SAMPLE_HTML, "/")
    login = apply_spa_shell(SAMPLE_HTML, "/login")
    assert home != login
    assert "Turn your idea into a plan" in home
    assert "Sign in to Manifest" in login
