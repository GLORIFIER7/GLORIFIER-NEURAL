# Trusted AI pull-request review policy

## Required AI review evidence

The policy expects formal reviews from both configured reviewer identities:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

For each open pull request targeting `main`, both reviews must be attached to the exact current head SHA. `APPROVED` and `COMMENTED` are accepted completed states. Missing, stale, dismissed, unknown, or `CHANGES_REQUESTED` reviews do not pass. A `:stop_sign:` annotation in the latest formal review body from a configured reviewer blocks that current-head review even when no inline thread exists. A `:stop_sign:` annotation in an inline review comment blocks only while its thread is unresolved and current to the head SHA. Human reviews and ordinary bot comments do not substitute for the required formal AI reviews.

The evaluator fails closed on malformed GitHub API responses, invalid SHAs, incomplete review metadata, invalid timestamps, and unresolved current-head blockers. It waits up to 15 minutes for the expected formal reviews before failing for missing evidence.

## Authoritative enforcement workflow

`.github/workflows/trusted-ai-review-policy.yml` is the only workflow that enforces the AI review policy.

- `pull_request_target` handles pull request opened, reopened, synchronized, and ready-for-review events.
- `pull_request_review` re-evaluates submitted, edited, and dismissed reviews.
- Every supported event path checks out policy code from the protected default branch, `main`. No event-supplied PR base SHA or PR head is used as a checkout ref. All checkouts disable persisted credentials.
- It does not check out, import, or execute pull-request head code.
- It obtains the canonical current PR head SHA from the GitHub API, then evaluates formal reviews and review threads against that exact SHA.
- The job has only `contents: read` and `pull-requests: read` permissions.

The PR-editable `.github/workflows/ci.yml` is for code tests, dependency auditing, and the main-branch image publishing job. It must not define an AI review policy job or listen for `pull_request_review` events. The exact trusted check name to use in the branch ruleset is **`Trusted AI Review Policy`**.

## Manual re-evaluation fallback

GitHub exposes `pull_request_review_thread` as a webhook event, but it is not a supported GitHub Actions workflow trigger in the workflow-event reference used for this repository. Do **not** add `pull_request_review_thread` to the trusted workflow's `on:` block.

When a blocking review thread has been resolved but no new supported event has re-run the policy, use the existing exact-head manual dispatch:

1. Open the pull request and copy the current PR head SHA (the full 40-character head commit SHA).
2. In GitHub, open **Actions → Trusted AI Review Policy → Run workflow**.
3. Select the `main` branch. The policy job is restricted to `refs/heads/main` and loads policy code from trusted `main`; it never checks out or executes PR-head code.
4. Enter the open pull request number in `pull_request_number` and paste the copied exact head SHA in `pull_request_head_sha`.
5. Select **Run workflow**. The resolver fetches the canonical PR head from the GitHub API and rejects a mismatched or malformed SHA before evaluation. The publisher binds the outcome to the canonical current head.
6. If the pull request advances during dispatch, the publisher detects that the supplied SHA no longer matches the canonical PR head and exits before writing any check. It does not create a success or failure check for the mismatched dispatch. Copy the current PR head SHA and repeat the manual dispatch.

This procedure only re-evaluates the existing policy. It does not create formal AI reviews, clear unresolved findings, grant approval, bypass branch protection, or authorize merging. The normal required reviewer evidence and signed-commit rules still apply.

## Public-repository Actions event policy

This repository is public and the trusted workflow uses `pull_request_target`. GitHub has announced an event-policy restriction for this event in public repositories, with enforcement scheduled for **December 2, 2026**. Before that date, the repository or organization Actions event policy must explicitly allowlist this workflow file:

`.github/workflows/trusted-ai-review-policy.yml`

The allowlist is an account/repository settings control, not a repository file. After an administrator changes it, verify a new PR event and a review event both create the expected `Trusted AI Review Policy` check. Until that read-back and test are completed, public-repository event availability is not fully verified.

References: [GitHub changelog announcement](https://github.blog/changelog/2026-11-02-pull_request_target-blocked-by-default-december-2/) and [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target).

## Current repository ruleset — read-back on 2026-11-12

The current GitHub repository settings page shows the active ruleset **`GLORIFIER-NEURAL main protection1`**, ID **`27086549`**, targeting the default `main` branch.

Verified controls:

- Required status checks: `test (3.11)`, `test (3.12)`, and `Trusted AI Review Policy`; all three identify GitHub Actions (App ID `15368`) as their source.
- Strict branch-up-to-date mode and required signed commits are enabled.
- Code scanning requires CodeQL (High or higher security alerts; Errors alert threshold), and code-quality results require All severities.
- Code-owner review and conversation resolution are required; the required human approval count is zero.
- Force pushes and branch deletion are blocked; the bypass actors list is empty.

**Outstanding check-authenticity risk:** The required contexts share the GitHub Actions source identity (App ID `15368`). That source identity does not prove which workflow produced the `Trusted AI Review Policy` result. CodeAnt identified that a same-repository PR workflow could request `checks: write` and publish a same-name check. Keep this issue open until the required check is published by a dedicated GitHub App identity, or a verified repository-wide control prevents untrusted workflows from creating matching checks. Do not treat the green status from the current shared identity as an exclusive trusted policy result.

**Actions event-policy status:** The Actions Policies page reported zero Actions policies. The proposed active policy for `.github/workflows/trusted-ai-review-policy.yml` with exactly `pull_request_target`, `pull_request_review`, and `workflow_dispatch` was configured in the form but could not be saved because GitHub required an MFA confirmation. It remains NOT CREATED; an administrator must complete it with MFA and verify the saved policy and event execution before the December 2, 2026 public-repository change.

This is a November 12 read-back; the November 11 snapshot that follows is historical evidence and is superseded by these current observations. No branch rules or Actions settings were changed during this read-back.


## Historical ruleset snapshot — read-back on 2026-11-11 (superseded 2026-11-12)

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
