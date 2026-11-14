"""Tests for envelope encryption / field-level crypto (Task #12)."""

from __future__ import annotations

import base64
import os

import pytest

from app.security import crypto


@pytest.fixture(autouse=True)
def _kek_env(monkeypatch):
    """Provide a deterministic KEK v1 for the duration of each test."""
    key_v1 = base64.b64encode(b"\x11" * 32).decode()
    key_v2 = base64.b64encode(b"\x22" * 32).decode()
    monkeypatch.setenv("MANIFEST_KEK_V1", key_v1)
    monkeypatch.setenv("MANIFEST_KEK_V2", key_v2)
    monkeypatch.setenv("MANIFEST_KEK_ACTIVE_VERSION", "1")
    monkeypatch.delenv("MANIFEST_ENV", raising=False)
    crypto.reset_kek_cache_for_test()
    yield
    crypto.reset_kek_cache_for_test()


def test_kek_loaded_from_env():
    kek = crypto.get_kek(1)
    assert kek == b"\x11" * 32
    assert crypto.get_active_kek_version() == 1


def test_dek_wrap_unwrap_roundtrip():
    dek = crypto.generate_dek()
    wrapped = crypto.wrap_dek(dek)
    assert wrapped.kek_version == 1
    blob = wrapped.to_blob()
    restored = crypto.WrappedDEK.from_blob(blob)
    assert crypto.unwrap_dek(restored) == dek


def test_field_encrypt_decrypt_roundtrip():
    dek = crypto.generate_dek()
    aad = b"context:test"
    ct = crypto.encrypt_field("hello world", dek, aad=aad)
    assert crypto.is_encrypted_blob(ct)
    assert crypto.decrypt_field(ct, dek, aad=aad) == "hello world"


def test_field_decrypt_fails_on_wrong_dek():
    dek = crypto.generate_dek()
    other = crypto.generate_dek()
    ct = crypto.encrypt_field("secret", dek)
    with pytest.raises(Exception):
        crypto.decrypt_field(ct, other)


def test_field_decrypt_fails_on_aad_mismatch():
    dek = crypto.generate_dek()
    ct = crypto.encrypt_field("secret", dek, aad=b"a")
    with pytest.raises(Exception):
        crypto.decrypt_field(ct, dek, aad=b"b")


def test_field_decrypt_fails_on_corrupted_blob():
    dek = crypto.generate_dek()
    ct = bytearray(crypto.encrypt_field("secret", dek))
    ct[-1] ^= 0x01  # flip a tag bit
    with pytest.raises(Exception):
        crypto.decrypt_field(bytes(ct), dek)


def test_unknown_kek_version_raises_in_production(monkeypatch):
    monkeypatch.setenv("MANIFEST_ENV", "production")
    monkeypatch.delenv("MANIFEST_KEK_V99", raising=False)
    crypto.reset_kek_cache_for_test()
    with pytest.raises(RuntimeError):
        crypto.get_kek(99)


def test_dek_rotation_old_wrap_still_unwraps(monkeypatch):
    # Wrap with v1...
    dek = crypto.generate_dek()
    wrapped_v1 = crypto.wrap_dek(dek)
    # ...rotate active to v2...
    monkeypatch.setenv("MANIFEST_KEK_ACTIVE_VERSION", "2")
    crypto.reset_kek_cache_for_test()
    # ...new wraps go under v2...
    wrapped_v2 = crypto.wrap_dek(dek)
    assert wrapped_v2.kek_version == 2
    # ...but v1 wrapped DEK still unwraps because v1 KEK is still configured.
    assert crypto.unwrap_dek(wrapped_v1) == dek


def test_envelope_blob_starts_with_version_byte():
    dek = crypto.generate_dek()
    ct = crypto.encrypt_field("hi", dek)
    assert ct[0] == crypto.ENVELOPE_VERSION


def test_is_encrypted_blob_rejects_garbage():
    assert not crypto.is_encrypted_blob(b"")
    assert not crypto.is_encrypted_blob("not bytes")  # type: ignore[arg-type]
    assert not crypto.is_encrypted_blob(b"\x99" + b"\x00" * 50)
