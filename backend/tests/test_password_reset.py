"""Tests for the password reset utilities and rate limiter.

Service-level integration tests that exercise the GraphQL mutation
end-to-end (with DB writes) are intentionally out of scope here — the
test suite mocks the Supabase client and direct psycopg2 connections
are not wired up. These tests focus on the pure-Python pieces, which
cover the bulk of the reset flow's correctness-critical logic.
"""

from __future__ import annotations

import pytest

from app.services import password_reset_service as prs
from app.utils.reset_token_utils import (
    compare_token_hashes,
    generate_reset_token,
    hash_token,
)


def setup_function(_):
    prs._reset_buckets_for_test()


def test_generate_reset_token_hashes_match():
    raw, digest = generate_reset_token()
    assert isinstance(raw, str) and len(raw) >= 32
    assert hash_token(raw) == digest


def test_generate_reset_token_unique():
    a, _ = generate_reset_token()
    b, _ = generate_reset_token()
    assert a != b


def test_hash_token_is_deterministic_and_unique_per_input():
    assert hash_token("a") == hash_token("a")
    assert hash_token("a") != hash_token("b")
    # SHA-256 hex digest length is 64.
    assert len(hash_token("anything")) == 64


def test_compare_token_hashes_constant_time():
    raw, digest = generate_reset_token()
    assert compare_token_hashes(digest, digest) is True
    assert compare_token_hashes(digest, "0" * len(digest)) is False
    assert compare_token_hashes("", "") is True
    assert compare_token_hashes(digest, "") is False


@pytest.mark.parametrize(
    "password,expected_error_contains",
    [
        (None, "required"),
        ("", "8 characters"),
        ("short", "8 characters"),
        ("a" * 7, "8 characters"),
        ("a" * 257, "too long"),
        # Composition policy added in Task #11: at least 3 character classes.
        ("abcdefgh", "three of"),
        ("alllowercase", "three of"),
    ],
)
def test_validate_password_strength_rejects_bad_inputs(password, expected_error_contains):
    err = prs.validate_password_strength(password)
    assert err is not None
    assert expected_error_contains in err.lower()


def test_validate_password_strength_accepts_minimum():
    # Must have ≥3 character classes (uppercase, lowercase, digit, symbol).
    assert prs.validate_password_strength("Sup3r-Str0ng-Pwd!") is None
    assert prs.validate_password_strength("Abcd1234") is None


def test_request_rate_limit_blocks_after_email_threshold():
    email = "rate-test@example.com"
    ip = "10.0.0.1"
    for _ in range(5):
        assert prs.check_request_rate_limit(email, ip) is True
    # 6th attempt for the same email should be blocked.
    assert prs.check_request_rate_limit(email, ip) is False


def test_request_rate_limit_blocks_after_ip_threshold():
    ip = "10.0.0.99"
    # Use 20 distinct emails so the per-email limit doesn't trip first.
    for i in range(20):
        assert prs.check_request_rate_limit(f"u{i}@example.com", ip) is True
    assert prs.check_request_rate_limit("u-extra@example.com", ip) is False


def test_request_rate_limit_independent_ips():
    for _ in range(5):
        assert prs.check_request_rate_limit("alice@example.com", "10.0.0.1") is True
    # Different email + different IP starts fresh on both counters.
    assert prs.check_request_rate_limit("bob@example.com", "10.0.0.2") is True


def test_reset_attempt_rate_limit():
    ip = "10.0.0.50"
    for _ in range(20):
        assert prs.check_reset_attempt_rate_limit(ip) is True
    assert prs.check_reset_attempt_rate_limit(ip) is False


def test_build_reset_url_uses_app_base_url(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://manifest.example/")
    # request_base_url must be ignored to prevent host-header poisoning.
    url = prs.build_reset_url("abc123", request_base_url="https://attacker.example")
    assert url == "https://manifest.example/auth/reset-password?token=abc123"


def test_build_reset_url_ignores_request_host(monkeypatch):
    """Even without APP_BASE_URL we must not honour the request's Host header."""
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    url = prs.build_reset_url("xyz", request_base_url="https://attacker.example")
    assert url == "http://localhost:5000/auth/reset-password?token=xyz"


def test_build_reset_url_falls_back_to_localhost(monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    url = prs.build_reset_url("xyz")
    assert url == "http://localhost:5000/auth/reset-password?token=xyz"
