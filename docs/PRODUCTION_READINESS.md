# GLORIFIER Neural production readiness

This runbook describes the controls required before declaring the Cloudflare Worker production-ready.

> **Evidence freshness — 2026-11-12:** Current production provider selection, Worker deployment/version/traffic, external-egress setting, inference flag, database connectivity, secret-binding presence, and live readiness are **NOT VERIFIED**. The Cloudflare inventories and smoke results dated 2026-11-05 below are historical snapshots, not current production read-backs. Configuration examples describe intended controls; they do not assert that those values are currently deployed.

## Deployment target

- Worker: `glorifier-neural`
- Public route: `https://glorifier-neural.glorifier.workers.dev`
- Runtime: Cloudflare Python Workers / FastAPI
- Database read probe: existing `NEON_READONLY` Hyperdrive binding
- Task-run writes: a separately provisioned `NEON_WRITE` binding or a writer `NEON_DATABASE_URL` secret
- Historical production-provider observation (2026-11-05): OpenAI Responses API. The adapter defaults to model `gpt-6-luna` unless `OPENAI_MODEL` overrides it. The current deployed provider selection is **NOT VERIFIED**.

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

Historical safe-mode observation (2026-11-04; superseded by the historical 2026-11-05 observation below, which is also not current production evidence): `GET /health` returned HTTP 200 and process status `VERIFIED`. The production smoke job (run [#41792456546](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41792456546), 13:33:52Z) returned HTTP 503 from `/ready` with `providers: NOT VERIFIED`, `database: VERIFIED`, `authentication: VERIFIED`, `rate_limit: VERIFIED`, and `inference_performed=false`. That run passed the strict provider-disabled safe-mode branch. This records the earlier non-provider-ready state only; it is not the current production readiness result.

## Cloudflare variables and secrets

Configure the following in Workers & Pages → `glorifier-neural` → Settings → Variables and Secrets. Do not put secret values in Git, this document, issue comments, or chat.

### Required secret

- `GLORIFIER_API_TOKEN`: a high-entropy bearer token used by authenticated `POST /v1/tasks` callers.
- `GLORIFIER_INTERNAL_SERVICE_TOKEN`: a separate high-entropy credential used only by the internal GLORIFIER-to-NEURAL service-verification path. Keep it distinct from `GLORIFIER_API_TOKEN`; never publish either value.

### OpenAI (optional provider; current production selection NOT VERIFIED)

The historical 2026-11-05 observation recorded `GLORIFIER_PROVIDER=openai`. The current deployed provider selection is **NOT VERIFIED**.
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

A historical Cloudflare settings read-back on 2026-11-05 at approximately 16:28 (UTC+07:00) recorded `GLORIFIER_ENABLE_INFERENCE=true`, `GLORIFIER_PROVIDER=openai`, and `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`. The `OPENAI_API_KEY` binding name was present in that dated inventory; its value was not read. This is historical configuration evidence only. The 2026-11-05 production smoke performed read-only readiness checks and explicitly reported `inference_performed=false`; it did not submit a prompt or verify a live completion. Authenticated task requests can send prompt content to OpenAI and incur separate API usage charges. Current source also requires the independent, default-false `GLORIFIER_PAID_INFERENCE_AUTHORIZED=true` gate in addition to inference enablement and external-egress consent; a historical production flag snapshot does not prove that the new source guard has been deployed. A successful model-catalogue check establishes model access only; it does not prove inference quality, latency, capacity, or end-to-end task execution.

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

These adapters are explicit alternatives, not automatic multi-provider failover. Only the provider named by `GLORIFIER_PROVIDER` is registered in the runtime. No provider is switched automatically when another provider is unavailable. Do not infer or change the deployed provider selection from this historical documentation; first obtain a fresh authorized read-back of the provider setting and secret-binding presence, then separately verify read-only readiness and obtain authorization for any inference test.

### Neon task-run writes (optional)

The historical 2026-11-05 production inventory recorded the `glorifier-neon-readonly` Hyperdrive resource bound as `NEON_READONLY`. Current binding presence is **NOT VERIFIED**. When configured, this binding is intended only for the read-only `SELECT 1` readiness probe and must not be used for writes. The `/ready` check on 2026-11-05 returned HTTP 200 with `status: READY` and `database: VERIFIED`; that read-only probe did not test application-data reads or writes. Current database connectivity, writer-role `NEON_WRITE` binding presence, and task-run persistence state are **NOT VERIFIED**.

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

The post-deploy smoke job requires HTTP 200 from `/health` and accepts either (a) HTTP 200 from `/ready` when the selected provider, database, authentication, and rate-limit checks pass, or (b) the strict provider-disabled safe-mode HTTP 503 response when database, authentication, and rate-limit checks pass and `inference_performed=false`. It performs no inference and does not incur a model completion request. The most recent production smoke recorded in this runbook is dated 2026-11-05 and followed branch (a): `/ready` returned HTTP 200 with `status: READY`. The 2026-11-04 HTTP 503 result above is also historical. A same-day Cloudflare settings read-back recorded the production inference flag as `true`, but the smoke still performed no inference. These observations do not establish the currently deployed configuration or current readiness response. Current deployment, configuration, and readiness remain **NOT VERIFIED** until a fresh authorized read-back. An HTTP 503 is a fail-closed non-ready/safe-mode result, not proof of provider readiness.

## Rate limiting

The Worker uses the Cloudflare-native `GLORIFIER_RATE_LIMITER` binding with a configured limit of 60 requests per 60-second window. Its HMAC-SHA-256 key is derived from the bearer token plus the normalized client identity (`CF-Connecting-IP` on Workers, or the client host locally), so separate clients using the same token receive separate buckets. Cloudflare's native Workers rate-limit counters are approximate and per-location, not a strict global quota. Do not represent this as globally exact enforcement.

## Historical production observation — 2026-11-05 (UTC+07:00)

Direct Cloudflare configuration inventory was read at approximately 16:28 local time. The deployment inventory returned at that time:

- Worker: `glorifier-neural`; route: `https://glorifier-neural.glorifier.workers.dev`.
- Deployment observed on 2026-11-05: `77cace04-8c1b-4a26-82b6-b4504f920625`, created `2026-11-05T07:30:11.656407Z`; the inventory then reported 100% traffic assigned to version `ecf822d5-745e-4c33-8fc2-5c10ca83baf7`.
- Non-secret Worker variables observed in the 2026-11-05 inventory: `GLORIFIER_PROVIDER=openai`, `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=true`, `GLORIFIER_ENABLE_INFERENCE=true`, and `GLORIFIER_NEON_CONNECTIVITY_ENABLED=true`.
- Secret-binding inventory includes `OPENAI_API_KEY`, `GLORIFIER_API_TOKEN`, and `NVIDIA_NIM_API_KEY`. Only binding names were inspected; secret values were not read.
- The successful production smoke recorded in this historical observation was GitHub Actions run [#41987341798](https://github.com/GLORIFIER7/GLORIFIER-NEURAL/actions/runs/41987341798), around `2026-11-05T07:30Z`. It confirmed `/health` HTTP 200 and `/ready` HTTP 200 with `status: READY`; provider, database connectivity, authentication, and rate limiting were `VERIFIED`.
- That smoke response reported `inference_performed=false`. No prompt was submitted and no model inference was executed.
- Audit and task-run persistence remain `NOT CONFIGURED (OPTIONAL)`; no optional persistence write was tested.

At the time of the 2026-11-05 observation, the recorded Cloudflare deployment and read-only readiness checks were **VERIFIED**. This historical result is not evidence of current deployment, traffic, settings, connectivity, or readiness. Current production state remains **NOT VERIFIED** pending a fresh authorized read-back. Live inference, inference quality, end-to-end task execution, optional audit/task-run writes, and externally verified economic outcomes were not verified by that historical smoke. Do not infer successful model execution from a successful readiness probe.
## Release procedure

1. Make code changes on a branch and open a pull request. The active repository ruleset `GLORIFIER-NEURAL main protection1` (ID `27086549`; read back 2026-11-12) targets `~DEFAULT_BRANCH` and strictly requires `test (3.11)`, `test (3.12)`, and `Trusted AI Review Policy`, each attributed to GitHub Actions integration `15368`. Required signatures, CodeQL/code-quality controls, code-owner review, review-thread resolution, deletion prevention, and non-fast-forward prevention remain enabled; the required human approval count is zero and the bypass list is empty. The trusted-check workflow still lacks an exclusive publisher identity, and its event-policy allowlist remains subject to an administrator-controlled MFA step; see `docs/AI_REVIEW_POLICY.md`.
2. Require the repository's CI, security checks, and Cloudflare dry-run validation to pass. Do not bypass the active ruleset or weaken quality thresholds to obtain a green result.
3. After an approved merge to `main`, verify the Cloudflare Workers Builds validation-only package-preparation run; it must not upload or promote a Worker version. For production promotion, manually dispatch `.github/workflows/cloudflare-neural-worker.yml` from `main` with `deploy=true` through the protected `glorifier-neural-cloudflare-production` environment. Verify the protected deployment job, exact deployed Worker version, and intended traffic before announcing release. Do not wait for an automatic Workers Builds production deployment.
4. Require live `/health` and `/ready` checks. Expect `/ready` HTTP 200 when the selected provider, database, authentication, and rate-limit checks are verified. Accept HTTP 503 only for the explicit provider-disabled safe-mode response when the other required controls are verified and `inference_performed=false`; that response is not provider-ready.
5. Current production inference configuration is **NOT VERIFIED**. The historical 2026-11-05 read-back recorded `GLORIFIER_ENABLE_INFERENCE=true`, but that value must not be treated as current. Perform a controlled authenticated inference request only after a fresh authorized configuration read-back, confirmation that the selected provider credential is valid, explicit approval to transmit task content, and acceptance of any applicable API usage charges. The automated readiness/smoke steps intentionally do not submit a prompt.

Do not declare full AI production readiness until provider model-catalog readiness and a separately controlled inference check succeed. Enable audit writes or task-run persistence only after their own schema, least-privilege credentials, backup, and read/write verification steps have been approved and completed.
