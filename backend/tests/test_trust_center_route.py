from fastapi.testclient import TestClient

from app.main import fastapi_app


def test_trust_center_returns_program_snapshot():
    client = TestClient(fastapi_app)
    resp = client.get("/api/trust-center")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "program_version",
        "generated_at",
        "company",
        "frameworks",
        "data_subject_rights",
        "controls",
        "sub_processors_url",
    ):
        assert key in body, f"missing trust-center field {key}"
    rights = body["data_subject_rights"]
    assert rights["access"] == "GET /api/dsar/access"
    assert rights["erasure"] == "POST /api/dsar/erase"
    assert body["frameworks"]["gdpr"]["status"]
    assert body["frameworks"]["hipaa"]["role"] == "business_associate"
