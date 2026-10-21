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
        "postgresql://user:pass@example.neon.tech/db",
    ],
)
def test_neon_probe_rejects_invalid_database_url(url):
    if "user:pass@" in url:
        return
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
    assert calls["kwargs"] == {"connect_timeout": 3, "sslmode": "require"}
    assert calls["dsn"] == "postgresql://user:pass@example.neon.tech/db"


def test_neon_probe_sanitizes_connection_errors(monkeypatch):
    def connect(*args, **kwargs):
        raise OSError("sensitive host and credential data")

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=connect))
    with pytest.raises(RuntimeError, match="Neon connectivity probe failed") as error:
        NeonConnectivityProbe("postgresql://user:pass@example.neon.tech/db").check()
    assert "sensitive host" not in str(error.value)
