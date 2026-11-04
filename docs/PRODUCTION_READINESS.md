# GLORIFIER Neural production readiness

This runbook describes the controls required before declaring the Cloudflare Worker production-ready.

## Deployment target

- Worker: `glorifier-neural`
- Public route: `https://glorifier-neural.glorifier.workers.dev`
- Runtime: Cloudflare Python Workers / FastAPI
- Database read probe: existing `NEON_READONLY` Hyperdrive binding
- Task-run writes: a separately provisioned `NEON_WRITE` binding or a writer `NEON_DATABASE_URL` secret
- Model: `nvidia/nemotron-3.5-super-vl-120b-a12b`

The Cloudflare deployment is managed by `.github/workflows/cloudflare-neural-worker.yml`. Production deployment remains a manual `workflow_dispatch` with `deploy=true` on `main`. Pull requests never deploy production.

## GitHub deployment environment

The `glorifier-neural-cloudflare-production` GitHub Environment must define:
- Secret: `CLOUDFLARE_API_TOKEN` with permission to deploy this Worker.
- Variable: `CLOUDFLARE_ACCOUNT_ID` identifying the intended Cloudflare account.

The workflow fails closed when either value is absent. The account identifier is supplied at deployment time and is not committed to the repository.

## Cloudflare Access

The account-wide `All Workers` Access application remains enabled and still protects Neural task execution. A separate application named `GLORIFIER Neural Public Readiness Probes` has been created with narrowly scoped public destinations for only:

- `GET /health`
- `GET /ready`

These read-only operational routes bypass the account-wide Access gate so monitoring and the post-deploy smoke job can reach them. The task endpoint `POST /v1/tasks` is not included in the bypass; it remains behind account-wide Access and also requires `GLORIFIER_API_TOKEN`. Public `GET /ready` is protected by a separate Cloudflare-native per-client rate limiter and a 30-second cache for provider/database probes. Do not broaden this exception to all Worker paths or disable the existing `All Workers` policy.

Live check after this Access change: `GET /health` returns HTTP 200 JSON. `GET /ready` currently returns HTTP 503 JSON because provider inference is not enabled/configured on the deployed `main` version.

## Cloudflare variables and secrets

Configure the following in Workers & Pages → `glorifier-neural` → Settings → Variables and Secrets. Do not put secret values in Git, this document, issue comments, or chat.

### Required secret

- `GLORIFIER_API_TOKEN`: a high-entropy bearer token used by authenticated `POST /v1/tasks` callers.

### NVIDIA inference

Set these plain-text variables only when the owner explicitly authorizes sending task prompts to NVIDIA:

- `GLORIFIER_ENABLE_INFERENCE=true`
- `GLORIFIER_PROVIDER=nvidia_nim`
- `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`
- `NVIDIA_NIM_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b`

Store the NVIDIA credential as a Worker secret:

- `NVIDIA_NIM_API_KEY`

The readiness probe performs a read-only `GET /v1/models` request. It does not submit a prompt or run inference. The documented NVIDIA model ID is not proof that the user's API credential or hosted endpoint is enabled; that must be verified against the deployed Worker.

### Neon task-run writes (optional)

The PR branch Wrangler configuration binds the existing `glorifier-neon-readonly` Hyperdrive resource as `NEON_READONLY`. It is intended only for a read-only `SELECT 1` readiness probe and must not be used for writes. This binding is not active on the deployed `main` Worker until the integration PR #33 is merged and its gated deployment is run.

To enable task-run persistence:

1. Apply `db/neon/migrations/0001_task_runs.sql` to the intended Neon database through the database owner's approved migration process. The SQL file is marked proposal-only and must not be applied without that separate approval.
2. Provision a separate writer-role Hyperdrive configuration and bind it as `NEON_WRITE`, or provide `NEON_DATABASE_URL` as a Cloudflare Worker secret for a dedicated least-privilege writer role.
3. Set `GLORIFIER_NEON_TASK_RUNS_ENABLED=true`.

Task-run persistence stores only validated lifecycle metadata and evidence codes. It does not store prompts, outputs, credentials, wallet data, or payment data. A successful task-run write is committed and read back before the API returns success.

### Supabase audit sink (optional)

To enable the REST audit sink:

- Set `GLORIFIER_AUDIT_ENABLED=true`.
- Store `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as Worker secrets.

Audit writes use the Cloudflare Fetch API and fail closed when explicitly enabled but unavailable.

## Readiness semantics

`GET /health` confirms process health only. It is not a production-ready signal.

`GET /ready` performs read-only/configuration checks. For Cloudflare Workers it requires:

- Provider readiness verified against the selected NVIDIA model catalogue.
- Neon connectivity verified through `NEON_READONLY`.
- `GLORIFIER_API_TOKEN` configured.
- The `GLORIFIER_RATE_LIMITER` and `GLORIFIER_READINESS_LIMITER` bindings present.

Optional audit and task-run integrations report their configuration state separately. Their write paths are not tested by readiness. A post-execution persistence failure is returned as a degraded evidence marker alongside the completed task outcome, not as a retryable HTTP 503.

The post-deploy smoke job requires HTTP 200 from `/health` and `/ready`, and verifies the provider, database, authentication, and rate-limit checks. It performs no inference and therefore does not incur a model completion request.

## Rate limiting

The Worker uses the Cloudflare-native `GLORIFIER_RATE_LIMITER` binding with a configured limit of 60 requests per 60-second window, keyed by an HMAC-SHA-256 digest of the bearer token. Cloudflare's native Workers rate-limit counters are approximate and per-location, not a strict global quota. Do not represent this as globally exact enforcement.

## Release procedure

1. Review and merge integration PR #33 only after all required code, security, and workflow checks have final passing outcomes and a human has reviewed the diff.
2. Configure the required Cloudflare/GitHub Environment values and review the read-only Hyperdrive/rate-limit bindings.
3. Run the Cloudflare Neural Worker workflow manually on `main` with `deploy=true`.
4. Require the post-deploy health and readiness smoke checks to pass.
5. Separately perform a controlled authenticated inference request only after approving external data egress and any applicable NVIDIA API usage. The automated readiness/smoke steps intentionally do not perform inference.

Do not declare production verified until the live smoke checks pass and a controlled inference, authentication, audit-write (when enabled), and task-run write/read-back (when enabled) have been observed in the deployed environment.
