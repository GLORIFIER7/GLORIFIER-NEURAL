from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_health_does_not_overclaim_dependencies():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["process"] == "VERIFIED"
    assert body["checks"]["providers"] == "NOT OBSERVABLE"
    assert body["checks"]["database"] == "NOT OBSERVABLE"


def test_task_endpoint_disabled_without_token(monkeypatch):
    monkeypatch.delenv("GLORIFIER_API_TOKEN", raising=False)
    monkeypatch.setenv("GLORIFIER_REQUIRE_API_TOKEN", "true")
    response = client.post("/v1/tasks", json={"task": "test"})
    assert response.status_code == 503


def test_task_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer wrong-secret"},
        json={"task": "test", "require_approval": False},
    )
    assert response.status_code == 401


def test_task_endpoint_never_claims_inference_without_provider(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "test", "require_approval": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT VERIFIED"
    assert body["evidence"] == ["provider:none", "execution:none"]
