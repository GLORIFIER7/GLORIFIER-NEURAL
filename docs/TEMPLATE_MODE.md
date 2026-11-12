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

## Current boundary

This mode is a repository operating policy and maintenance designation. It does not alter the production Worker or repository administration settings. Keep changes on repair branches and submit them as draft pull requests for review.
