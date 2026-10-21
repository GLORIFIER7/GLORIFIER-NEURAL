-- GLORIFIER Neural audit foundation (PostgreSQL / Supabase compatible).
-- This migration creates storage only; the application does not write to it yet.
-- Apply only after reviewing the target database and taking a backup.

begin;

create schema if not exists glorifier;

create table if not exists glorifier.audit_events (
    event_id uuid primary key default gen_random_uuid(),
    request_id text not null,
    event_type text not null check (
        event_type in ('task_received', 'policy_denied', 'approval_required',
                       'inference_started', 'inference_completed', 'inference_failed', 'task_not_executed')
    ),
    status text not null check (
        status in ('FULLY VERIFIED', 'VERIFIED', 'PARTIALLY VERIFIED',
                   'NOT VERIFIED', 'DEGRADED', 'NOT OBSERVABLE')
    ),
    action_class text not null,
    provider text,
    evidence jsonb not null default '[]'::jsonb
        check (jsonb_typeof(evidence) = 'array'),
    details jsonb not null default '{}'::jsonb
        check (jsonb_typeof(details) = 'object'),
    created_at timestamptz not null default now()
);

create index if not exists audit_events_request_id_created_at_idx
    on glorifier.audit_events (request_id, created_at desc);

create index if not exists audit_events_created_at_idx
    on glorifier.audit_events (created_at desc);

alter table glorifier.audit_events enable row level security;

comment on table glorifier.audit_events is
    'Append-oriented operational evidence. Never store prompts, secrets, credentials, or raw customer content in details.';

commit;
