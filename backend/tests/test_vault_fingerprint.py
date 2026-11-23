"""vaultExport's fingerprint: nothing to send when nothing changed, everything when anything
did, deletions included (they leave no timestamp)."""

from app.db.database import InMemoryDatabaseClient
from app.services.ideas import vault


def _db():
    db = InMemoryDatabaseClient()
    for iid, title in (("a", "TideLine"), ("b", "DrainWatch")):
        db.table("ideas").insert(
            {
                "idea_id": iid,
                "user_id": "u1",
                "title": title,
                "description": f"{title} warns streets about floods.",
                "created_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
            }
        ).execute()
    return db


def test_unchanged_account_sends_nothing():
    db = _db()
    first = vault.build_vault(db, "u1")
    again = vault.build_vault(db, "u1", "2026-11-20T00:00:00+00:00", first["fingerprint"])
    assert again["files"] == [] and again["paths"] == []
    assert again["fingerprint"] == first["fingerprint"]


def test_a_deleted_idea_changes_the_fingerprint_and_sends_the_full_listing():
    db = _db()
    first = vault.build_vault(db, "u1")
    assert "Manifest/Ideas/DrainWatch.md" in first["paths"]
    db.table("ideas").delete().eq("idea_id", "b").execute()
    after = vault.build_vault(db, "u1", "2026-11-20T00:00:00+00:00", first["fingerprint"])
    assert after["fingerprint"] != first["fingerprint"]
    assert "Manifest/Home.md" in after["paths"]
    assert "Manifest/Ideas/DrainWatch.md" not in after["paths"]
    assert any(f["path"] == "Manifest/Ideas/TideLine.md" for f in after["files"])
