import uuid

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


def test_readiness_fails_closed_while_integrations_are_missing():
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "NOT READY"
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
    assert body["evidence"] == ["inference:disabled", "execution:none"]


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


def test_response_has_unique_correlation_id():
    first = client.get("/health")
    second = client.get("/health")

    first_id = first.headers["x-request-id"]
    second_id = second.headers["x-request-id"]

    assert str(uuid.UUID(first_id)) == first_id
    assert str(uuid.UUID(second_id)) == second_id
    assert first_id != second_id


def test_sensitive_action_is_denied_at_api_boundary(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "transfer funds", "action_class": "financial", "require_approval": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DEGRADED"
    assert body["evidence"] == ["policy:deny"]
    assert "blocked by default" in body["message"]


def test_task_endpoint_rejects_missing_authorization(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post("/v1/tasks", json={"task": "test"})
    assert response.status_code == 401


def test_task_endpoint_rejects_unknown_fields(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "test", "unexpected_admin_override": True},
    )
    assert response.status_code == 422


def test_task_endpoint_rejects_blank_task(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "   "},
    )
    assert response.status_code == 422


def test_readiness_response_has_security_headers():
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_readiness_does_not_claim_database_or_provider_health():
    response = client.get("/ready")
    body = response.json()
    assert body["status"] == "NOT READY"
    assert set(body["checks"]) == {"providers", "database"}
    assert all(value == "NOT VERIFIED" for value in body["checks"].values())

def test_declared_oversized_request_body_is_rejected():
    response = client.get("/health", headers={"Content-Length": "65537"})
    assert response.status_code == 413
    assert response.json()["detail"] == "Request body exceeds the 65536-byte limit"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]

def test_malformed_content_length_is_rejected():
    response = client.get("/health", headers={"Content-Length": "invalid"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Content-Length header"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_negative_content_length_is_rejected():
    response = client.get("/health", headers={"Content-Length": "-1"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Content-Length header"


def test_opt_in_audit_records_sanitized_events_with_response_request_id(monkeypatch):
    from app.audit import AuditEvent

    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    events = []

    class FakeSink:
        def write(self, event: AuditEvent):
            events.append(event)

    monkeypatch.setattr("app.api.SupabaseRestAuditSink.from_environment", lambda: FakeSink())
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "private task text", "require_approval": False},
    )

    assert response.status_code == 200
    assert len(events) == 2
    assert events[0].event_type == "task_received"
    assert events[1].event_type == "task_not_executed"
    assert events[0].request_id == response.headers["x-request-id"]
    assert events[1].request_id == response.headers["x-request-id"]
    assert all(not hasattr(event, "task") for event in events)
    assert all("private task text" not in repr(event) for event in events)


def test_audit_write_failure_prevents_task_execution(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    called = {"run": False}

    class BrokenSink:
        def write(self, event):
            raise RuntimeError("private credentials must not leak")

    def forbidden_run(task_request):
        called["run"] = True
        raise AssertionError("task execution must not start if initial audit write fails")

    monkeypatch.setattr("app.api.SupabaseRestAuditSink.from_environment", lambda: BrokenSink())
    monkeypatch.setattr("app.api.orchestrator.run", forbidden_run)
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "test", "require_approval": False},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Audit persistence unavailable; task not executed"
    assert "private credentials" not in response.text
    assert called["run"] is False



def test_task_endpoint_rate_limits_authenticated_requests(monkeypatch):
    from app.rate_limit import FixedWindowRateLimiter

    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    monkeypatch.setattr("app.api.TASK_RATE_LIMITER", FixedWindowRateLimiter(max_requests=1))
    headers = {"Authorization": "Bearer test-secret"}
    first = client.post("/v1/tasks", headers=headers, json={"task": "first"})
    second = client.post("/v1/tasks", headers=headers, json={"task": "second"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1


def test_task_rate_limit_does_not_apply_before_authentication(monkeypatch):
    from app.rate_limit import FixedWindowRateLimiter

    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    monkeypatch.setattr("app.api.TASK_RATE_LIMITER", FixedWindowRateLimiter(max_requests=1))
    first = client.post("/v1/tasks", headers={"Authorization": "Bearer wrong"}, json={"task": "first"})
    second = client.post("/v1/tasks", headers={"Authorization": "Bearer wrong"}, json={"task": "second"})

    assert first.status_code == 401
    assert second.status_code == 401


def test_final_audit_write_failure_returns_503_without_leaking_details(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    writes = {"count": 0}

    class FinalWriteFails:
        def write(self, event):
            writes["count"] += 1
            if writes["count"] == 2:
                raise RuntimeError("secret-key-and-private-payload")

    monkeypatch.setattr(
        "app.api.SupabaseRestAuditSink.from_environment",
        lambda: FinalWriteFails(),
    )
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "safe test task", "require_approval": False},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Audit persistence failed after task processing; inspect audit status"
    )
    assert "secret-key-and-private-payload" not in response.text
    assert writes["count"] == 2



def test_unexpected_initial_audit_failure_fails_closed_without_leaking(monkeypatch):
    monkeypatch.setenv("GLORIFIER_API_TOKEN", "test-secret")
    called = {"run": False}

    class BrokenSink:
        def write(self, event):
            raise OSError("internal network path and credential details")

    def forbidden_run(task_request):
        called["run"] = True
        raise AssertionError("task processing must not start after audit failure")

    monkeypatch.setattr("app.api.SupabaseRestAuditSink.from_environment", lambda: BrokenSink())
    monkeypatch.setattr("app.api.orchestrator.run", forbidden_run)
    response = client.post(
        "/v1/tasks",
        headers={"Authorization": "Bearer test-secret"},
        json={"task": "test", "require_approval": False},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Audit persistence unavailable; task not executed"
    assert "internal network path" not in response.text
    assert called["run"] is False
