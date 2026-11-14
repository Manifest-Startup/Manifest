import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Manifest API is live"}


def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json()["message"] == "pong"


def test_health_aliases():
    for path in ("/health", "/healthz"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["message"] == "pong"
