import dataclasses

import pytest

from app.audit import AuditEvent, AuditSink


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
