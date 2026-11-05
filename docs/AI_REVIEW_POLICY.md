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

`.github/workflows/ai-review-policy-trusted.yml` is the trusted status publisher.

- It runs only from the default branch: on pushes to `main`, on completion of the trusted-base `CI` workflow (`workflow_run`), and on a five-minute schedule as a fallback.
- It reads open pull requests and their canonical head SHAs from the GitHub API, then reads formal reviews and review threads.
- It never checks out or executes pull-request code. It checks out the trusted `main` revision with persisted credentials disabled.
- Its only write permission is `statuses: write`; it has `pull-requests: read` and `contents: read`. No repository secret is required.
- It groups all open PRs by their exact head SHA and writes one `AI Review Policy (trusted)` commit status per unique SHA. Because GitHub commit statuses are SHA-scoped rather than PR-scoped, a SHA succeeds only when every open PR sharing that SHA passes independently; any blocker fails the group, and any unverifiable evidence produces an error.
- Missing reviews remain `pending` for at most 15 minutes from the head commit timestamp, then become `failure`. Future-dated or timezone-invalid commit timestamps are rejected as unverifiable evidence and cannot extend the pending interval. Explicit blockers or invalid review states fail immediately. Only two acceptable current-head reviews with no current unresolved AI blocker produce `success`. Malformed REST/GraphQL evidence and status-publication failures are reported as errors; any such per-head error also fails the workflow run.
- The `workflow_run` trigger rechecks after the existing `CI` workflow completes; the five-minute schedule is a fallback, not a real-time guarantee, and GitHub may delay scheduled execution under load. A new head SHA receives a new status and cannot inherit a previous head's success. The runner never consumes CI artifacts or executes code from the upstream workflow.

The older `AI Review Policy` job in `.github/workflows/ci.yml` remains a defense-in-depth check. Its `pull_request` and `pull_request_review` workflow definitions are evaluated from the PR merge ref, so it must not be treated as an independently trusted merge gate. GitHub documents that `pull_request_target` runs from the base branch, but this repository intentionally does not rely on that event because GitHub has announced a future restriction for it on public repositories.

## Required ruleset configuration — NOT YET ENFORCED

As audited on 2026-11-05, repository ruleset **GLORIFIER-NEURAL** (ID `26492703`) is active and targets `~DEFAULT_BRANCH`, but its `required_status_checks` list is empty. Its pull-request rule requires zero human approvals, and code-owner review is disabled. The ruleset's `bypass_actors` list is not empty: it contains a DeployKey and repository-role actors 2, 4, and 5, each with `bypass_mode: always`. The API reports `current_user_can_bypass: always`.

Therefore, the trusted status publisher is **not a mandatory merge gate until the ruleset is updated**. Keep the existing deletion, non-fast-forward, signed-commit, and code-scanning protections. Apply these exact settings to ruleset 26492703:

1. Clear every bypass actor: `bypass_actors: []`. Do not retain deploy-key, maintain, write, or admin bypass entries.
2. Add the exact required status context `AI Review Policy (trusted)`, with GitHub Actions selected as the expected source. The observed GitHub Actions app ID is `15368`.
3. Enable strict required-status-check enforcement so the status must be present for the current head and the branch must be up to date.
4. Keep required human approvals at `0`; do not add human/team reviewer requirements.

After saving, read the ruleset again and verify: enforcement is `active`; target is `~DEFAULT_BRANCH`; `bypass_actors` is empty; `current_user_can_bypass` is not `always`; `AI Review Policy (trusted)` is the required status from GitHub Actions; and human approvals remain zero. Until all of those conditions are confirmed, report the policy as **implemented in code but not enforced by the ruleset**.

## Existing CI review event behavior

The CI workflow continues to run its AI policy job on PR events as defense in depth. Review-thread resolution alone does not emit a formal review event, so the trusted scheduled publisher re-reads current state on its next run. Do not rely on a review-event check from the old PR-controlled workflow as a substitute for the trusted status context.
