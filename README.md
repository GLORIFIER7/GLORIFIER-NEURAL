# GLORIFIER Neural Orchestration

A governed, provider-neutral AI orchestration API built with Python and FastAPI. This repository is an implementation starter, **not** a claim that any model provider, database, agent network, or production environment is connected.

## Current capabilities

- FastAPI health endpoint at `GET /health`.
- Task request/response schemas with input limits.
- Deny-by-default policy for financial actions, wallet signing, minting, destructive operations, and production writes.
- Explicit provider adapter interface; no provider is registered by default.
- Optional PyTorch availability check.
- Unit tests and GitHub Actions CI configuration.
- Container runs as a non-root user.

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

Open `http://127.0.0.1:8000/docs`. The `/health` endpoint reports process health separately from provider and database observability.

## API access

The task endpoint is disabled by default unless `GLORIFIER_API_TOKEN` is configured. Set a strong token in the deployment secret manager; never commit it to Git. Send it as a bearer token in the Authorization header. Do not expose the service publicly without TLS, request rate limits, monitoring, and an operational incident plan.

## Explicit limitations

- No OpenAI, Gemini, NVIDIA, OpenRouter, or other provider adapter is wired in.
- No Supabase or Neon connection, migration, dual-write, or reconciliation is implemented.
- No persistent audit database or customer billing is implemented.
- No autonomous financial actions, wallet signing, minting, or irreversible production changes are enabled.
- CI configuration has been committed, but passing checks must be confirmed from actual GitHub Actions runs.

## Status vocabulary

Use `FULLY VERIFIED`, `VERIFIED`, `PARTIALLY VERIFIED`, `NOT VERIFIED`, `DEGRADED`, and `NOT OBSERVABLE` only when backed by explicit checks and evidence. A healthy process is not proof that providers or databases are healthy.

## Architecture

- `app/api.py`: API routes and safe endpoint gating.
- `app/orchestrator.py`: policy-first orchestration shell.
- `app/policy.py`: deny-by-default action policy.
- `app/providers/base.py`: provider adapter contract.
- `app/neural/torch_status.py`: optional PyTorch status check.
- `tests/`: policy and API regression tests.
- `.github/workflows/ci.yml`: lint and test on Python 3.11/3.12.
