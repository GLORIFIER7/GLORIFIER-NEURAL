from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.database.task_runs import RETENTION_DAYS, TaskRunRepository


def test_task_run_repository_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GLORIFIER_NEON_TASK_RUNS_ENABLED", raising=False)
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    assert TaskRunRepository.from_environment() is None


def test_task_run_repository_requires_url_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("GLORIFIER_NEON_TASK_RUNS_ENABLED", "true")
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="URL is missing"):
        TaskRunRepository.from_environment()


def test_valid_metadata_is_bounded_and_retained_for_30_days():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    values = TaskRunRepository.validate_record(
        request_id=str(uuid4()), action_class="summarize", status="NOT VERIFIED",
        provider="nvidia_nim", evidence=["inference:disabled", "execution:none"], now=now,
    )
    assert values[5] == now
    assert values[6] == now + timedelta(days=RETENTION_DAYS)
    assert values[4] == ["inference:disabled", "execution:none"]


@pytest.mark.parametrize("action_class", ["", "Summarize", "customer prompt", "x" * 81, "hello\nworld"])
def test_rejects_unsafe_action_class(action_class):
    with pytest.raises(ValueError, match="action_class"):
        TaskRunRepository.validate_record(
            request_id=str(uuid4()), action_class=action_class, status="VERIFIED"
        )


def test_rejects_unknown_status():
    with pytest.raises(ValueError, match="status"):
        TaskRunRepository.validate_record(
            request_id=str(uuid4()), action_class="summarize", status="success"
        )


def test_rejects_free_text_in_evidence():
    with pytest.raises(ValueError, match="evidence"):
        TaskRunRepository.validate_record(
            request_id=str(uuid4()), action_class="summarize", status="VERIFIED",
            evidence=["customer email is example@example.com"],
        )


def test_rejects_oversized_evidence_list():
    with pytest.raises(ValueError, match="20 evidence codes"):
        TaskRunRepository.validate_record(
            request_id=str(uuid4()), action_class="summarize", status="VERIFIED",
            evidence=[f"event:{index}" for index in range(21)],
        )


def test_rejects_naive_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        TaskRunRepository.validate_record(
            request_id=str(uuid4()), action_class="summarize", status="VERIFIED",
            now=datetime(2026, 1, 1),
        )



def test_delete_expired_uses_bounded_expiry_only_batch(monkeypatch):
    import sys
    from types import SimpleNamespace

    class Cursor:
        def __init__(self):
            self.query = ""
            self.params = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params

        def fetchall(self):
            return [(uuid4(),), (uuid4(),)]

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self.cursor_instance

    connection = Connection()
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: connection),
    )
    now = datetime(2026, 2, 1, tzinfo=UTC)
    repository = TaskRunRepository("postgresql://test.invalid/db")

    assert repository.delete_expired(batch_size=50, now=now) == 2
    assert connection.cursor_instance.params == (now, 50)
    assert "expires_at <= %s" in connection.cursor_instance.query
    assert "LIMIT %s" in connection.cursor_instance.query
    assert "FOR UPDATE SKIP LOCKED" in connection.cursor_instance.query


@pytest.mark.parametrize("batch_size", [0, -1, 1001, True, 1.5])
def test_delete_expired_rejects_unsafe_batch_size(batch_size):
    repository = TaskRunRepository("postgresql://test.invalid/db")
    with pytest.raises(ValueError, match="batch_size"):
        repository.delete_expired(batch_size=batch_size)


def test_delete_expired_rejects_naive_timestamp():
    repository = TaskRunRepository("postgresql://test.invalid/db")
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.delete_expired(now=datetime(2026, 1, 1))
