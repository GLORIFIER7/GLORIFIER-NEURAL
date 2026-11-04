import secrets
import sys
import types

import pytest

from app.database.neon import NeonConnectivityProbe


def test_neon_probe_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GLORIFIER_NEON_CONNECTIVITY_ENABLED", raising=False)
    monkeypatch.setenv("NEON_DATABASE_URL", "postgresql://user:pass@example.neon.tech/db")
    assert NeonConnectivityProbe.from_environment() is None


def test_enabled_neon_probe_requires_url(monkeypatch):
    monkeypatch.setenv("GLORIFIER_NEON_CONNECTIVITY_ENABLED", "true")
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="URL is missing"):
        NeonConnectivityProbe.from_environment()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.neon.tech/db",
        "postgresql://example.neon.tech/db",
    ],
)
def test_neon_probe_rejects_invalid_database_url(url):
    with pytest.raises(ValueError, match="URL or timeout is invalid"):
        NeonConnectivityProbe(url)


def test_neon_probe_uses_tls_bounded_connection_and_read_only_query(monkeypatch):
    calls = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query):
            calls["query"] = query

        def fetchone(self):
            return (1,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    def connect(dsn, **kwargs):
        calls["dsn"] = dsn
        calls["kwargs"] = kwargs
        return Connection()

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    NeonConnectivityProbe("postgresql://user:pass@example.neon.tech/db").check()

    assert calls["query"] == "SELECT 1"
    assert calls["kwargs"] == {
        "connect_timeout": 3,
        "sslmode": "verify-full",
        "sslrootcert": "system",
        "channel_binding": "require",
    }
    assert calls["dsn"] == "postgresql://user:pass@example.neon.tech/db"


def test_neon_probe_sanitizes_connection_errors(monkeypatch):
    def connect(*args, **kwargs):
        raise OSError("sensitive host and credential data")

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    with pytest.raises(RuntimeError, match="Neon connectivity probe failed") as error:
        NeonConnectivityProbe("postgresql://user:pass@example.neon.tech/db").check()
    assert "sensitive host" not in str(error.value)

@pytest.mark.parametrize("timeout_seconds", [1, 3, 5])
def test_neon_connection_options_accepts_bounded_integer_timeouts(timeout_seconds):
    from app.database.neon import neon_connection_options

    assert neon_connection_options(timeout_seconds) == {
        "connect_timeout": timeout_seconds,
        "sslmode": "verify-full",
        "sslrootcert": "system",
        "channel_binding": "require",
    }


@pytest.mark.parametrize(
    "timeout_seconds",
    [0, -1, 6, True, False, 1.5, "3", None],
)
def test_neon_connection_options_rejects_invalid_timeouts(timeout_seconds):
    from app.database.neon import neon_connection_options

    with pytest.raises(ValueError, match="Neon connection timeout"):
        neon_connection_options(timeout_seconds)


@pytest.mark.parametrize("timeout_seconds", [0, 6, True, 1.5])
def test_neon_probe_rejects_invalid_timeout_types_and_ranges(timeout_seconds):
    with pytest.raises(ValueError, match="Neon connection timeout"):
        NeonConnectivityProbe(
            "postgresql://user:pass@example.neon.tech/db",
            timeout_seconds=timeout_seconds,
        )



def test_worker_neon_probe_uses_pg8000_with_verified_tls(monkeypatch):
    calls = {}

    class Cursor:
        def execute(self, query):
            calls["query"] = query

        def fetchone(self):
            return (1,)

        def close(self):
            calls["cursor_closed"] = True

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            calls["closed"] = True

    def connect(**kwargs):
        calls["kwargs"] = kwargs
        return Connection()

    monkeypatch.setitem(sys.modules, "pg8000", types.SimpleNamespace(connect=connect))
    probe = NeonConnectivityProbe(
        "postgresql://neon_user:neon_pass@example.neon.tech/neural"
    )

    probe.check_worker()

    ssl_context = calls["kwargs"]["ssl_context"]
    assert ssl_context.verify_mode == 2
    assert ssl_context.check_hostname is True
    assert calls["kwargs"]["host"] == "example.neon.tech"
    assert calls["kwargs"]["database"] == "neural"
    assert calls["kwargs"]["user"] == "neon_user"
    assert calls["kwargs"]["password"] == "neon_pass"
    assert calls["query"] == "SELECT 1"
    assert calls["closed"] is True


def test_worker_neon_probe_sanitizes_driver_errors(monkeypatch, caplog):
    def connect(**_kwargs):
        raise OSError("private database host and password")

    monkeypatch.setitem(sys.modules, "pg8000", types.SimpleNamespace(connect=connect))
    probe = NeonConnectivityProbe(
        "postgresql://neon_user:neon_pass@example.neon.tech/neural"
    )

    with (
        caplog.at_level("WARNING", logger="app.database.neon"),
        pytest.raises(RuntimeError, match="Neon connectivity probe failed") as error,
    ):
        probe.check_worker()

    assert "private database host" not in str(error.value)
    assert "neon_pass" not in str(error.value)
    assert "OSError" in caplog.text
    assert "private database host" not in caplog.text
    assert "neon_pass" not in caplog.text


def test_worker_neon_configuration_uses_task_run_opt_in_and_request_bindings():
    env = {
        "GLORIFIER_NEON_TASK_RUNS_ENABLED": "true",
        "NEON_DATABASE_URL": "postgresql://neon_user:neon_pass@example.neon.tech/neural",
    }

    probe = NeonConnectivityProbe.from_environment(env)

    assert probe is not None
    assert probe._database_url == env["NEON_DATABASE_URL"]


def test_neon_probe_uses_cloudflare_readonly_hyperdrive_binding(monkeypatch):
    calls = {}

    class Cursor:
        def execute(self, query):
            calls["query"] = query

        def fetchone(self):
            return (1,)

        def close(self):
            return None

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            calls["closed"] = True

    def connect(**kwargs):
        calls["kwargs"] = kwargs
        return Connection()

    monkeypatch.setitem(sys.modules, "pg8000", types.SimpleNamespace(connect=connect))
    hyperdrive = types.SimpleNamespace(
        user="neon_readonly",
        password=secrets.token_urlsafe(32),
        host="hyperdrive.internal",
        port="5432",
        database="glorifier",
    )
    probe = NeonConnectivityProbe.from_environment(
        {
            "GLORIFIER_NEON_CONNECTIVITY_ENABLED": "true",
            "NEON_READONLY": hyperdrive,
        }
    )

    probe.check_worker()

    assert calls["kwargs"]["host"] == "hyperdrive.internal"
    assert calls["kwargs"]["database"] == "glorifier"
    assert calls["kwargs"]["timeout"] == 15
    assert calls["kwargs"]["ssl_context"] is False
    assert calls["query"] == "SELECT 1"
    assert calls["closed"] is True

def test_worker_probe_preserves_result_mismatch_when_cleanup_fails(monkeypatch):
    from types import SimpleNamespace

    class Cursor:
        def execute(self, _query):
            return None

        def fetchone(self):
            return (0,)

        def close(self):
            raise RuntimeError("cleanup failure must not hide the probe result")

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            raise RuntimeError("connection cleanup failure must not hide the probe result")

    monkeypatch.setitem(sys.modules, "pg8000", types.SimpleNamespace(connect=lambda **_kwargs: Connection()))
    probe = NeonConnectivityProbe.from_environment(
        {
            "GLORIFIER_NEON_CONNECTIVITY_ENABLED": "true",
            "NEON_READONLY": SimpleNamespace(
                user="neon_readonly",
                password=secrets.token_urlsafe(32),
                host="hyperdrive.internal",
                port="5432",
                database="glorifier",
            ),
        }
    )

    with pytest.raises(RuntimeError, match="unexpected result") as exc_info:
        probe.check_worker()

    assert "cleanup failure" not in str(exc_info.value)
