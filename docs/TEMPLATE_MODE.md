# Temporary NEURAL Template Mode

**Status:** TEMPORARY TEMPLATE / MAINTENANCE MODE  
**Effective date:** 2026-11-12  
**Authority:** GLORIFIER remains the governing control plane. This document records the temporary operating posture; it does not grant deployment, merge, provider, database, or administrator privileges.

## Purpose

Treat GLORIFIER-NEURAL as a reusable engineering template while its outstanding pull requests, trusted-review controls, and administrator-side GitHub Actions policy are being repaired and verified. Prioritize reproducible patterns, provider adapter contracts, policy tests, CI, security controls, and documentation over expanding live capabilities.

## What template mode means

- New work should be reusable, provider-neutral, documented, and testable.
- Keep provider integrations opt-in and fail closed when credentials, explicit consent, or required controls are absent.
- Keep inference disabled in local and newly provisioned environments unless a separately authorized test explicitly enables it.
- Treat provider access, inference, database access, persistence, deployments, and economic outcomes as separate claims requiring fresh evidence.
- Keep financial actions, wallet signing, minting, destructive operations, and production writes denied by default.
- Use isolated repair branches and pull requests. Require exact-head CI, security checks, and required reviews.
- Do not auto-merge. Do not weaken branch protections, required checks, signed-commit requirements, or review policy.
- Do not change secrets, production data, Cloudflare settings, GitHub rulesets, Actions policies, or financial/blockchain state as part of template-mode work.

## Explicit non-goals

Template mode does not mean the codebase has been deleted, archived, or proven production-safe. It does not itself disable an already deployed Cloudflare Worker, revoke credentials, change provider configuration, or stop an independently configured deployment workflow. Those actions require separate inspection, authorization, and verified read-back.

The last repository documentation contains a historical Cloudflare configuration observation dated 2026-11-05, including an inference flag set to true. That observation is stale and must not be represented as the current production state. Until a fresh authorized Cloudflare read-back is recorded, current production inference and egress settings are **NOT VERIFIED**.

## Exit criteria

Return NEURAL to active implementation only after all of the following are evidenced:

1. Every open pull request is inventoried and classified as repairable, superseded, dependency-only, or blocked by external administration/review.
2. Each retained PR has current-head CI and security results; stale results do not count.
3. Trusted review evidence is attached to the exact current head and the check's source identity is trustworthy.
4. The authorized administrator saves the intended GitHub Actions event-policy allowlist after MFA, and a read-back confirms the saved policy.
5. Required branch protections and signed-commit controls remain enabled and unchanged.
6. Any desired production reactivation is separately authorized, inspected, and verified; template-mode documentation alone is not a deployment or runtime control.

## Reporting rules

Use evidence-only status labels: **VERIFIED**, **PARTIALLY VERIFIED**, **NOT VERIFIED**, **BLOCKED — ADMIN ACTION**, and **NOT APPLICABLE**. Record the observation timestamp, repository/branch/commit, exact checks, and source links. Never report a PR as fixed or safe to merge solely because its patch was written or one workflow passed.

## Reusable architecture contract

NEURAL remains a reusable, provider-neutral template with explicit boundaries:

- **Provider adapters:** implement the shared adapter contract in `app/providers/base.py`; provider selection is explicit, never inferred from the presence of credentials.
- **Orchestration:** `app/orchestrator.py` coordinates the selected provider only after policy checks and authorization gates.
- **Governance:** `app/policy.py` is deny-by-default for financial actions, wallet signing, minting, destructive operations, production writes, and unknown action classes.
- **Evidence:** distinguish process liveness, dependency readiness, provider reachability, inference, persistence, and economic outcomes. A successful `/health` or read-only `/ready` probe does not prove inference or task execution.
- **Human authority:** agents and providers may propose or execute only within explicitly granted scopes; repository protections and owner authorization remain authoritative.

## Setup and testing boundary

Use the repository's documented quick start in [README.md](../README.md#quick-start) and the safe defaults in [.env.example](../.env.example). Local and newly provisioned environments must retain:

- `GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=false`
- `GLORIFIER_ENABLE_INFERENCE=false`
- `GLORIFIER_PAID_INFERENCE_AUTHORIZED=false`

The development test baseline is Python 3.11 or 3.12, followed by:

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

The GitHub Actions CI matrix is the authoritative repository verification. Record the exact PR head SHA and workflow run IDs; a result from an earlier commit is stale evidence.

## Deployment boundary

Pull-request CI, tests, local Docker builds, and Cloudflare preview/package-validation builds are not production deployments. Production promotion is governed by [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and [OCTOPUS_DEPLOY.md](OCTOPUS_DEPLOY.md), including their protected manual-dispatch and environment requirements. Template mode does not invoke those workflows, publish images, change Worker settings, or authorize production promotion.

## Canonical references

- [Architecture and capabilities](../README.md#architecture)
- [Local setup and quick start](../README.md#quick-start)
- [Provider spend and inference controls](../README.md#explicit-inference-configuration)
- [AI review and governance controls](AI_REVIEW_POLICY.md)
- [Production readiness and deployment controls](PRODUCTION_READINESS.md)
- [Octopus deployment boundary](OCTOPUS_DEPLOY.md)
- [NVIDIA Dynamo adapter and live-verification gates](NVIDIA-DYNAMO.md)
- [Container and dependency definitions](../Dockerfile), [pyproject.toml](../pyproject.toml), and [uv.lock](../uv.lock)

## Current boundary

This mode is a repository operating policy and maintenance designation. It does not alter the production Worker or repository administration settings. Keep changes on repair branches and submit them as draft pull requests for review.
