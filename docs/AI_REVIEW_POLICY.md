# AI-only pull request review policy

GLORIFIER-NEURAL uses two independently configured AI reviewers:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Human reviews do not substitute for either bot. The policy itself requires no human approval count.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed formal reviews because the configured bots have submitted `COMMENTED` reviews in this repository.
- Both formal reviews must be attached to the exact current pull-request head SHA. Missing, stale, dismissed, unknown, or `CHANGES_REQUESTED` reviews do not pass.
- An explicit `:stop_sign:` annotation from either AI reviewer blocks while its review thread is unresolved and current to the head commit.
- Resolved and outdated threads do not block. Ambiguous prose such as "critical" or "high severity" does not independently block.
- GitHub API errors, invalid head SHAs, malformed review-thread responses, and unverified timestamps fail closed.

## Trusted status publisher

`.github/workflows/ai-review-policy-trusted.yml` is the default-branch status publisher.

- It runs only from the default branch: on pushes to `main`, on completion of the trusted-base `CI` workflow (`workflow_run`), and on a five-minute schedule as a fallback.
- It reads open pull requests and their canonical head SHAs from the GitHub API, then reads formal reviews and review threads.
- It never checks out or executes pull-request code. It checks out the trusted `main` revision with persisted credentials disabled.
- Its only write permission is `statuses: write`; it has `pull-requests: read` and `contents: read`. No repository secret is required.
- It groups all open PRs by their exact head SHA and writes one `AI Review Policy (diagnostic)` commit status per unique SHA. Because GitHub commit statuses are SHA-scoped rather than PR-scoped, a SHA succeeds only when every open PR sharing that SHA passes independently; any blocker fails the group, and any unverifiable evidence produces an error.
- Missing reviews remain `pending` for at most 15 minutes from the head commit timestamp, then become `failure`. Future-dated or timezone-invalid commit timestamps are rejected as unverifiable evidence and cannot extend the pending interval. Explicit blockers or invalid review states fail immediately. Only two acceptable current-head reviews with no current unresolved AI blocker produce `success`. Malformed REST/GraphQL evidence and status-publication failures are reported as errors; any such per-head error also fails the workflow run.
- The `workflow_run` trigger rechecks after the existing `CI` workflow completes; the five-minute schedule is a fallback, not a real-time guarantee, and GitHub may delay scheduled execution under load. A new head SHA receives a new status and cannot inherit a previous head's success. The runner never consumes CI artifacts or executes code from the upstream workflow.

The older `AI Review Policy` job in `.github/workflows/ci.yml` remains a defense-in-depth check. Its `pull_request` and `pull_request_review` workflow definitions are evaluated from the PR merge ref, so it must not be treated as an independently trusted merge gate. GitHub documents that `pull_request_target` runs from the base branch, but this repository intentionally does not rely on that event because GitHub has announced a future restriction for it on public repositories.

## Required ruleset configuration — NOT YET ENFORCED

Fresh GitHub API read-back on 2026-11-05 confirms repository ruleset **GLORIFIER-NEURAL** (ID `26492703`) is active and targets `~DEFAULT_BRANCH`. Its `bypass_actors` list is now empty and `current_user_can_bypass` is `never`. The pull-request rule currently has zero required approving reviews, requires code-owner review, and resolves review threads. Strict required-status-check freshness is enabled, but the `required_status_checks` list is still empty.

Therefore, the default-branch status publisher is **implemented in code but not a mandatory merge gate**. The bypass-removal requirement is satisfied; do not re-add any bypass actor. Keep the existing deletion, non-fast-forward, signed-commit, and code-scanning protections. The remaining ruleset change is to add the exact required status context `AI Review Policy (diagnostic)`, with GitHub Actions selected as the expected source (observed app ID `15368`). Keep required human approvals at `0`. Review the enabled code-owner requirement separately against the repository's stated AI-only review policy before changing it.

After saving the required-check context, read the ruleset again and verify: enforcement is `active`; target is `~DEFAULT_BRANCH`; `bypass_actors` is empty; `current_user_can_bypass` is `never`; strict status-check enforcement is enabled; `AI Review Policy (diagnostic)` is required from GitHub Actions; and human approvals remain zero. Do not claim enforcement until the exact context is visible in the saved ruleset.

## Existing CI review event behavior

The CI workflow continues to run its AI policy job on PR events as defense in depth. Review-thread resolution alone does not emit a formal review event, so the trusted scheduled publisher re-reads current state on its next run. Do not rely on a review-event check from the old PR-controlled workflow as a substitute for the diagnostic status context.


## Security limitation — diagnostic only, not a mandatory merge gate

The commit-status publisher is deliberately a diagnostic signal and must **not** be required as the sole merge gate in its current form.

1. **Status-context spoofing:** the publisher uses the GitHub Actions identity. A different PR-controlled workflow may be able to request `statuses: write` and publish the same context to the same commit. Selecting GitHub Actions as the expected source does not distinguish this publisher workflow from another workflow using the same Actions identity. The current integration does not have a separately installed GitHub App identity that can be restricted to this publisher.
2. **Status reuse across pull requests:** commit statuses attach to commit SHAs, not to an individual PR. A newly opened PR that uses a SHA which already has a successful diagnostic status can inherit that success before the next poll evaluates the new PR's review evidence. Grouping open PRs by SHA reduces conflicting writes after a sweep, but it cannot retract the old success before the sweep runs.
3. **Asynchronous invalidation:** reopening a review thread does not reliably trigger this scheduled/CI-completion publisher. The prior success can remain on the same SHA until a subsequent run. Strict status checking does not make an existing status expire.

For these reasons, do **not** add `AI Review Policy (diagnostic)` to the branch ruleset's required status checks and do not describe it as tamper-resistant. A mandatory gate needs an independently authenticated verifier identity (for example, a dedicated GitHub App not usable by PR workflows), a PR-specific merge-time decision that cannot inherit another PR's evidence, and event-driven invalidation for review-thread changes. These capabilities are not available through the currently connected GitHub write integration.

The existing ruleset gaps are separate and remain unresolved: both rulesets were observed with always-bypass actors and no required status checks. Removing bypass actors and configuring required checks requires repository Administration write access. Do not claim those controls are fixed until the rulesets have been updated and read back successfully.
