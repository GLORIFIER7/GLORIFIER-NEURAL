"""Runtime integration checks for migrations applied to a disposable PostgreSQL database."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from psycopg import Error


DATABASE_URL = os.environ["GLORIFIER_TEST_DATABASE_URL"]


def rejected(connection, statement: str, params: tuple) -> None:
    try:
        connection.execute(statement, params)
    except Error:
        connection.rollback()
        return
    connection.rollback()
    raise AssertionError("Expected database constraint to reject invalid data")


def main() -> None:
    now = datetime.now(UTC)
    request_id = str(uuid4())
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            """INSERT INTO glorifier.task_runs
               (request_id, action_class, status, evidence, created_at, expires_at)
               VALUES (%s, 'integration_test', 'VERIFIED', '[]'::jsonb, %s, %s)""",
            (request_id, now, now + timedelta(days=1)),
        )
        conn.execute("DELETE FROM glorifier.task_runs WHERE request_id = %s", (request_id,))

        base = (
            str(uuid4()), "integration_test", "VERIFIED", "[]",
            now, now + timedelta(days=1),
        )
        insert_task = """INSERT INTO glorifier.task_runs
            (request_id, action_class, status, evidence, created_at, expires_at)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)"""
        rejected(conn, insert_task, (base[0], "Bad Action", base[2], base[3], base[4], base[5]))
        rejected(conn, insert_task, (base[0], base[1], "success", base[3], base[4], base[5]))
        rejected(
            conn, insert_task,
            (base[0], base[1], base[2], json.dumps(["x"] * 21), base[4], base[5]),
        )
        rejected(
            conn, insert_task,
            (base[0], base[1], base[2], "[]", base[4], base[4] + timedelta(days=31)),
        )

        conn.execute(
            """INSERT INTO glorifier.audit_events
               (request_id, event_type, status, action_class, evidence, details)
               VALUES (%s, 'task_received', 'VERIFIED', 'integration_test', '[]'::jsonb, '{}'::jsonb)""",
            (str(uuid4()),),
        )
        rejected(
            conn,
            """INSERT INTO glorifier.audit_events
               (request_id, event_type, status, action_class, evidence, details)
               VALUES (%s, 'unknown_event', 'VERIFIED', 'integration_test', '[]'::jsonb, '{}'::jsonb)""",
            (str(uuid4()),),
        )
        rejected(
            conn,
            """INSERT INTO glorifier.audit_events
               (request_id, event_type, status, action_class, evidence, details)
               VALUES (%s, 'task_received', 'VERIFIED', 'integration_test', '{}'::jsonb, '{}'::jsonb)""",
            (str(uuid4()),),
        )

        rls = conn.execute(
            """SELECT c.relrowsecurity FROM pg_class c
               JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'glorifier' AND c.relname = 'audit_events'"""
        ).fetchone()
        assert rls == (True,), "Supabase audit table must have RLS enabled"

        grants = conn.execute(
            """SELECT
                 has_schema_privilege('service_role', 'glorifier', 'USAGE'),
                 has_table_privilege('service_role', 'glorifier.audit_events', 'INSERT'),
                 has_table_privilege('service_role', 'glorifier.audit_events', 'SELECT')"""
        ).fetchone()
        assert grants == (True, True, False), f"Unexpected service_role grants: {grants}"

    print("Disposable PostgreSQL migration integration checks passed.")


if __name__ == "__main__":
    main()
