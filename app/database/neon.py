"""Opt-in Neon PostgreSQL connectivity checks for local and Cloudflare runtimes."""
from __future__ import annotations

import os
import ssl
from collections.abc import Mapping
from urllib.parse import urlparse


def neon_connection_options(timeout_seconds: int = 3) -> dict[str, int | str]:
    """Return mandatory TLS server-authentication options for psycopg."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 0 < timeout_seconds <= 5
    ):
        raise ValueError("Neon connection timeout must be between 1 and 5 seconds")
    return {
        "connect_timeout": timeout_seconds,
        "sslmode": "verify-full",
        "sslrootcert": "system",
        "channel_binding": "require",
    }


def _environment_value(environment, name: str, default: str = "") -> str:
    if environment is None:
        return os.getenv(name, default)
    if isinstance(environment, Mapping):
        value = environment.get(name, default)
    else:
        value = getattr(environment, name, default)
    return default if value is None else str(value)


class NeonConnectivityProbe:
    """Run a bounded SELECT 1 probe using psycopg locally or pg8000 on Workers."""

    def __init__(
        self,
        database_url: str | None,
        *,
        hyperdrive=None,
        timeout_seconds: int = 3,
    ) -> None:
        neon_connection_options(timeout_seconds)
        if database_url:
            try:
                parsed = urlparse(database_url)
                parsed_port = parsed.port
            except (TypeError, ValueError):
                raise ValueError("Neon database URL or timeout is invalid") from None
            if (
                parsed.scheme not in ("postgres", "postgresql")
                or not parsed.hostname
                or parsed.username is None
                or parsed.password is None
                or (parsed_port is not None and not 1 <= parsed_port <= 65535)
            ):
                raise ValueError("Neon database URL or timeout is invalid")
        elif hyperdrive is None:
            raise ValueError("Neon database URL or Hyperdrive binding is required")
        self._database_url = database_url
        self._hyperdrive = hyperdrive
        self._timeout = timeout_seconds

    @classmethod
    def from_environment(cls, environment=None) -> NeonConnectivityProbe | None:
        """Return a probe only when connectivity or task-run persistence is explicitly enabled."""
        connectivity_enabled = (
            _environment_value(environment, "GLORIFIER_NEON_CONNECTIVITY_ENABLED")
            .strip()
            .casefold() == "true"
        )
        task_runs_enabled = (
            _environment_value(environment, "GLORIFIER_NEON_TASK_RUNS_ENABLED")
            .strip()
            .casefold() == "true"
        )
        if not connectivity_enabled and not task_runs_enabled:
            return None
        database_url = _environment_value(environment, "NEON_DATABASE_URL").strip()
        if isinstance(environment, Mapping):
            hyperdrive = environment.get("NEON_READONLY") or environment.get("NEON_WRITE")
        elif environment is not None:
            hyperdrive = getattr(environment, "NEON_READONLY", None) or getattr(
                environment, "NEON_WRITE", None
            )
        else:
            hyperdrive = None
        if not database_url and hyperdrive is None:
            raise ValueError("Neon connectivity is enabled but its URL is missing and no Hyperdrive binding is configured")
        return cls(database_url or None, hyperdrive=hyperdrive)

    def check(self) -> None:
        """Verify connection with psycopg and TLS verification outside Workers."""
        try:
            import psycopg
        except ImportError:
            raise RuntimeError("Neon connectivity driver is not installed") from None

        try:
            with psycopg.connect(
                self._database_url,
                **neon_connection_options(self._timeout),
            ) as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row != (1,):
                    raise RuntimeError("Neon connectivity probe returned an unexpected result")
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 - do not leak DSN, server errors, or query context
            raise RuntimeError("Neon connectivity probe failed") from None

    def check_worker(self) -> None:
        """Verify a Neon connection on Python Workers with the supported pg8000 driver."""
        try:
            import pg8000
        except ImportError:
            raise RuntimeError("Neon connectivity driver is not installed") from None

        connection = None
        cursor = None
        row = None
        query_completed = False
        operation_failed = False
        cleanup_failed = False
        try:
            if self._hyperdrive is not None:
                connection = pg8000.connect(
                    user=str(self._hyperdrive.user),
                    password=str(self._hyperdrive.password),
                    host=str(self._hyperdrive.host),
                    port=int(self._hyperdrive.port),
                    database=str(self._hyperdrive.database),
                    ssl_context=False,
                    timeout=self._timeout,
                )
            else:
                parsed = urlparse(self._database_url)
                connection = pg8000.connect(
                    user=parsed.username,
                    password=parsed.password,
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    database=parsed.path.lstrip("/"),
                    ssl_context=ssl.create_default_context(),
                    timeout=self._timeout,
                )
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            query_completed = True
        except Exception:  # noqa: BLE001 - do not leak DSN, server errors, or query context
            operation_failed = True
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:  # noqa: BLE001 - preserve the authoritative probe result
                    cleanup_failed = True
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001 - preserve the authoritative probe result
                    cleanup_failed = True

        if query_completed and row != (1,):
            raise RuntimeError("Neon connectivity probe returned an unexpected result")
        if operation_failed or cleanup_failed:
            raise RuntimeError("Neon connectivity probe failed") from None
