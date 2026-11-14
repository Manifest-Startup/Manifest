"""Profile pictures must land in durable storage on stateless hosts."""

from unittest.mock import MagicMock, patch

from app.main import fastapi_app
from app.routes.dependencies import require_user_id
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _client():
    fastapi_app.dependency_overrides[require_user_id] = lambda: "user-1"
    return TestClient(fastapi_app)


def _db():
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
    return db


def test_profile_picture_uses_supabase_storage_when_configured():
    db = _db()
    try:
        with (
            patch("app.routes.account_routes._supabase_configured", return_value=True),
            patch(
                "app.routes.account_routes.upload_bytes_to_supabase",
                return_value="https://ref.supabase.co/storage/v1/object/public/profile-pictures/user-1/a.png",
            ) as upload,
            patch("app.routes.account_routes.create_database_client", return_value=db),
        ):
            response = _client().post(
                "/api/account/profile-picture", files={"file": ("a.png", PNG, "image/png")}
            )
    finally:
        fastapi_app.dependency_overrides.pop(require_user_id, None)

    assert response.status_code == 200
    url = response.json()["profilePictureUrl"]
    assert url.startswith("https://ref.supabase.co/storage/v1/object/public/profile-pictures/")
    payload, bucket, path, content_type = upload.call_args.args
    assert payload == PNG
    assert bucket == "profile-pictures"
    assert path.startswith("user-1/") and path.endswith(".png")
    assert content_type == "image/png"
    db.table.return_value.update.assert_called_once_with({"profile_picture_url": url})


def test_profile_picture_falls_back_to_local_disk_without_storage(tmp_path):
    db = _db()
    try:
        with (
            patch("app.routes.account_routes._supabase_configured", return_value=False),
            patch("app.routes.account_routes.GENERATED_PDF_ROOT", tmp_path),
            patch("app.routes.account_routes.create_database_client", return_value=db),
        ):
            response = _client().post(
                "/api/account/profile-picture", files={"file": ("a.png", PNG, "image/png")}
            )
    finally:
        fastapi_app.dependency_overrides.pop(require_user_id, None)

    assert response.status_code == 200
    url = response.json()["profilePictureUrl"]
    assert url.startswith("/generated/pdfs/profile-pictures/user-1/")
    assert (tmp_path / url.removeprefix("/generated/pdfs/")).read_bytes() == PNG
