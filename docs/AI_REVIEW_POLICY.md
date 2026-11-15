# Trusted AI pull-request review policy

## Required AI review evidence

The policy requires evidence from two independently configured reviewers:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Amazon Q must submit a GitHub pull-request review object (`APPROVED` or `COMMENTED`) attached to the exact current head SHA. CodeAnt's integration uses structured pull-request issue comments rather than a formal GitHub review object: the evaluator requires a completed `codeant-review-status` machine-readable record for the exact current head and a separate `CodeAnt PR Risk` assessment explicitly marked `Low Risk`, with its assessed commit matching the same SHA. An ordinary free-text comment, a stale or in-progress review status, an absent risk assessment, or a non-Low-Risk result does not satisfy this evidence contract.

Missing or stale Amazon Q evidence, malformed CodeAnt status/risk payloads, an unresolved current-head AI blocker, or a `CHANGES_REQUESTED` Amazon Q review fails the policy. A `:stop_sign:` annotation in the latest formal Amazon Q review body blocks that review even without an inline thread. A `:stop_sign:` annotation in an inline review comment blocks while its thread is unresolved and current to the head SHA. Human comments and manually authored bot-looking text do not substitute for evidence authored by the configured bot accounts.

The evaluator fails closed on malformed GitHub API responses, invalid SHAs, incomplete review metadata, invalid timestamps, stale evidence, and unresolved current-head blockers. It waits up to 15 minutes for missing reviewer evidence before failing the check.

## Authoritative enforcement workflow

`.github/workflows/trusted-ai-review-policy.yml` is the only workflow that enforces the AI review policy.

- `pull_request_target` handles pull-request opened, reopened, synchronized, and ready-for-review events.
- `pull_request_review` re-evaluates submitted, edited, and dismissed formal reviews.
- `pull_request_review_comment` re-evaluates created, edited, and deleted inline review comments.
- `issue_comment` re-evaluates CodeAnt status/risk comments on pull requests; ordinary issue comments are ignored.
- `workflow_dispatch` provides exact-head manual re-evaluation.
- Every supported event path checks out policy code from protected default branch `main`. No event-supplied PR base SHA or PR head is used as a checkout ref. All checkouts disable persisted credentials.
- It does not check out, import, or execute pull-request head code.
- It resolves the canonical current PR head SHA from the GitHub API and evaluates Amazon Q review records, CodeAnt's structured current-head evidence, and unresolved AI review threads.
- The evaluator job has only `contents: read` and `pull-requests: read` permissions. Check publication permission is isolated to the separate publisher job.

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

The allowlist is an account/repository settings control, not a repository file. The proposed allowlist must include exactly the required triggers used by this workflow: `pull_request_target`, `pull_request_review`, `pull_request_review_comment`, `issue_comment`, and `workflow_dispatch`. After an administrator saves it with MFA, read the policy back and verify that PR, formal-review, inline-review-comment, and CodeAnt issue-comment events all start the expected trusted workflow. Until that read-back and those tests are completed, public-repository event availability is NOT VERIFIED.

References: [GitHub changelog announcement](https://github.blog/changelog/2026-11-02-pull_request_target-blocked-by-default-december-2/) and [GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target).

## Current repository ruleset — read-back on 2026-11-16

A fresh GitHub API read of active ruleset **`GLORIFIER-NEURAL main protection1`**, ID **`27086549`**, targeting the default `main` branch, confirms:

- Required status checks are **only** `test (3.11)` and `test (3.12)`, both from GitHub Actions (integration ID `15368`).
- **`Trusted AI Review Policy` is not currently a required status check.** Do not describe it as an enforced merge gate until an administrator adds it, reads the ruleset back, and verifies a failing policy blocks merge.
- Strict required-status-check mode, required signed commits, CodeQL scanning, all-severity code quality, CODEOWNER-review and review-thread-resolution rules are enabled.
- Required approving human-review count is zero.
- The bypass actor list is empty; branch deletion and non-fast-forward updates are blocked.

**Check-source authenticity remains unresolved:** the existing GitHub Actions source identity (App ID `15368`) cannot distinguish this trusted publisher workflow from another workflow using the same identity. A dedicated GitHub App publisher identity or an independently verified repository-wide restriction is required before a same-name check can be treated as authoritative.

**CODEOWNERS coverage remains unresolved:** no `CODEOWNERS` file was found at the repository root, `.github/CODEOWNERS`, or `docs/CODEOWNERS`. The active CODEOWNER-review rule therefore has no verified path-to-owner mapping in those supported locations. An owner must name a real backup maintainer and add a reviewed mapping; do not invent an account or substitute a bot.

**Actions event-policy status remains NOT CREATED:** the earlier settings attempt required administrator MFA and was not saved. The administrator allowlist must cover `pull_request_target`, `pull_request_review`, `pull_request_review_comment`, `issue_comment`, and `workflow_dispatch`. Save and read back the policy, then verify every relevant event path before the December 2, 2026 public-repository restriction.

The November 12 and November 11 snapshots that follow are retained as historical evidence; their required-check lists and event allowlist instructions are superseded by this November 16 read-back. No branch rules or Actions settings were changed during this read-back.


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

Current check-source caveat: The shared GitHub Actions identity (App ID 15368) is used by all three required check contexts; it cannot prove which workflow created the Trusted AI Review Policy check.

The shared GitHub Actions source identity (App ID 15368) is applied to all three required check contexts.
