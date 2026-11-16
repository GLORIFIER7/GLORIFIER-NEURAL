# GLORIFIER Neural production readiness

This runbook describes the controls required before declaring the Cloudflare Worker production-ready.

## Deployment target

- Worker: `glorifier-neural`
- Public route: `https://glorifier-neural.glorifier.workers.dev`
- Runtime: Cloudflare Python Workers / FastAPI
- Database read probe: existing `NEON_READONLY` Hyperdrive binding
- Task-run writes: a separately provisioned `NEON_WRITE` binding or a writer `NEON_DATABASE_URL` secret
- Currently selected production provider: OpenAI Responses API. The adapter defaults to model `gpt-6-luna` unless `OPENAI_MODEL` overrides it. NVIDIA NIM remains an optional alternative provider, not the current production selection.

The Cloudflare deployment has one repository-managed production-promotion
path. As of 2026-11-10, the Cloudflare Workers Builds trigger remains attached to
`main` for package preparation, but its production command is
`bash ./worker-build.sh --prepare-only`. That mode prepares the Worker package
and exits before invoking Wrangler; it does not upload or promote a Worker version.
The repository's `.github/workflows/cloudflare-neural-worker.yml` is the
production-promotion path and requires a manual `workflow_dispatch`, gated by
`deploy=true` on `main` and the protected
`glorifier-neural-cloudflare-production` environment. Pull-request and ordinary
push runs in GitHub Actions validate or dry-run only; they do not deploy production.

The branch-specific Workers Builds triggers used for Dependabot PRs #38, #39, and
#40 are separately scoped to their respective branches. They now run from
`/cloudflare`, prepare the Worker package with
`bash ./worker-build.sh --prepare-only`, and run
`npx wrangler deploy --dry-run`. All three corrected builds completed successfully
and stopped at `--dry-run`; they published neither a Preview nor a production
version. Worker preview URLs remain disabled in `cloudflare/wrangler.jsonc`. The
main-branch Workers Builds trigger remains enabled for validation-only package
preparation; its deploy command was read back as
`bash ./worker-build.sh --prepare-only` on 2026-11-10. The preview command
remains `npx wrangler preview` and was not changed. This is configuration
evidence, not production-deployment evidence.

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

Historical safe-mode observation (2026-11-04; superseded by the current production observation below): `GET /health` returned HTTP 200 and process status `VERIFIED`. The production smoke job (run [#41792456546](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41792456546), 13:33:52Z) returned HTTP 503 from `/ready` with `providers: NOT VERIFIED`, `database: VERIFIED`, `authentication: VERIFIED`, `rate_limit: VERIFIED`, and `inference_performed=false`. That run passed the strict provider-disabled safe-mode branch. This records the earlier non-provider-ready state only; it is not the current production readiness result.

## Cloudflare variables and secrets

Configure the following in Workers & Pages → `glorifier-neural` → Settings → Variables and Secrets. Do not put secret values in Git, this document, issue comments, or chat.

### Required secret

- `GLORIFIER_API_TOKEN`: a high-entropy bearer token used by authenticated `POST /v1/tasks` callers.
- `GLORIFIER_INTERNAL_SERVICE_TOKEN`: a separate high-entropy credential used only by the internal GLORIFIER-to-NEURAL service-verification path. Keep it distinct from `GLORIFIER_API_TOKEN`; never publish either value.

### OpenAI (currently selected production provider)

The observed production Worker is configured with `GLORIFIER_PROVIDER=openai`.
Its read-only model-access probe uses `GET /v1/models/{model}`; the adapter
defaults to `gpt-6-luna` unless `OPENAI_MODEL` is explicitly set.

For read-only provider readiness, configure:

- `GLORIFIER_PROVIDER=openai`
- `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`
- Store `OPENAI_API_KEY` as a Worker secret.

Read-only readiness does not authorize task inference. Only after the owner separately approves prompt transmission and applicable provider charges, task inference also requires:

- `GLORIFIER_ENABLE_INFERENCE=true`
- `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true`

Keep the paid-inference authorization false in the zero-budget default.

A direct Cloudflare settings read-back on 2026-11-05 at approximately 16:28 (UTC+07:00) confirmed `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=openai`, and `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`. The `OPENAI_API_KEY` binding name is present; its value was not read. This is configuration evidence only. The latest production smoke performed read-only readiness checks and explicitly reported `inference_performed=false`; it did not submit a prompt or verify a live completion. Authenticated task requests can send prompt content to OpenAI and incur separate API usage charges. Current source also requires the independent, default-false `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true` gate in addition to inference enablement and external-egress consent; a historical production flag snapshot does not prove that the new source guard has been deployed. A successful model-catalogue check establishes model access only; it does not prove inference quality, latency, capacity, or end-to-end task execution.

### NVIDIA NIM (optional alternative provider)

Set these plain-text variables only when the owner explicitly authorizes sending task prompts to NVIDIA:

- `GLORIFIER_ENABLE_INFERENCE=true`
- `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true` (separate owner approval for paid inference; otherwise keep it `false`)
- `GLORIFIER_PROVIDER=nvidia_nim`
- `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`
- `NVIDIA_NIM_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b`

Store the NVIDIA credential as a Worker secret:

- `NVIDIA_NIM_API_KEY`

The readiness probe performs a read-only `GET /v1/models` request. It does not submit a prompt or run inference. The documented NVIDIA model ID is not proof that the user's API credential or hosted endpoint is enabled; that must be verified against the deployed Worker.

### Gemini Interactions API (optional alternative provider)

The service supports Gemini through Google's recommended Interactions API. The default model is `gemini-3.8-flash`; override it with `GEMINI_MODEL` when required by the account.

Configure the following only after the owner has supplied a valid Gemini API key:

- Set `GLORIFIER_PROVIDER=gemini`.
- Explicitly set `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true` at deployment time to permit provider readiness and external requests; the tracked Worker configuration defaults this switch to `false`.
- Separately set `GLORIFIER_ENABLE_INFERENCE=true` only after an authorized inference test is approved; the tracked Worker configuration defaults this switch to `false`.
- Separately set `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true` only after the owner explicitly approves paid task inference; the tracked Worker configuration defaults this switch to `false`.
- Store `GEMINI_API_KEY` as a Cloudflare Worker secret.
- Optionally set `GEMINI_MODEL`; the default is `gemini-3.8-flash`.

Readiness uses a read-only `GET /v1beta/models/{model}` request and does not submit a prompt. Inference uses `POST /v1beta/interactions` with `store=false`, bounded output tokens, disabled redirects, a request deadline, and sanitized errors. This makes requests stateless at the Gemini Interactions resource layer; it does not replace Google's applicable service data-processing terms or billing controls.

### Anthropic Claude Messages API (optional alternative provider)

The service supports Claude through Anthropic's Messages API. The default model is `claude-sonnet-5`; override it with `ANTHROPIC_MODEL` when required by the account.

Configure the following only after the owner has supplied a valid Anthropic API key:

- Set `GLORIFIER_PROVIDER=anthropic`.
- Explicitly set `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true` at deployment time to permit provider readiness and external requests; the tracked Worker configuration defaults this switch to `false`.
- Separately set `GLORIFIER_ENABLE_INFERENCE=true` only after an authorized inference test is approved; the tracked Worker configuration defaults this switch to `false`.
- Separately set `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true` only after the owner explicitly approves paid task inference; the tracked Worker configuration defaults this switch to `false`.
- Store `ANTHROPIC_API_KEY` as a Cloudflare Worker secret.
- Optionally set `ANTHROPIC_MODEL`; the default is `claude-sonnet-5`.

Readiness uses the read-only `GET /v1/models/{model_id}` endpoint and does not submit a message. Inference uses `POST /v1/messages` with a bounded `max_tokens`, the pinned `anthropic-version` header, disabled redirects, a request deadline, and sanitized errors. Requests may incur Anthropic API usage charges.

These adapters are explicit alternatives, not automatic multi-provider failover. Only the provider named by `GLORIFIER_PROVIDER` is registered in the runtime. No provider is switched automatically when another provider is unavailable. Keep the deployed provider on its current selection until the selected provider's secret binding, read-only readiness, and a separately authorized inference test have been verified.

### Neon task-run writes (optional)

The production Worker currently has the `glorifier-neon-readonly` Hyperdrive resource bound as `NEON_READONLY`. It is used only for the read-only `SELECT 1` readiness probe and must not be used for writes. The direct live `/ready` check on 2026-11-05 returned HTTP 200 with `status: READY` and `database: VERIFIED`; the Hyperdrive probe is read-only and does not test application-data writes. The probe remains read-only and does not verify application-data reads/writes. No writer-role `NEON_WRITE` binding is configured, and task-run persistence remains disabled.

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

- Provider readiness verified through the selected provider adapter's bounded, read-only model-access probe: OpenAI uses `GET /v1/models/{model}`; Gemini uses `GET /v1beta/models/{model}`; Anthropic uses `GET /v1/models/{model_id}`; NVIDIA NIM uses its read-only model catalogue probe.
- Neon connectivity verified through `NEON_READONLY`.
- `GLORIFIER_API_TOKEN` configured.
- The `GLORIFIER_RATE_LIMITER` and `GLORIFIER_READINESS_LIMITER` bindings present.

Optional audit and task-run integrations report their configuration state separately. Their write paths are not tested by readiness. A post-execution persistence failure is returned as a degraded evidence marker alongside the completed task outcome, not as a retryable HTTP 503.

The post-deploy smoke job requires HTTP 200 from `/health` and accepts either (a) HTTP 200 from `/ready` when the selected provider, database, authentication, and rate-limit checks pass, or (b) the strict provider-disabled safe-mode HTTP 503 response when database, authentication, and rate-limit checks pass and `inference_performed=false`. It performs no inference and does not incur a model completion request. The 2026-11-05 HTTP 200 /ready result and its configuration snapshot are historical only. They are superseded by the read-only 2026-11-16 configuration snapshot below: external egress, inference, and paid-inference authorization are all false. No prompt was submitted. Treat any subsequent readiness result as unverified until a fresh probe is recorded.

## Rate limiting

The Worker uses the Cloudflare-native `GLORIFIER_RATE_LIMITER` binding with a configured limit of 60 requests per 60-second window. Its HMAC-SHA-256 key is derived from the bearer token plus the normalized client identity (`CF-Connecting-IP` on Workers, or the client host locally), so separate clients using the same token receive separate buckets. Cloudflare's native Workers rate-limit counters are approximate and per-location, not a strict global quota. Do not represent this as globally exact enforcement.

## Historical production observation — 2026-11-05 (UTC+07:00; superseded 2026-11-16)

Direct Cloudflare configuration inventory was read at approximately 16:28 local time. The latest deployment inventory returned:

- Worker: `glorifier-neural`; route: `https://glorifier-neural.glorifier.workers.dev`.
- Latest deployment: `77cace04-8c1b-4a26-82b6-b4504f920625`, created `2026-11-05T07:30:11.656407Z`; 100% traffic assigned to version `ecf822d5-745e-4c33-8fc2-5c10ca83baf7`.
- Current non-secret Worker variables: `GLORIFIER_PROVIDER=openai`, `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`, `GLORIFIER_ENABLE_INFERENCE=true`, and `GLORIFIER_NEON_CONNECTIVITY_ENABLED=true`.
- Secret-binding inventory includes `OPENAI_API_KEY`, `GLORIFIER_API_TOKEN`, and `NVIDIA_NIM_API_KEY`. Only binding names were inspected; secret values were not read.
- The latest successful production smoke was GitHub Actions run [#41987341798](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41987341798), around `2026-11-05T07:30Z`. It confirmed `/health` HTTP 200 and `/ready` HTTP 200 with `status: READY`; provider, database connectivity, authentication, and rate limiting were `VERIFIED`.
- That smoke response reported `inference_performed=false`. No prompt was submitted and no model inference was executed.
- Audit and task-run persistence remain `NOT CONFIGURED (OPTIONAL)`; no optional persistence write was tested.

Historical conclusion as of 2026-11-05 only: Cloudflare deployment and the configured read-only production readiness checks were reported VERIFIED at that observation time. This is not the current configuration state; see the superseding 2026-11-16 observation below.
## Current production observation — 2026-11-16

Read-only Cloudflare Worker settings were retrieved between 2026-11-16T06:26:29Z and 2026-11-16T06:27:45Z (UTC). This is configuration evidence only; it does not establish a successful provider request or task execution.

### NEURAL Worker configuration

The glorifier-neural Worker reported these plain-text variables:

- GLORIFIER_PROVIDER=openai
- GLORIFIER_NEON_CONNECTIVITY_ENABLED=true
- GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=false
- GLORIFIER_ENABLE_INFERENCE=false
- GLORIFIER_PAID_INFERENCE_AUTHORIZED=false

The secret-binding inventory included GLORIFIER_API_TOKEN, GLORIFIER_INTERNAL_SERVICE_TOKEN, NVIDIA_NIM_API_KEY, and OPENAI_API_KEY. Only binding names were inspected; secret values were not read.

### Observability privacy configuration

A read-only script-settings read between 2026-11-16T06:27:42Z and 2026-11-16T06:27:45Z reported observability.redact_query_string=false for both glorifier and glorifier-neural. Their persisted logs and traces therefore do not yet have query-string redaction enabled at the Worker-settings layer. Main GLORIFIER PR #894 adds redact_query_string: true to both tracked Wrangler configs and regression tests. It is a source-only proposal and has not been deployed; the live setting remains false until a reviewed deployment and fresh read-back confirm otherwise.

The earlier 2026-11-05 GLORIFIER_ENABLE_INFERENCE=true and GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true values are superseded by this 2026-11-16 observation. Keep external egress, inference, and paid-inference authorization disabled. Do not send prompts, trigger provider inference, or execute tasks merely to make /ready return HTTP 200. A same-day earlier unauthenticated probe recorded process liveness as partially verified and /ready HTTP 503; that probe is not a substitute for a new health/readiness check.

### Current repository governance — 2026-11-16

The live NEURAL main-branch ruleset 27086549 is active and requires strict successful checks test (3.11) and test (3.12), signed commits, and resolved review threads. It has zero required approving reviews, an empty bypass_actors list, and the connected principal reports current_user_can_bypass: never. The AI Review Policy status is advisory only and is not a required status check.

The ruleset's code-owner-review setting is enabled, but no CODEOWNERS file was found at the repository root, .github/CODEOWNERS, or docs/CODEOWNERS on the current branch. Path-level code-owner coverage is NOT VERIFIED until an administrator adds and validates an ownership map. Do not treat the enabled ruleset flag as proof that a code owner is assigned.

## Release procedure

1. Open a pull request and inspect the active ruleset before release. For NEURAL, ruleset ID 27086549 requires the exact current-head CI contexts test (3.11) and test (3.12), signed commits, and review-thread resolution; its code-owner review and review-thread resolution settings are enabled. However, no supported CODEOWNERS file was found, so effective path-level code-owner coverage is NOT VERIFIED. The AI Review Policy diagnostic is advisory only, not a required merge status. For primary GLORIFIER, ruleset ID 24038955 currently has no required-status-check rule and its bypass list includes always-bypass actors; an administrator must review that risk. Do not bypass either ruleset or weaken checks.
2. Require CI, dependency/security checks, and Cloudflare Worker dry-run validation to pass on the exact immutable PR head. Do not count skipped jobs, historical results, or checks from an older commit as current evidence.
3. After an approved merge to main, use the protected .github/workflows/neural-cloudflare-worker.yml workflow with a manual workflow_dispatch and deploy=true from main through the glorifier-neural-cloudflare-production environment. The main-branch Workers Builds trigger is validation-only (--prepare-only); it is not a production release. Verify the deployment job, exact active Worker version, traffic allocation, and service bindings before announcing a release.
4. Verify live /health and /ready endpoints after deployment. Interpret HTTP 503 as non-ready; accept the documented provider-disabled safe-mode response only as evidence that the fail-closed path works, not as provider-ready or production-ready. Record provider, database, authentication, and rate-limit signals separately.
5. Keep GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=false, GLORIFIER_ENABLE_INFERENCE=false, and GLORIFIER_PAID_INFERENCE_AUTHORIZED=false unless the owner separately authorizes prompt transmission and any applicable provider charges. Readiness probes are read-only and are not evidence of inference. Do not submit a prompt or perform an authenticated task without that separate authorization.

## CI dependency maintenance

### Disposable PostgreSQL image digest

The disposable PostgreSQL service in .github/workflows/database-integration.yml is pinned to postgres:16@sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9. Treat this digest as an explicit dependency that needs a manual refresh during the monthly dependency review; do not assume the existing .github/dependabot.yml entries update service-container image digests inside workflow YAML.

When refreshing it, verify the official PostgreSQL 16 image and selected immutable digest, update the service image in .github/workflows/database-integration.yml, update the exact expected digest in tests/test_ci_workflow_security.py, run the focused CI security test module, then run the disposable PostgreSQL migration workflow on the proposed branch. Keep the major version at 16 unless a separate compatibility review authorizes a major-version upgrade.
