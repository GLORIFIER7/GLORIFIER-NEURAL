# GLORIFIER Neural Orchestration

A governed, provider-neutral AI orchestration API built with Python and FastAPI. This repository is an implementation starter, **not** a claim that any model provider, database, agent network, or production environment is connected.

## Current capabilities

- FastAPI liveness/status endpoint at `GET /health`.
- Fail-closed readiness endpoint at `GET /ready` (HTTP 503 until provider and database integrations are implemented and verified).
- Task request/response schemas with input limits, including a bounded action-class field.
- Enforces a 64 KiB request-body limit against both the declared `Content-Length` and streamed ASGI body chunks; keep a matching limit at the reverse proxy as defense in depth.
- Deny-by-default policy for financial actions, wallet signing, minting, destructive operations, production writes, and unknown action classes.
- Explicit provider adapter interface; no provider is registered by default.
- Optional NVIDIA NIM chat-completions adapter (`NVIDIA_NIM_API_KEY`, optional `NVIDIA_NIM_MODEL`), wired only when `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=nvidia_nim`, and `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true` are explicitly set.
- Constant-time comparison for bearer-token validation and fail-closed behavior when the API token is absent.
- Validated UUID-shaped `X-Correlation-ID` propagation: a valid caller-supplied value is echoed unchanged in `X-Correlation-ID` and stored as `details.correlation_id` on audit events. Invalid values are replaced with a server-generated UUID. Every response also carries a unique server-generated `X-Request-ID`, which is used as the audit-event `request_id`.
- Optional PyTorch availability check.
- Unit tests and GitHub Actions CI on Python 3.11 and 3.12.
- Container runs as a non-root user; CI builds the image without publishing it.
- Dependabot proposes weekly Python dependency and GitHub Actions updates.

## Request and correlation identifiers

`X-Correlation-ID` is a tracing/grouping value, not an authentication credential or idempotency key. The API trims the incoming header, accepts only a canonical UUID-shaped value, and echoes an accepted value byte-for-byte (including uppercase hex) in the response. A missing or invalid value is replaced by a server-generated UUID. The sanitized value is recorded separately as `details.correlation_id` on the audit event.

`X-Request-ID` is generated independently for each request, returned on every response, and stored as the audit event's `request_id`. Reusing the same valid `X-Correlation-ID` across related requests therefore never reuses the request ID or the audit key. Clients should use `X-Correlation-ID` to correlate related work and `X-Request-ID` to identify one specific server request.

## Quick start

Requires Python 3.11 or 3.12.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .
pytest
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. The `/health` endpoint reports process status separately from integrations that are not implemented. `/ready` returns HTTP 503 while required provider and database integrations remain unverified; this prevents a deployment orchestrator from mistaking a running process for a ready service. Current provider and database checks are `NOT VERIFIED`, not healthy.

## API access

The task endpoint is disabled unless `GLORIFIER_API_TOKEN` is configured. Set a strong, unique token in the deployment secret manager; never commit it to Git or paste it into chat. Send it as a bearer token in the Authorization header. The legacy `GLORIFIER_REQUIRE_API_TOKEN` flag cannot enable access when the token is missing.

Do not expose the service publicly without TLS, infrastructure-level request rate limits, monitoring, secret rotation, and an operational incident plan. The app applies a bounded, process-local limit of 60 authenticated task requests per client IP and bearer token per minute, returning HTTP 429 with `Retry-After`. Forwarded headers are not trusted. This is defense in depth only: counters are per process and reset on restart, so enforce distributed limits at the edge/reverse proxy before multi-instance or public production use.

## Explicit inference configuration

Inference remains disabled by default. To opt in to NVIDIA NIM, set `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=nvidia_nim`, `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`, and `NVIDIA_NIM_API_KEY` in the deployment secret manager. The egress flag is a separate privacy control: the task text is sent to NVIDIA NIM when inference runs, so enable it only for data approved for external processing. Optionally set `NVIDIA_NIM_MODEL`; the default is `meta/llama-3.1-8b-instruct`. Restart the service after changing environment variables. The API still applies action policy first, and requests requiring human approval do not reach the provider. Never put keys in requests, source files, logs, or chat. Unit tests mock provider calls and do not make live network requests. Live inference is **NOT VERIFIED** until an operator performs a controlled staging check.

## Database foundation

A PostgreSQL-compatible audit schema starter is in `db/supabase/migrations/0001_audit_events.sql`. It is **not applied automatically**. The API can write sanitized audit events only when `GLORIFIER_AUDIT_ENABLED=true` and `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` are configured. The `glorifier` schema must be exposed in Supabase API settings. If the initial audit write fails, task processing is blocked; if the final write fails, the API returns HTTP 503 and flags that audit status needs inspection. Do not enable this against production until the migration, schema exposure, access controls, backup, and staging test are reviewed. Review `db/README.md`. Neon remains unconfigured and unverified.

## Explicit limitations

- NVIDIA NIM is wired through explicit runtime configuration only. Unless `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=nvidia_nim`, and `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true` are all set, requests do not perform inference. A server-side API key is also required; live inference remains NOT VERIFIED until a controlled staging check succeeds.
- Neon has an optional, read-only connectivity probe. Install `.[neon]`, set `GLORIFIER_NEON_CONNECTIVITY_ENABLED=true` and `NEON_DATABASE_URL` in the deployment secret manager to make `/ready` run a bounded `SELECT 1` using certificate-verified TLS (`sslmode=verify-full`, system trust roots) and required channel binding. This does not create schemas or write data. The probe is disabled by default and is not proof of application-data readiness.
- No Supabase migration, Neon application-data schema, dual-write, or reconciliation is implemented.
- Supabase audit writes are opt-in through `GLORIFIER_AUDIT_ENABLED=true`, `SUPABASE_URL`, and server-side `SUPABASE_SERVICE_ROLE_KEY`; the API writes a sanitized pre-execution event before processing and a result event afterward. Audit persistence has not been verified against a live project.
- No autonomous financial actions, wallet signing, minting, or irreversible production changes are enabled.
- CI runs lint, tests, and a local Docker build; it does not deploy or publish an image.

## Status vocabulary

Use `FULLY VERIFIED`, `VERIFIED`, `PARTIALLY VERIFIED`, `NOT VERIFIED`, `DEGRADED`, and `NOT OBSERVABLE` only when backed by explicit checks and evidence. A healthy process is not proof that providers or databases are healthy. `NOT VERIFIED` indicates a known integration or capability has not been implemented or validated; `NOT OBSERVABLE` means the system lacks evidence to determine its state.

## Architecture

- `app/api.py`: API routes, authentication, and health reporting.
- `app/orchestrator.py`: policy-first orchestration shell.
- `app/policy.py`: deny-by-default action policy.
- `app/providers/base.py`: provider adapter contract.
- `app/neural/torch_status.py`: optional PyTorch status check.
- `tests/`: policy and API regression tests.
- `.github/workflows/ci.yml`: lint, tests, and Docker build on Python 3.11/3.12.
- `.github/dependabot.yml`: weekly dependency update proposals.
