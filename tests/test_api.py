from app.api import app
from fastapi.testclient import TestClient


client = TestClient(app)


def test_health_does_not_overclaim_dependencies():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["process"] == "VERIFIED"
    assert body["checks"]["providers"] == "NOT OBSERVABLE"
    assert body["checks"]["database"] == "NOT OBSERVABLE"


def test_task_endpoint_disabled_without_token(monkeypatch):
    monkeypatch.setenv("GLORIFIER_REQUIRE_API_TOKEN", "true")
    monkeypatch.delenv("GLORIFIER_API_TOKEN", raising=False)
    response = client.post("/v1/tasks", json={"task": "test"})
    assert response.status_code == 503
