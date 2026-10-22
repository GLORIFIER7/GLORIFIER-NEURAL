"""Opt-in, read-only Neon PostgreSQL connectivity probe.

This module never writes data or creates schemas. It runs only when explicitly
enabled, and all failures are sanitized before they can reach an API response.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


class NeonConnectivityProbe:
    """Run a bounded TLS-only SELECT 1 against an explicitly configured Neon URL."""

    def __init__(self, database_url: str, *, timeout_seconds: int = 3) -> None:
        parsed = urlparse(database_url)
        if (
            parsed.scheme not in ("postgres", "postgresql")
            or not parsed.hostname
            or parsed.username is None
            or parsed.password is None
            or not 0 < timeout_seconds <= 5
        ):
            raise ValueError("Neon database URL or timeout is invalid")
        self._database_url = database_url
        self._timeout = timeout_seconds

    @classmethod
    def from_environment(cls) -> NeonConnectivityProbe | None:
        """Return a probe only when explicitly enabled and configured."""
        if os.getenv("GLORIFIER_NEON_CONNECTIVITY_ENABLED", "").strip().casefold() != "true":
            return None
        database_url = os.getenv("NEON_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("Neon connectivity is enabled but its URL is missing")
        return cls(database_url)

    def check(self) -> None:
        """Verify connection and execute a read-only constant query; never expose errors."""
        try:
            import psycopg
        except ImportError:
            raise RuntimeError("Neon connectivity driver is not installed") from None

        try:
            with psycopg.connect(
                self._database_url,
                connect_timeout=self._timeout,
                sslmode="require",
            ) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row != (1,):
                    raise RuntimeError("Neon connectivity probe returned an unexpected result")
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 - do not leak DSN, server errors, or query context
            raise RuntimeError("Neon connectivity probe failed") from None
