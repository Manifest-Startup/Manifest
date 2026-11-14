"""Tests for GraphQL surface hardening (SEC-029)."""

from __future__ import annotations

import importlib
import os

import pytest


def _reload_schema():
    import app.graphql.schema as sch
    importlib.reload(sch)
    return sch


def test_default_extensions_include_depth_alias_and_token_limiters():
    sch = _reload_schema()
    names = {type(ext).__name__ for ext in sch.schema.extensions}
    assert "QueryDepthLimiter" in names
    assert "MaxAliasesLimiter" in names
    assert "MaxTokensLimiter" in names


def test_introspection_disabled_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("GRAPHQL_INTROSPECTION", raising=False)
    sch = _reload_schema()
    names = {type(ext).__name__ for ext in sch.schema.extensions}
    assert "DisableIntrospection" in names


def test_introspection_enabled_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("GRAPHQL_INTROSPECTION", raising=False)
    sch = _reload_schema()
    names = {type(ext).__name__ for ext in sch.schema.extensions}
    assert "DisableIntrospection" not in names


def test_introspection_force_disabled_via_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("GRAPHQL_INTROSPECTION", "false")
    sch = _reload_schema()
    names = {type(ext).__name__ for ext in sch.schema.extensions}
    assert "DisableIntrospection" in names


@pytest.fixture(autouse=True)
def _restore_env():
    saved = {k: os.environ.get(k) for k in ("ENVIRONMENT", "GRAPHQL_INTROSPECTION")}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    _reload_schema()
