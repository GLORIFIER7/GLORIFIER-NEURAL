# Database foundation

This folder contains a reviewed starting point for PostgreSQL-compatible audit storage.

## Status

- Migration: schema only; **not applied** to Supabase or Neon.
- Application integration: **NOT VERIFIED**; the API does not write audit events.
- Reconciliation, retention, backup/restore, and production permissions: **NOT VERIFIED**.
- The migration enables row-level security and intentionally creates no client-facing policies. Access should be granted only through a separately reviewed server-side role/policy design.

## Apply safely

1. Confirm the exact target project and environment.
2. Take and verify a database backup or restore point.
3. Review `migrations/0001_audit_events.sql`.
4. Apply it in a development/staging database first using the provider's migration workflow.
5. Verify the table, indexes, RLS state, and rollback/recovery procedure before considering production.

Do not paste database connection strings or service-role keys into GitHub issues, source files, or chat.

## Data handling

Do not store raw prompts, provider credentials, authorization headers, or sensitive customer content in audit details. Use request identifiers and minimal, non-sensitive evidence. Define retention and deletion rules before collecting production data.

This migration is compatible in intent with PostgreSQL deployments such as Supabase and Neon, but it has not been executed against either service.
