# GLORIFIER Neural Orchestration

A governed, provider-neutral AI orchestration API built with Python and FastAPI. This repository is an implementation starter, **not** a claim that any model provider, database, agent network, or production environment is connected.

## Current capabilities

- FastAPI liveness/status endpoint at `GET /health`.
- Fail-closed readiness endpoint at `GET /ready` (HTTP 503 until provider and database integrations are implemented and verified).
- Task request/response schemas with input limits, including a bounded action-class field.
- Deny-by-default policy for financial actions, wallet signing, minting, destructive operations, production writes, and unknown action classes.
- Explicit provider adapter interface; no provider is registered by default.
- Constant-time comparison for bearer-token validation and fail-closed behavior when the API token is absent.
- Optional PyTorch availability check.
- Unit tests and GitHub Actions CI on Python 3.11 and 3.12.
- Container runs as a non-root user; CI builds the image without publishing it.
- Dependabot proposes weekly Python dependency and GitHub Actions updates.

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

Do not expose the service publicly without TLS, infrastructure-level request rate limits, monitoring, secret rotation, and an operational incident plan. The app does not currently implement distributed rate limiting.

## Database foundation

A PostgreSQL-compatible audit schema starter is in `db/supabase/migrations/0001_audit_events.sql`. It is **not applied** and the API does not write to it yet. Review `db/README.md` for staging, backup, access-control, and data-handling requirements. Supabase and Neon connections remain unconfigured and unverified.

## Explicit limitations

- No OpenAI, Gemini, NVIDIA, OpenRouter, or other provider adapter is wired in; requests do not perform model inference.
- No Supabase or Neon connection, migration, dual-write, or reconciliation is implemented.
- No persistent audit database or customer billing is implemented.
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
