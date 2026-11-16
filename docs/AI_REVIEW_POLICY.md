# AI review status diagnostics

GLORIFIER-NEURAL retains a default-branch-only diagnostic that evaluates configured AI-review evidence and publishes a SHA-scoped GitHub commit status for open pull requests. The status is **advisory only**. It is not a required merge check, does not authorize a merge, and does not replace required human or code-owner review.

The diagnostic recognizes evidence from two configured AI reviewers:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Human approval and code-owner requirements are determined by the active GitHub ruleset, not by this diagnostic.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed formal reviews because the configured bots have submitted `COMMENTED` reviews in this repository.
- Both formal reviews must be attached to the exact current pull-request head SHA. Missing, stale, dismissed, unknown, or `CHANGES_REQUESTED` reviews do not pass.
- An explicit `:stop_sign:` annotation from either AI reviewer blocks while its review thread is unresolved and current to the head commit.
- Resolved and outdated threads do not block. Ambiguous prose such as "critical" or "high severity" does not independently block.
- GitHub API errors, invalid head SHAs, malformed review-thread responses, and unverified timestamps fail closed.

## Default-branch status diagnostics

`.github/workflows/ai-review-policy-trusted.yml` is the default-branch status publisher.

- It runs only from the default branch: on pushes to `main`, on completion of the trusted-base `CI` workflow (`workflow_run`), and on a 15-minute schedule as a fallback.
- It reads open pull requests and their canonical head SHAs from the GitHub API, then reads formal reviews and review threads.
- It never checks out or executes pull-request code. It checks out the trusted `main` revision with persisted credentials disabled.
- Its only write permission is `statuses: write`; it has `pull-requests: read` and `contents: read`. No repository secret is required.
- It groups all open PRs by their exact head SHA and writes one `AI Review Policy (diagnostic)` commit status per unique SHA. Because GitHub commit statuses are SHA-scoped rather than PR-scoped, a SHA succeeds only when every open PR sharing that SHA passes independently; any blocker fails the group, and any unverifiable evidence produces an error.
- Missing reviews remain `pending` for at most 15 minutes from the head commit timestamp, then become `failure`. Future-dated or timezone-invalid commit timestamps are rejected as unverifiable evidence and cannot extend the pending interval. Explicit blockers or invalid review states fail immediately. Only two acceptable current-head reviews with no current unresolved AI blocker produce `success`. Malformed REST/GraphQL evidence and status-publication failures are reported as errors; any such per-head error also fails the workflow run.
- The `workflow_run` trigger rechecks after the existing `CI` workflow completes; the 15-minute schedule is a fallback, not a real-time guarantee, and GitHub may delay scheduled execution under load. A new head SHA receives a new status and cannot inherit a previous head's success. The runner never consumes CI artifacts or executes code from the upstream workflow.

The former blocking `ai-review-policy` job in `.github/workflows/ci.yml` and the dedicated `.github/workflows/trusted-ai-review-policy.yml` workflow are removed by this maintenance change. Regular CI validates code, dependencies, and build artifacts; it no longer waits for AI reviewers or enforces their findings. The default-branch diagnostic publisher remains separate and informational.

## Ruleset configuration — live read-back (2026-11-16)

The GitHub API read-back on 2026-11-16 reports:

- **NEURAL ruleset 27086549:** active on the default branch; strict required status checks are enabled for `test (3.11)` and `test (3.12)`; required approving reviews are `0`; code-owner review and review-thread resolution are enabled; signed commits, CodeQL security scanning, code-quality enforcement, and Copilot review are enabled. `bypass_actors: []` and `current_user_can_bypass: never`.
- **GLORIFIER ruleset 24038955:** active on the default branch; no required status-check rule is configured; required approving reviews are `0`; code-owner review and review-thread resolution are enabled; CodeQL and Dependabot scanning, code-quality enforcement, and Copilot review are enabled. Its bypass list contains one deploy-key actor and repository-role IDs `2`, `4`, and `5`, each with `bypass_mode: always`; `current_user_can_bypass: always`.

The earlier 2026-11-05 statement that GLORIFIER had zero bypass actors is superseded by this 2026-11-16 read-back. GLORIFIER's default-branch protection therefore remains an administrator action: require the intended successful CI/security contexts and remove or narrowly constrain the always-bypass entries. NEURAL's current ruleset has strict Python checks and no bypass actors, but its status publisher is not configured as a required check.

Do not add `AI Review Policy (diagnostic)` to either ruleset as a required context. The current GitHub Actions identity can be reused by PR-controlled workflows, and the status is attached to a commit SHA rather than a specific PR. The diagnostic is not a tamper-resistant gate.

## Refresh cadence and limitations

Pull-request review submissions and review-thread changes do not trigger the diagnostic publisher directly. It refreshes on an eligible default-branch push, completion of the default-branch CI workflow, or the scheduled poll. A review-thread change can therefore remain reflected by an older status until the next scheduled run; GitHub may delay scheduled execution under load. Treat the context as informational, never as an authorization signal or required merge check.


## Security limitation — diagnostic only, not a mandatory merge gate

The commit-status publisher is deliberately a diagnostic signal and must **not** be required as the sole merge gate in its current form.

1. **Status-context spoofing:** the publisher uses the GitHub Actions identity. A different PR-controlled workflow may be able to request `statuses: write` and publish the same context to the same commit. Selecting GitHub Actions as the expected source does not distinguish this publisher workflow from another workflow using the same Actions identity. The current integration does not have a separately installed GitHub App identity that can be restricted to this publisher.
2. **Status reuse across pull requests:** commit statuses attach to commit SHAs, not to an individual PR. A newly opened PR that uses a SHA which already has a successful diagnostic status can inherit that success before the next poll evaluates the new PR's review evidence. Grouping open PRs by SHA reduces conflicting writes after a sweep, but it cannot retract the old success before the sweep runs.
3. **Asynchronous invalidation:** reopening a review thread does not reliably trigger this scheduled/CI-completion publisher. The prior success can remain on the same SHA until a subsequent run. Strict status checking does not make an existing status expire.

For these reasons, do **not** add `AI Review Policy (diagnostic)` to the branch ruleset's required status checks and do not describe it as tamper-resistant. A mandatory gate needs an independently authenticated verifier identity (for example, a dedicated GitHub App not usable by PR workflows), a PR-specific merge-time decision that cannot inherit another PR's evidence, and event-driven invalidation for review-thread changes. These capabilities are not available through the currently connected GitHub write integration.

These values are read-only observations, not changes made by this PR. Do not describe GLORIFIER as zero-bypass or claim its CI checks are required until an administrator changes the ruleset and a fresh API read-back confirms the result. The AI-review diagnostic remains intentionally outside both required-check lists.
