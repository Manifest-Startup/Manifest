from unittest.mock import patch

from scripts import run_privacy_retention as runner


class _Cur:
    def __init__(self):
        self.calls = []
        self.rowcount = 4

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))


class _Conn:
    def __init__(self, cur):
        self.cur_obj = cur
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cur_obj

    def commit(self):
        self.committed = True


def test_run_all_executes_every_policy_and_returns_summary():
    cur = _Cur()
    conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.object(runner, "record_security_event") as audit:
        summary = runner.run_all()
    assert len(summary["policies"]) == len(runner.RETENTION_POLICIES)
    for pol in summary["policies"]:
        assert pol["outcome"] == "success"
        assert pol["deleted"] == 4
    audit.assert_called_once()
    assert conn.committed is True


def test_run_all_skips_when_no_database_configured():
    with patch.object(runner, "get_database_url", return_value=None), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    for pol in summary["policies"]:
        assert pol["outcome"] == "skipped_no_db"


def test_run_all_marks_failure_on_exception():
    class _BadCur(_Cur):
        def execute(self, sql, params):
            raise RuntimeError("nope")

    bad_conn = _Conn(_BadCur())
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=bad_conn), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    assert all(p["outcome"] == "failure" for p in summary["policies"])


def test_run_all_applies_retention_exception_predicates(tmp_path):
    """A YAML hold scoped to ``users`` must be injected as
    ``AND NOT (...)`` into the guest_accounts DELETE so held rows
    survive the run."""
    register = tmp_path / "ex.yaml"
    register.write_text(
        "exceptions:\n"
        "  - id: LIT-2026-001\n"
        "    scope: users\n"
        "    match: \"user_id = 'held-1'\"\n"
        "    reason: litigation hold\n"
        "    approved_by: DPO\n"
        "    opened_at: '2026-04-01T00:00:00Z'\n",
        encoding="utf-8",
    )
    cur = _Cur()
    conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    assert summary["register_status"] == "ok"
    assert any(e["id"] == "LIT-2026-001" for e in summary["active_exceptions"])
    guest = next(p for p in summary["policies"] if p["name"] == "guest_accounts")
    assert "LIT-2026-001" in guest["exceptions_applied"]
    guest_sql = next(sql for sql, _ in cur.calls if "FROM users" in sql)
    assert "AND NOT (user_id = 'held-1')" in guest_sql
    pwd = next(p for p in summary["policies"] if p["name"] == "expired_password_reset_tokens")
    assert pwd["exceptions_applied"] == []


def test_run_all_fails_safe_when_register_is_malformed(tmp_path):
    """If the register file exists but cannot be parsed, the run must
    skip every destructive policy rather than silently delete data
    under legal hold."""
    register = tmp_path / "broken.yaml"
    register.write_text("exceptions: [ this is : not valid yaml", encoding="utf-8")
    cur = _Cur()
    conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event") as audit:
        summary = runner.run_all()
    assert summary["register_status"].startswith("error:")
    assert all(p["outcome"] == "skipped_register_error" for p in summary["policies"])
    assert cur.calls == []  # no DELETE was issued
    audit.assert_called_once()
    assert audit.call_args.kwargs["outcome"] == "partial"


def _assert_no_destructive_calls(cur, summary, expected_status_prefix="error:"):
    assert summary["register_status"].startswith(expected_status_prefix)
    assert all(p["outcome"] == "skipped_register_error" for p in summary["policies"])
    assert cur.calls == []


def test_run_all_fails_safe_when_register_file_is_empty(tmp_path):
    """An *existing but empty/truncated* register file must be treated
    as a hard error — the only allowed empty state is a *missing* file.
    Otherwise an accidentally-cleared register would silently drop
    every legal hold."""
    register = tmp_path / "empty.yaml"
    register.write_text("", encoding="utf-8")
    cur = _Cur(); conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    _assert_no_destructive_calls(cur, summary)
    assert summary["register_status"] == "error:register_empty_file"


def test_run_all_fails_safe_when_register_root_is_list(tmp_path):
    register = tmp_path / "rootlist.yaml"
    register.write_text("- foo\n- bar\n", encoding="utf-8")
    cur = _Cur(); conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    _assert_no_destructive_calls(cur, summary)


def test_run_all_fails_safe_when_exceptions_key_missing(tmp_path):
    register = tmp_path / "missing.yaml"
    register.write_text("other_key: 1\n", encoding="utf-8")
    cur = _Cur(); conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    _assert_no_destructive_calls(cur, summary)


def test_run_all_fails_safe_when_exceptions_not_a_list(tmp_path):
    register = tmp_path / "scalar.yaml"
    register.write_text("exceptions: foo\n", encoding="utf-8")
    cur = _Cur(); conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    _assert_no_destructive_calls(cur, summary)


def test_run_all_rejects_match_predicate_with_sql_injection(tmp_path):
    """An entry whose ``match`` predicate would inject a second
    statement, comment, or destructive keyword must be rejected by the
    allowlist. Because the entry is then dropped, the whole register is
    treated as partially-invalid and the run aborts fail-safe."""
    register = tmp_path / "evil.yaml"
    register.write_text(
        "exceptions:\n"
        "  - id: EVIL-1\n"
        "    scope: users\n"
        "    match: \"1=1; DROP TABLE users\"\n"
        "    reason: tampered entry\n"
        "    approved_by: attacker\n"
        "    opened_at: '2026-04-01T00:00:00Z'\n",
        encoding="utf-8",
    )
    cur = _Cur(); conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    _assert_no_destructive_calls(cur, summary)


def test_run_all_fails_safe_when_register_entries_invalid(tmp_path):
    """Non-empty exceptions list whose entries are all malformed must
    also block the destructive run — silently dropping all holds is
    unacceptable."""
    register = tmp_path / "invalid.yaml"
    register.write_text(
        "exceptions:\n  - not_a_dict\n  - 42\n",
        encoding="utf-8",
    )
    cur = _Cur()
    conn = _Conn(cur)
    with patch.object(runner, "get_database_url", return_value="postgres://x"), \
         patch.object(runner, "get_db_connection", return_value=conn), \
         patch.dict("os.environ", {"RETENTION_EXCEPTIONS_PATH": str(register)}), \
         patch.object(runner, "record_security_event"):
        summary = runner.run_all()
    assert summary["register_status"] == "error:register_entries_invalid"
    assert cur.calls == []
