"""Unit tests for the canonical audit schema, redaction, and hash chain (SEC-068)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.security import audit_chain, audit_sink
from app.security.audit_chain import (
    GENESIS_HASH,
    Category,
    Sensitivity,
    Severity,
    canonical_payload,
    compute_event_hash,
    get_definition,
    link_event,
    sanitize_metadata,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_has_known_event_types():
    defn = get_definition("login_success")
    assert defn.category == Category.AUTH
    assert defn.severity == Severity.INFO
    assert defn.sensitivity == Sensitivity.INTERNAL


def test_registry_falls_back_for_unknown_type():
    defn = get_definition("brand_new_event_type_42")
    assert defn.event_type == "brand_new_event_type_42"
    assert defn.category == Category.SECURITY
    assert defn.severity == Severity.INFO
    # And the description hints that we should add it to the registry.
    assert "Unregistered" in defn.description


def test_detection_events_are_high_or_critical():
    """Detector emits should always page or escalate."""
    for event_type in (
        "detection_brute_force",
        "detection_impossible_travel",
        "detection_mass_export",
        "detection_priv_escalation",
        "detection_audit_chain_break",
    ):
        defn = get_definition(event_type)
        assert defn.severity in {Severity.HIGH, Severity.CRITICAL}


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------


def test_sanitize_redacts_known_secrets_and_pii():
    cleaned = sanitize_metadata({
        "openai_key": "sk-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "user_email": "founder@example.com",
        "nested": {
            "github_token": "ghp_AAAAAAAAAAAAAAAAAAAA",
            "stripe": "sk_live_AAAAAAAAAAAAAAAAAAAA",
        },
        "list_field": ["alice@example.com", "harmless"],
    })
    flat = json.dumps(cleaned)
    assert "sk-" not in flat
    assert "ghp_" not in flat
    assert "sk_live_" not in flat
    assert "@example.com" not in flat
    assert "harmless" in flat


def test_sanitize_truncates_huge_strings():
    huge = "x" * 5000
    cleaned = sanitize_metadata({"note": huge})
    assert len(cleaned["note"]) <= 2050  # 2000 + truncation marker
    assert cleaned["note"].endswith("…[truncated]")


def test_sanitize_returns_empty_dict_for_none():
    assert sanitize_metadata(None) == {}
    assert sanitize_metadata({}) == {}


def test_sanitize_does_not_mutate_input():
    original = {"openai_key": "sk-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}
    snapshot = json.dumps(original)
    sanitize_metadata(original)
    assert json.dumps(original) == snapshot


def test_sanitize_is_idempotent():
    once = sanitize_metadata({"email": "x@example.com", "n": 5})
    twice = sanitize_metadata(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Canonical payload + hash chain
# ---------------------------------------------------------------------------


def _sample_kwargs(**overrides):
    base = dict(
        event_id="11111111-1111-1111-1111-111111111111",
        event_type="login_success",
        user_id="user-1",
        request_ip="203.0.113.7",
        session_id="sess-1",
        request_id="req-1",
        metadata={"foo": "bar"},
        created_at_iso="2026-04-19T14:00:00+00:00",
    )
    base.update(overrides)
    return base


def test_canonical_payload_is_deterministic_and_sorted():
    a = canonical_payload(
        event_id="e", event_type="t", category="auth", severity="info",
        sensitivity="internal", user_id=None, request_ip=None,
        session_id=None, request_id=None, metadata={"b": 1, "a": 2},
        created_at_iso="2026-04-19T00:00:00+00:00",
    )
    b = canonical_payload(
        event_id="e", event_type="t", category="auth", severity="info",
        sensitivity="internal", user_id=None, request_ip=None,
        session_id=None, request_id=None, metadata={"a": 2, "b": 1},
        created_at_iso="2026-04-19T00:00:00+00:00",
    )
    assert a == b
    # sorted keys in the JSON output
    assert a.index('"a":') < a.index('"b":')


def test_compute_event_hash_chains_with_separator():
    h1 = compute_event_hash(None, "payload-1")  # genesis
    h2 = compute_event_hash(h1, "payload-2")
    assert h1 != h2
    # Length-extension defence: moving bytes between prev and payload
    # must not produce the same hash.
    h_split_a = compute_event_hash("aa" + "bb", "payload")
    h_split_b = compute_event_hash("aa", "bb" + "payload")
    assert h_split_a != h_split_b


def test_link_event_resolves_definition_and_hashes():
    defn, canonical, h = link_event(GENESIS_HASH, **_sample_kwargs())
    assert defn.event_type == "login_success"
    assert defn.category == Category.AUTH
    assert h == compute_event_hash(GENESIS_HASH, canonical)


def test_chain_walk_detects_tampering():
    """Tamper the middle event's metadata; the recomputed chain breaks."""
    rows = []
    prev = GENESIS_HASH
    for i in range(3):
        kwargs = _sample_kwargs(
            event_id=f"id-{i}",
            metadata={"index": i},
            created_at_iso=f"2026-04-19T14:0{i}:00+00:00",
        )
        defn, canonical, h = link_event(prev, **kwargs)
        rows.append((kwargs, prev, h, canonical))
        prev = h

    # Tamper: change the second row's metadata and re-canonicalise
    bad_kwargs = dict(rows[1][0])
    bad_kwargs["metadata"] = {"index": 999}
    _, bad_canonical, _ = link_event(rows[1][1], **bad_kwargs)

    # Reproduce the chain check: the third row's stored prev_hash no
    # longer matches the (tampered) second row's recomputed hash.
    recomputed_second = compute_event_hash(rows[1][1], bad_canonical)
    stored_third_prev = rows[2][1]
    assert recomputed_second != stored_third_prev


# ---------------------------------------------------------------------------
# SIEM sink
# ---------------------------------------------------------------------------


@pytest.fixture
def sink_dir(monkeypatch):
    audit_sink.reset_for_test()
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setenv("AUDIT_SINK_ENABLED", "1")
        monkeypatch.setenv("AUDIT_SINK_PATH", d)
        yield Path(d)
    audit_sink.reset_for_test()


def test_sink_writes_jsonl_when_enabled(sink_dir: Path):
    audit_sink.emit(
        event_id="e1", event_type="login_success", category="auth",
        severity="info", sensitivity="internal",
        user_id="u", request_ip="1.2.3.4", session_id="s", request_id="r",
        metadata={"foo": "bar"}, event_hash="h1", prev_hash="h0",
        created_at_iso="2026-04-19T14:00:00+00:00",
    )
    files = list(sink_dir.glob("audit-*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["event_id"] == "e1"
    assert parsed["metadata"] == {"foo": "bar"}
    assert parsed["event_hash"] == "h1"


def test_sink_drops_metadata_for_secret_sensitivity(sink_dir: Path):
    audit_sink.emit(
        event_id="e2", event_type="kek_rotated", category="security",
        severity="high", sensitivity="secret",
        user_id=None, request_ip=None, session_id=None, request_id=None,
        metadata={"raw_key_material": "DO_NOT_LEAK"},
        event_hash="h2", prev_hash="h1",
        created_at_iso="2026-04-19T14:01:00+00:00",
    )
    contents = next(sink_dir.glob("audit-*.jsonl")).read_text(encoding="utf-8")
    assert "DO_NOT_LEAK" not in contents
    parsed = json.loads(contents.strip())
    assert parsed.get("metadata_omitted") is True
    assert "metadata" not in parsed


def test_sink_drops_metadata_for_high_risk_category(sink_dir: Path):
    """Per defence-in-depth policy, ADMIN/PRIVACY/DETECTION export only chain
    coordinates by default — even at non-secret sensitivity — so a SIEM
    forwarder misconfig can't fan out high-risk metadata."""
    audit_sink.emit(
        event_id="e4", event_type="role_changed", category="admin",
        severity="high", sensitivity="confidential",
        user_id="admin", request_ip=None, session_id=None, request_id=None,
        metadata={"target_user": "victim@example.com", "new_role": "owner"},
        event_hash="h4", prev_hash="h3",
        created_at_iso="2026-04-19T14:03:00+00:00",
    )
    contents = next(sink_dir.glob("audit-*.jsonl")).read_text(encoding="utf-8")
    parsed = json.loads(contents.strip())
    assert parsed.get("metadata_omitted") is True
    assert "victim@example.com" not in contents


def test_sink_includes_metadata_for_low_risk_when_opted_in(sink_dir: Path, monkeypatch):
    monkeypatch.setenv("AUDIT_SINK_INCLUDE_METADATA", "1")
    audit_sink.emit(
        event_id="e5", event_type="role_changed", category="admin",
        severity="high", sensitivity="confidential",
        user_id="admin", request_ip=None, session_id=None, request_id=None,
        metadata={"new_role": "owner"},
        event_hash="h5", prev_hash="h4",
        created_at_iso="2026-04-19T14:04:00+00:00",
    )
    parsed = json.loads(next(sink_dir.glob("audit-*.jsonl")).read_text(encoding="utf-8").strip())
    assert parsed.get("metadata") == {"new_role": "owner"}


def test_secondary_redactors_strip_bearer_tokens_and_hex_secrets():
    raw = {
        "headers": "Authorization: Bearer abcdEFGH1234567890tokenValueXYZ==",
        "leaked_hash": "deadbeef" * 8,  # 64-char hex
        "note": "All good — no secrets here.",
    }
    cleaned = sanitize_metadata(raw)
    assert "abcdEFGH1234567890tokenValueXYZ" not in json.dumps(cleaned)
    assert "deadbeef" * 8 not in json.dumps(cleaned)
    # Plain prose must still pass through.
    assert cleaned["note"] == "All good — no secrets here."


def test_sink_noop_when_disabled(monkeypatch, tmp_path):
    audit_sink.reset_for_test()
    monkeypatch.delenv("AUDIT_SINK_ENABLED", raising=False)
    monkeypatch.setenv("AUDIT_SINK_PATH", str(tmp_path))
    audit_sink.emit(
        event_id="e3", event_type="login_success", category="auth",
        severity="info", sensitivity="internal",
        user_id=None, request_ip=None, session_id=None, request_id=None,
        metadata={}, event_hash="h", prev_hash="h",
        created_at_iso="2026-04-19T14:02:00+00:00",
    )
    assert list(tmp_path.glob("*.jsonl")) == []
