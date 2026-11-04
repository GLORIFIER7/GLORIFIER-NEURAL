# GLORIFIER Neural production readiness

This runbook describes the controls required before declaring the Cloudflare Worker production-ready.

## Deployment target

- Worker: `glorifier-neural`
- Public route: `https://glorifier-neural.glorifier.workers.dev`
- Runtime: Cloudflare Python Workers / FastAPI
- Database read probe: existing `NEON_READONLY` Hyperdrive binding
- Task-run writes: a separately provisioned `NEON_WRITE` binding or a writer `NEON_DATABASE_URL` secret
- Model: `nvidia/nemotron-3.5-super-vl-120b-a12b`

The Cloudflare deployment has two production paths. Cloudflare Workers Builds
automatically builds and deploys commits on `main`, using the `/cloudflare` root
and `bash ./worker-build.sh deploy`. The repository's
`.github/workflows/cloudflare-neural-worker.yml` also provides a separate manual
`workflow_dispatch` path, gated by `deploy=true` on `main`. Pull-request and
push runs in GitHub Actions validate or dry-run only; they do not deploy production.

The feature-branch Workers Builds configuration for this PR is separately scoped
to its branch, runs from `/cloudflare`, prepares the package with
`bash ./worker-build.sh --prepare-only`, and runs
`npx wrangler deploy --dry-run`. Its `previews_enabled` flag is false, so it
does not publish a Preview or production version. The main-branch production build
configuration remains unchanged.

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

Live check on 2026-11-04: `GET /health` returned HTTP 200 and process status `VERIFIED`. The latest rerun of the production smoke job (run [#41792456546](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41792456546), 13:33:52Z) returned HTTP 503 from `/ready` with `providers: NOT VERIFIED`, `database: VERIFIED`, `authentication: VERIFIED`, `rate_limit: VERIFIED`, and `inference_performed=false`. The smoke job passed the strict provider-disabled safe-mode branch. This is deployed safe mode, not provider readiness.

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

The production Worker currently has the `glorifier-neon-readonly` Hyperdrive resource bound as `NEON_READONLY`. It is used only for the read-only `SELECT 1` readiness probe and must not be used for writes. The latest structured production smoke rerun reported `database: VERIFIED`; the HTTP 503 readiness status was due to `providers: NOT VERIFIED` while inference was disabled. The probe remains read-only and does not verify application-data reads/writes. No writer-role `NEON_WRITE` binding is configured, and task-run persistence remains disabled.

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

The post-deploy smoke job requires HTTP 200 from `/health` and accepts either provider-ready HTTP 200 from `/ready`, or the strict provider-disabled safe-mode HTTP 503 response when the database, authentication, and rate-limit checks are verified and `inference_performed=false`. It performs no inference and does not incur a model completion request. The latest production smoke rerun met the strict provider-disabled safe-mode branch: database, authentication, and rate-limit checks were VERIFIED, with `inference_performed=false`. Retain HTTP 503 as the correct non-provider-ready status until provider readiness is configured and verified.

## Rate limiting

The Worker uses the Cloudflare-native `GLORIFIER_RATE_LIMITER` binding with a configured limit of 60 requests per 60-second window, keyed by an HMAC-SHA-256 digest of the bearer token. Cloudflare's native Workers rate-limit counters are approximate and per-location, not a strict global quota. Do not represent this as globally exact enforcement.

## Current production observation — 2026-11-04

- Latest Cloudflare deployment record observed at `2026-11-04T13:24:33Z`; source was the dashboard and 100% of production traffic was assigned to version `3481f2ac-2207-4b30-9858-32ad4bff8f0a`.
- `/health`: HTTP 200 with overall status `PARTIALLY VERIFIED`; process check `VERIFIED`. The endpoint does not perform dependency-readiness checks, so provider/database/PyTorch remain `NOT VERIFIED` in that response.
- `/ready`: HTTP 503 because provider readiness is `NOT VERIFIED`.
- The successful smoke rerun (run [#41792456546](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41792456546), 13:33:52Z) reported database `VERIFIED`, authentication `VERIFIED`, rate limit `VERIFIED`, providers `NOT VERIFIED`, and `inference_performed=false`; the strict provider-disabled safe-mode branch passed.
- Cloudflare settings expose a `GLORIFIER_API_TOKEN` secret binding and a secret binding named `NVIDIA_NIM_API_KEY`. Secret values and credential validity are not observable from the binding inventory.
- Provider inference remains unverified; optional audit and task-run persistence are not configured.

## Release procedure

1. Make code changes on a branch and open a pull request. The active repository ruleset requires one approving review, CodeQL/code-scanning and code-quality constraints, and prohibits deletion and non-fast-forward updates.
2. Require the repository's CI, security checks, and Cloudflare dry-run validation to pass. Do not bypass the active ruleset or weaken quality thresholds to obtain a green result.
3. After an approved merge to `main`, verify the automatic Cloudflare Workers Builds production build and active deployment. The separate GitHub Actions path can be manually dispatched with `deploy=true` using the configured GitHub Environment credentials. Verify the deployment job and intended Worker version/traffic before announcing release.
4. Require live `/health` and `/ready` checks. A 503 is acceptable only for the explicit provider-disabled safe-mode response when database, authentication, and rate-limit controls are verified and `inference_performed=false`; it is not evidence of provider readiness.
5. Separately perform a controlled authenticated inference request only after the owner provisions a valid NVIDIA key, approves sending task content to NVIDIA, and approves any applicable usage charges. The automated readiness/smoke steps intentionally do not submit a prompt.

Do not declare full AI production readiness until provider model-catalog readiness and a separately controlled inference check succeed. Enable audit writes or task-run persistence only after their own schema, least-privilege credentials, backup, and read/write verification steps have been approved and completed.
