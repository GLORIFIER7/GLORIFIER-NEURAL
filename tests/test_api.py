from fastapi.testclient import TestClient

from app.api import app


client = TestClient(app)


def test_health_does_not_overclaim_dependencies():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["process"] == "VERIFIED"
    assert body["checks"]["providers"] == "NOT VERIFIED"
    assert body["checks"]["database"] == "NOT VERIFIED"


def test_security_headers_are_present():
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_task_endpoint_disabled_without_token(monkeypatch):
    monkeypatch.delenv("GLORIFIER_API_TOKEN", raising=False)
    monkeypatch.setenv("GLORIFIER_REQUIRE_API_TOKEN", "false")
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


def test_missing_token_cannot_be_bypassed_by_environment_flag(monkeypatch):
    monkeypatch.delenv("GLORIFIER_API_TOKEN", raising=False)
    monkeypatch.setenv("GLORIFIER_REQUIRE_API_TOKEN", "false")
    response = client.post("/v1/tasks", json={"task": "test"})
    assert response.status_code == 503


def test_action_class_input_is_bounded(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "test", "action_class": "x" * 65},
    )
    assert response.status_code == 422

def test_task_input_bounds_are_enforced(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    headers = {"Authorization": "Bearer test-secret"}

    empty_task = client.post(
        "/v1/tasks",
        headers=headers,
        json={"task": ""},
    )
    oversized_task = client.post(
        "/v1/tasks",
        headers=headers,
        json={"task": "x" * 20_001},
    )
    oversized_purpose = client.post(
        "/v1/tasks",
        headers=headers,
        json={"task": "test", "purpose": "x" * 101},
    )

    assert empty_task.status_code == 422
    assert oversized_task.status_code == 422
    assert oversized_purpose.status_code == 422
