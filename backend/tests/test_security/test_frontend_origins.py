import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.security.config import frontend_origins_from_env


def test_frontend_origins_from_env_parses_comma_separated_urls(monkeypatch):
    monkeypatch.setenv(
        "FRONTEND_ORIGINS",
        "https://manifest.vercel.app, https://staging.manifeststartup.com",
    )
    assert frontend_origins_from_env() == [
        "https://manifest.vercel.app",
        "https://staging.manifeststartup.com",
    ]


def test_frontend_origins_from_env_adds_https_for_bare_hosts(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "my-app.vercel.app")
    assert frontend_origins_from_env() == ["https://my-app.vercel.app"]


def test_frontend_origins_from_env_empty_when_unset(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)
    assert frontend_origins_from_env() == []
