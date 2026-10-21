import dataclasses
import json

import pytest

from app.audit import AuditEvent, AuditSink, SupabaseRestAuditSink


def test_audit_event_contains_only_minimal_operational_fields():
    event = AuditEvent(
        request_id="req-123",
        event_type="task_received",
        status="NOT VERIFIED",
        action_class="read_only",
        evidence=("execution:none",),
    )

    assert event.request_id == "req-123"
    assert event.evidence == ("execution:none",)
    assert "task" not in {field.name for field in dataclasses.fields(event)}
    assert "authorization" not in {field.name for field in dataclasses.fields(event)}
    assert "details" not in {field.name for field in dataclasses.fields(event)}


def test_audit_event_is_immutable():
    event = AuditEvent(
        request_id="req-123",
        event_type="task_received",
        status="NOT VERIFIED",
        action_class="read_only",
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.status = "VERIFIED"


def test_persistence_boundary_is_not_implicitly_implemented():
    sink = AuditSink()
    event = AuditEvent(
        request_id="req-123",
        event_type="task_received",
        status="NOT VERIFIED",
        action_class="read_only",
    )

    with pytest.raises(NotImplementedError):
        sink.write(event)


def test_supabase_sink_is_disabled_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("GLORIFIER_AUDIT_ENABLED", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    assert SupabaseRestAuditSink.from_environment() is None


def test_enabled_supabase_sink_requires_credentials(monkeypatch):
    monkeypatch.setenv("GLORIFIER_AUDIT_ENABLED", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(ValueError, match="credentials are missing"):
        SupabaseRestAuditSink.from_environment()


def test_supabase_sink_requires_https():
    with pytest.raises(ValueError, match="HTTPS"):
        SupabaseRestAuditSink("http://example.supabase.co", "test-key")


def test_supabase_sink_posts_only_sanitized_allowlisted_fields(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.audit.urllib.request.urlopen", fake_urlopen)
    sink = SupabaseRestAuditSink("https://example.supabase.co", "test-service-role-key")
    sink.write(
        AuditEvent(
            request_id="req-123",
            event_type="task_received",
            status="NOT VERIFIED",
            action_class="read_only",
            provider=None,
            evidence=("execution:none",),
        )
    )

    assert captured["url"] == "https://example.supabase.co/rest/v1/audit_events"
    assert captured["timeout"] == 2.0
    assert captured["body"] == {
        "request_id": "req-123",
        "event_type": "task_received",
        "status": "NOT VERIFIED",
        "action_class": "read_only",
        "provider": None,
        "evidence": ["execution:none"],
        "details": {},
    }
    assert "test-service-role-key" in captured["headers"]["Authorization"]
    assert captured["headers"]["Content-profile"] == "glorifier"


def test_supabase_sink_rejects_oversized_evidence_before_network(monkeypatch):
    sink = SupabaseRestAuditSink("https://example.supabase.co", "test-key")
    monkeypatch.setattr(
        "app.audit.urllib.request.urlopen",
        lambda *args, **kwargs: pytest.fail("network must not be called"),
    )
    event = AuditEvent(
        request_id="req-123",
        event_type="task_received",
        status="NOT VERIFIED",
        action_class="read_only",
        evidence=("x" * 161,),
    )
    with pytest.raises(ValueError, match="Invalid audit evidence"):
        sink.write(event)
