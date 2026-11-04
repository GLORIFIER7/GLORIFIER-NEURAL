# GLORIFIER Neural Orchestration

A governed, provider-neutral AI orchestration API built with Python and FastAPI, deployed as a Cloudflare Python Worker. The latest live `/health` check confirms process liveness; `/ready` currently returns HTTP 503, so production dependency readiness is not fully verified. The latest structured failing smoke observation reported Neon as degraded. NVIDIA inference and optional audit/task-run persistence remain unverified or disabled.

## Current capabilities

- FastAPI liveness/status endpoint at `GET /health`.
- Evidence-based readiness endpoint at `GET /ready`: it returns HTTP 200 only after the explicitly enabled provider passes its read-only model-availability probe; missing or failed providers return HTTP 503. Neon connectivity is an optional, separately reported read-only check.
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

Open `http://127.0.0.1:8000/docs`. The `/health` endpoint reports process status separately from external dependencies. `/ready` performs a bounded read-only check against the explicitly configured provider; for NVIDIA NIM it queries `GET https://integrate.api.nvidia.com/v1/models` and requires the selected model ID to be present. This does not submit a prompt or execute inference. The optional Neon `SELECT 1` probe is reported separately and blocks readiness only when explicitly enabled but failing. With no provider configured, `/ready` remains HTTP 503.

## Cloudflare deployment

Neural is deployed as a dedicated Cloudflare Python Worker, not as a Railway service.
The Worker uses Cloudflare's Python runtime with the FastAPI ASGI entrypoint in
`cloudflare/worker.py` and the `python_workers` compatibility flag in
`cloudflare/wrangler.jsonc`. Before validation or deployment, the workflow runs
`cloudflare/prepare_worker.py` to stage the repository's `app/` package as a
local Python project under `cloudflare/neural_app/`. Pywrangler resolves that
local project dependency and vendors it into `cloudflare/python_modules/`, the
directory Cloudflare bundles for Python Workers. The workflow asserts that the
vendored package contains the API, Neon, and PyTorch adapter modules before
starting the Pyodide runtime.

The account's Workers subdomain is `glorifier`. The live Worker address is
`https://glorifier-neural.glorifier.workers.dev`. The Cloudflare deployment API
reported the latest deployment at `2026-11-04T13:24:33Z`, with 100% of production
traffic assigned to version `3481f2ac-2207-4b30-9858-32ad4bff8f0a` at the time
of inspection. Deployment success is not a readiness result; see **Current deployed
state** below.

The task endpoint reads `GLORIFIER_API_TOKEN` from the Cloudflare request-scoped
`env` binding. A secret binding with this name is present on the current production
Worker; its value is not read or stored in this repository or Wrangler configuration.
The endpoint remains protected by Cloudflare Access and bearer-token validation.

This Cloudflare runtime keeps provider inference, external data egress, Supabase audit
persistence, and Neon task-run writes disabled by default. Production binds the
read-only `NEON_READONLY` Hyperdrive and enables only the bounded `SELECT 1`
readiness probe; it performs no schema migration or application-data write.
NVIDIA inference remains disabled unless the provider, inference, and external-egress
controls are explicitly enabled. The current Cloudflare secret inventory contains a
binding named `NVIDIA_NIM_API_KEY`, but its value and validity are not observable from
the binding inventory. `/ready` currently returns HTTP 503; do not treat this as
provider-ready safe mode until the structured response confirms the expected database,
authentication, and rate-limit states. `/health` reports process liveness only.

Pull requests build the Worker bundle in dry-run mode. The connected Cloudflare
Workers Builds integration has also built and deployed `main` commits. The latest
Cloudflare deployment record observed during this audit was created through the
dashboard; it is reported above. Separately,
the **Cloudflare Neural Worker** GitHub Actions workflow retains a manual-only
`workflow_dispatch` deployment path, gated by `deploy=true` on `main` and the
`CLOUDFLARE_API_TOKEN` secret plus `CLOUDFLARE_ACCOUNT_ID` variable in the
`glorifier-neural-cloudflare-production` GitHub Environment. The most recent
production version was created by the connected Workers Builds/Wrangler path;
the GitHub Actions push run validated the bundle but skipped its manual deploy job.

## API access

The task endpoint is disabled unless `GLORIFIER_API_TOKEN` is configured. Set a strong, unique token in the deployment secret manager; never commit it to Git or paste it into chat. Send it as a bearer token in the Authorization header. The legacy `GLORIFIER_REQUIRE_API_TOKEN` flag cannot enable access when the token is missing.

Do not expose the service publicly without TLS, monitoring, secret rotation, and an operational incident plan. Local execution applies a bounded, process-local limit of 60 authenticated task requests per minute, keyed by a domain-separated HMAC-SHA-256 fingerprint of the bearer token; local counters reset on restart. Cloudflare Workers use the native `GLORIFIER_RATE_LIMITER` binding with a 60-request/60-second configuration and the same credential-keyed HMAC construction. Public `/ready` probes use a separate `GLORIFIER_READINESS_LIMITER` binding, limited to 10 requests per 60 seconds per Cloudflare client IP, and cache provider/database probe results for 30 seconds. Worker requests fail closed with HTTP 503 if the binding is missing or unavailable and return HTTP 429 when the binding denies a request. Cloudflare documents these counters as approximate and per-location, not a strict global quota; use a separately reviewed global coordination design if exact global quotas are required.

## Explicit inference configuration

Inference remains disabled by default. To opt in to NVIDIA NIM, set `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=nvidia_nim`, `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`, and `NVIDIA_NIM_API_KEY` in the deployment secret manager. The egress flag is a separate privacy control: the task text is sent to NVIDIA NIM when inference runs, so enable it only for data approved for external processing. Optionally set `NVIDIA_NIM_MODEL`; the default is `nvidia/nemotron-3.5-super-vl-120b-a12b`. Restart the service after changing environment variables. The API still applies action policy first, and requests requiring human approval do not reach the provider. Never put keys in requests, source files, logs, or chat. Unit tests mock provider calls and do not make live network requests. Live inference is **NOT VERIFIED** until an operator performs a controlled staging check.

## Current deployed state — observed 2026-11-04

The Cloudflare deployment API reported the latest `glorifier-neural` deployment at
`2026-11-04T13:24:33Z`, with 100% of production traffic assigned to version
`3481f2ac-2207-4b30-9858-32ad4bff8f0a` at inspection time. The Worker settings
inventory showed the `GLORIFIER_API_TOKEN` secret binding, the read-only
`NEON_READONLY` Hyperdrive binding, and both native rate-limit bindings. It also
showed a secret binding named `NVIDIA_NIM_API_KEY`; Cloudflare did not expose any
secret values, so credential validity is not verified.

Observed live checks:

- `GET /health`: HTTP 200; process liveness is verified only.
- `GET /ready`: HTTP 503 in the latest live probe. The current fetch returned the
  status code but not the structured response body, so the underlying readiness
  reason is not independently confirmed by that probe.
- The latest structured failing GitHub smoke observation (run
  [#41792456546](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41792456546))
  reported `providers: NOT VERIFIED`, `database: DEGRADED`,
  `authentication: VERIFIED`, `rate_limit: VERIFIED`, and
  `inference_performed: false`.
- Optional audit and task-run persistence remain unconfigured. No live inference
  request or model-quality verification has been performed.

Do not classify the current deployment as fully ready or as a verified safe-mode
release until a fresh structured readiness response confirms the database,
authentication, and rate-limit checks.

## Database foundation

A PostgreSQL-compatible audit schema starter is in `db/supabase/migrations/0001_audit_events.sql`. It is **not applied automatically**. The API can write sanitized audit events only when `GLORIFIER_AUDIT_ENABLED=true` and `SUPABASE_URL` plus `SUPABASE_SERVICE_ROLE_KEY` are configured. The `glorifier` schema must be exposed in Supabase API settings. If the initial audit write fails, task processing is blocked; if the final write fails, the API returns HTTP 503 and flags that audit status needs inspection. Do not enable this against production until the migration, schema exposure, access controls, backup, and staging test are reviewed. Review `db/README.md`. Production has the read-only `NEON_READONLY` Hyperdrive binding and a configured connectivity probe. The latest detailed failed smoke observation reported `database: DEGRADED`; a subsequent live anonymous `/ready` fetch returned HTTP 503 without exposing its JSON body. The asynchronous `asyncpg` Hyperdrive path uses a bounded 15-second connection timeout and executes only read-only `SELECT 1`; database readiness remains unverified until a new structured probe succeeds.

## Explicit limitations

- NVIDIA NIM is wired through explicit runtime configuration only. Unless `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=nvidia_nim`, and `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true` are all set, requests do not perform inference. A server-side API key is also required; live inference remains NOT VERIFIED until a controlled staging check succeeds.
- NVIDIA NIM readiness uses a bounded, authenticated `GET /v1/models` request and verifies the configured model ID is available. This proves model-catalog reachability only, not inference quality, latency, capacity, SLA, or factual correctness. Actual inference remains a separate controlled staging check. The NVIDIA key is used only server-side and readiness never sends task content.
- Neon has an optional, read-only connectivity probe. Install `.[neon]` for local execution (the Docker image includes this extra), set `GLORIFIER_NEON_CONNECTIVITY_ENABLED=true` and `NEON_DATABASE_URL` in the deployment secret manager to make `/ready` run a bounded `SELECT 1` using certificate-verified TLS (`sslmode=verify-full`, system trust roots) and required channel binding. This does not create schemas or write data. The probe is disabled by default and is not proof of application-data readiness. The audit database integration remains optional and must be separately verified before it is treated as operational.
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
