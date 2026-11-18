"""Vault sync (ADR 0007): the account store, and two computers syncing through it with the
plugin's manifest_vault.py (its Account talks to the service directly instead of over HTTP)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from app.db.database import InMemoryDatabaseClient
from app.services.ideas import vault, vault_sync

USER = "11111111-1111-1111-1111-111111111111"
SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "agent-plugin/skills/manifest-vault/scripts/manifest_vault.py"
)


@pytest.fixture
def db():
    return InMemoryDatabaseClient()


@pytest.fixture
def mv():
    spec = importlib.util.spec_from_file_location("manifest_vault_for_sync", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- the account store -------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../x.md",
        "Notes/../x.md",
        ".obsidian/app.md",
        "Notes/a.png",
        "a\\..\\b.md",
    ],
)
def test_paths_outside_the_vault_or_hidden_are_refused(path):
    with pytest.raises(vault_sync.VaultSyncError):
        vault_sync.clean_path(path)


def test_save_update_conflict_and_delete(db):
    first = vault_sync.put_file(db, USER, "Notes/a.md", "one", None, device="mac")
    assert first["status"] == "saved"
    sha1 = first["file"]["sha256"]
    assert vault_sync.put_file(db, USER, "Notes/a.md", "one", None)["status"] == "unchanged"

    second = vault_sync.put_file(db, USER, "Notes/a.md", "two", sha1)
    assert second["status"] == "saved"
    stale = vault_sync.put_file(db, USER, "Notes/a.md", "three", sha1)
    assert stale["status"] == "conflict" and stale["file"]["content"] == "two"

    gone = vault_sync.put_file(db, USER, "Notes/a.md", None, second["file"]["sha256"])
    assert gone["status"] == "saved" and gone["file"]["deleted"] is True
    page = vault_sync.list_files(db, USER)
    assert [(f["path"], f["deleted"], f["content"]) for f in page["files"]] == [
        ("Notes/a.md", True, None)
    ]
    # A deleted path can be created again from scratch.
    assert vault_sync.put_file(db, USER, "Notes/a.md", "back", None)["status"] == "saved"


def test_list_is_per_person_and_incremental(db):
    vault_sync.put_file(db, USER, "Notes/a.md", "a", None)
    vault_sync.put_file(db, "someone-else", "Notes/b.md", "b", None)
    page = vault_sync.list_files(db, USER)
    assert [f["path"] for f in page["files"]] == ["Notes/a.md"]
    assert vault_sync.list_files(db, USER, page["server_time"])["files"] == []


def test_large_files_stay_local(db):
    with pytest.raises(vault_sync.VaultSyncError):
        vault_sync.put_file(db, USER, "Notes/big.md", "x" * (vault_sync.MAX_BYTES + 1), None)


# -- two computers -------------------------------------------------------------------------


def _account(mv, db, ideas: list[dict]):
    def post(url, body, auth=None, timeout=30):
        query, v = body["query"], body["variables"]
        if "vaultExport" in query:
            files = vault.build_files(ideas, {}, [])
            return {
                "data": {
                    "vaultExport": {"generatedAt": "2026-11-18T06:00:00+00:00", "files": files}
                }
            }
        if "vaultFiles" in query:
            page = vault_sync.list_files(db, USER, v["s"])
            return {"data": {"vaultFiles": {"serverTime": page["server_time"], **page}}}
        result = vault_sync.put_file(
            db, USER, v["p"], None if v["d"] else v["c"], v["b"], device=v["v"]
        )
        return {"data": {"putVaultFile": result}}

    return mv.Account("https://example.test", "token", post=post)


IDEA = {
    "idea_id": "i1",
    "title": "TideLine",
    "description": "Street flood warnings.",
    "updated_at": "2026-11-18T05:00:00+00:00",
}


def test_two_computers_share_notes_and_writing(mv, db, tmp_path):
    acct = _account(mv, db, [IDEA])
    laptop, desktop = tmp_path / "laptop", tmp_path / "desktop"
    mv.sync_online(laptop, acct)
    mv.sync_online(desktop, acct)

    # Branding: the logo sits beside Home, which embeds it; the snippet is enabled.
    home = (laptop / "Manifest/Home.md").read_text()
    assert "![[Manifest logo.svg|72]]" in home and "cssclasses" in home
    assert (laptop / mv.LOGO_PATH).read_text().startswith("<svg")
    appearance = json.loads((laptop / ".obsidian/appearance.json").read_text())
    assert appearance["enabledCssSnippets"] == ["manifest"]

    # A note and "My notes" writing on the laptop reach the desktop.
    (laptop / "Notes/Pricing.md").write_text("Charge cities per sensor.\n")
    idea_file = laptop / "Manifest/Ideas/TideLine.md"
    idea_file.write_text(idea_file.read_text() + "Call the harbour office.\n")
    report = mv.sync_online(laptop, acct)
    assert "uploaded Notes/Pricing.md" in report
    mv.sync_online(desktop, acct)
    assert (desktop / "Notes/Pricing.md").read_text() == "Charge cities per sensor.\n"
    assert "Call the harbour office." in (desktop / "Manifest/Ideas/TideLine.md").read_text()

    # Both edit the same note: both versions survive.
    (laptop / "Notes/Pricing.md").write_text("Laptop version\n")
    (desktop / "Notes/Pricing.md").write_text("Desktop version\n")
    mv.sync_online(laptop, acct)
    report = mv.sync_online(desktop, acct)
    assert any(line.startswith("conflict: kept both") for line in report)
    assert (desktop / "Notes/Pricing.md").read_text() == "Laptop version\n"
    copies = list((desktop / "Notes").glob("Pricing (conflicted copy *).md"))
    assert [c.read_text() for c in copies] == ["Desktop version\n"]

    # A deletion moves the file to .trash on the other computer; nothing is destroyed.
    mv.sync_online(laptop, acct)
    (laptop / "Notes/Pricing.md").unlink()
    assert "deleted from your account: Notes/Pricing.md" in mv.sync_online(laptop, acct)
    mv.sync_online(desktop, acct)
    assert not (desktop / "Notes/Pricing.md").exists()
    assert (desktop / ".trash/Notes/Pricing.md").read_text() == "Laptop version\n"


def test_offline_keeps_changes_and_reports_status(mv, db, tmp_path):
    def down(*args, **kwargs):
        raise mv.Offline("Can't reach Manifest.")

    laptop = tmp_path / "laptop"
    (laptop / "Notes").mkdir(parents=True)
    (laptop / "Notes/Idea.md").write_text("written on a plane\n")
    with pytest.raises(mv.Offline):
        mv.sync_online(laptop, mv.Account("https://example.test", "t", post=down))
    state = mv.load_state(laptop)
    assert state["status"] == "offline"
    changed, _ = mv.pending_changes(laptop, state)
    assert "Notes/Idea.md" in changed

    mv.sync_online(laptop, _account(mv, db, [IDEA]))
    assert vault_sync.list_files(db, USER)["files"][0]["content"] == "written on a plane\n"
    assert mv.load_state(laptop)["status"] == "up to date"


def test_mass_disappearance_does_not_delete_from_the_account(mv, db, tmp_path):
    acct = _account(mv, db, [IDEA])
    laptop = tmp_path / "laptop"
    (laptop / "Notes").mkdir(parents=True)
    for n in range(30):
        (laptop / f"Notes/n{n}.md").write_text(f"note {n}\n")
    mv.sync_online(laptop, acct)
    for n in range(30):
        (laptop / f"Notes/n{n}.md").unlink()
    report = mv.sync_online(laptop, acct)
    assert any("no deletions were sent" in line for line in report)
    assert not any(f["deleted"] for f in vault_sync.list_files(db, USER)["files"])
