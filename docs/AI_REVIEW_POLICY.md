# Trusted AI pull-request review policy

## Required AI review evidence

The policy expects formal reviews from both configured reviewer identities:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

For each open pull request targeting `main`, both reviews must be attached to the exact current head SHA. `APPROVED` and `COMMENTED` are accepted completed states. Missing, stale, dismissed, unknown, or `CHANGES_REQUESTED` reviews do not pass. An explicit `:stop_sign:` annotation from either reviewer blocks while its review thread remains unresolved and current to the head SHA. Human reviews and ordinary bot comments do not substitute for the required formal AI reviews.

The evaluator fails closed on malformed GitHub API responses, invalid SHAs, incomplete review metadata, invalid timestamps, and unresolved current-head blockers. It waits up to 15 minutes for the expected formal reviews before failing for missing evidence.

## Authoritative enforcement workflow

`.github/workflows/trusted-ai-review-policy.yml` is the only workflow that enforces the AI review policy.

- `pull_request_target` handles pull request opened, reopened, synchronized, and ready-for-review events.
- `pull_request_review` re-evaluates submitted, edited, and dismissed reviews.
- The workflow definition is loaded from the trusted base branch. It checks out only `github.event.pull_request.base.sha`, with persisted credentials disabled.
- It does not check out, import, or execute pull-request head code.
- It obtains the canonical current PR head SHA from the GitHub API, then evaluates formal reviews and review threads against that exact SHA.
- The job has only `contents: read` and `pull-requests: read` permissions.

The PR-editable `.github/workflows/ci.yml` is for code tests, dependency auditing, and the main-branch image publishing job. It must not define an AI review policy job or listen for `pull_request_review` events. The exact trusted check name to use in the branch ruleset is **`Trusted AI Review Policy`**.

## Public-repository Actions event policy

This repository is public and the trusted workflow uses `pull_request_target`. GitHub has announced an event-policy restriction for this event in public repositories, with enforcement scheduled for **December 2, 2026**. Before that date, the repository or organization Actions event policy must explicitly allowlist this workflow file:

`.github/workflows/trusted-ai-review-policy.yml`

The allowlist is an account/repository settings control, not a repository file. After an administrator changes it, verify a new PR event and a review event both create the expected `Trusted AI Review Policy` check. Until that read-back and test are completed, public-repository event availability is not fully verified.

## Active repository ruleset — read-back on 2026-11-11

The active ruleset is **`GLORIFIER-NEURAL main protection`**, ID **`27011361`**, scoped to `~DEFAULT_BRANCH`.

Verified controls:

- Enforcement is active and strict required-status-check mode is enabled.
- `bypass_actors` is empty and `current_user_can_bypass` is `never`.
- Branch deletion and non-fast-forward updates are prohibited.
- CodeQL scanning, required signatures, code-quality enforcement, Copilot code review, code-owner review, and review-thread resolution are enabled.
- Required approving human review count is zero.

The required-status-check list currently contains only `Amazon Q Developer` (integration ID `1220912`). It does **not** contain the CI matrix checks or `Trusted AI Review Policy`. This is a live merge-protection gap: a pull request can merge without the trusted policy check being successful. PR #86 was merged even though its trusted policy check failed for missing current-head reviews.

An administrator must update ruleset `27011361`, preserving its other protections and zero-bypass configuration, to require these exact check contexts from GitHub Actions (integration ID `15368`):

1. `test (3.11)`
2. `test (3.12)`
3. `Trusted AI Review Policy`

Retain `Amazon Q Developer` (integration ID `1220912`) only while that installed app remains an intended, active required check. Re-read the ruleset after saving and confirm the exact contexts, strict mode, and zero bypass actors. Then test a PR without either AI review and confirm the trusted check is red and merge is blocked; test a PR with both acceptable current-head reviews and no unresolved blockers and confirm the trusted check is green. Do not close the governance issue before these tests pass.

The connected GitHub write interface used for this maintenance can read rulesets but does not provide a ruleset-update action. The administrator settings change therefore remains external to this PR.

## Diagnostic status is not a merge gate

`.github/workflows/ai-review-policy-trusted.yml` publishes the SHA-scoped `AI Review Policy (diagnostic)` commit status from the default branch. It is useful for monitoring, but it is not a mandatory merge gate. Commit statuses can be reused across PRs sharing a SHA, may be spoofable by another workflow using the same GitHub Actions identity, and are refreshed asynchronously. Do not add `AI Review Policy (diagnostic)` to the ruleset's required checks.

## Operational boundaries

No policy change authorizes model inference, paid API usage, production deployment, database writes, wallet signing, minting, or other irreversible actions. The separate `GLORIFIER_PAID_INFERENCE_AUTHORIZED` guard remains default-deny. Production inference and persistence must be verified independently from repository CI and readiness checks.
