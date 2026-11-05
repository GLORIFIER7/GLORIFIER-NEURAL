# AI-only pull request review policy

The **AI Review Policy** job in `.github/workflows/ci.yml` evaluates two independently configured AI reviewer identities against the exact current pull request head SHA. It runs on `pull_request` events and re-evaluates on `pull_request_review` submissions, edits, and dismissals. The evaluator module is checked out from the event's target-branch base SHA into an isolated path, so the PR's version of `app.ai_review_policy.py` is not executed. **This is defense in depth, not a fully independent merge gate:** for `pull_request` events, the workflow definition itself is evaluated from the PR merge ref. A PR can therefore alter the job YAML unless workflow files are protected separately or a default-branch-pinned required-workflow rule is available and enabled.

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Human reviews never substitute for either bot, and no human approval count is required.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed formal reviews because the configured bots have submitted `COMMENTED` reviews in this repository.
- Missing or stale formal reviews fail. The latest current-head review must be `APPROVED` or `COMMENTED`; `CHANGES_REQUESTED` and dismissed/unknown states fail.
- An explicit `:stop_sign:` annotation from either AI reviewer blocks while its review thread is unresolved and current to the head commit. GitHub's formal-review and inline-thread login forms are normalized to the same configured bot identity.
- Resolved and outdated threads do not block. Ambiguous prose such as "critical" or "high severity" does not independently block.
- GitHub API errors and malformed review-thread responses fail closed. The policy uses a fixed GitHub.com API endpoint.
- The policy job is part of CI, waits up to 15 minutes for both reviewers, and has a 30-minute job timeout. Normal CI test jobs do not run for `pull_request_review` events. The policy checkout uses `persist-credentials: false`; the evaluator receives only the job-scoped read-only `GITHUB_TOKEN` needed to inspect reviews and review threads.
- CI concurrency groups include the event name so a review-event recheck cannot cancel the in-progress pull-request test run.

## Workflow-definition trust boundary

The current repository ruleset requires the `AI Review Policy` status context, but a normal `pull_request` workflow check is not cryptographically pinned to a protected workflow definition. Do not treat this check as tamper-proof against a PR that changes `.github/workflows/ci.yml` or adds another workflow that emits the same context. The repository owner must enable an independently pinned required workflow where the account supports it, or protect workflow-file changes using an appropriate repository-level control. The connected GitHub integration used for this remediation can inspect rulesets but cannot modify their administrative configuration.

## Required ruleset configuration

In repository ruleset **GLORIFIER-NEURAL** (ID `26492703`), preserve deletion protection, non-fast-forward protection, CodeQL code scanning, and code-quality rules. Keep required human approvals at **0** and bypass actors empty.

Target only `~DEFAULT_BRANCH`. Add **AI Review Policy** as a required status check from GitHub Actions with strict/latest-commit checking enabled. Do not add human or team reviewer requirements.

A successful Actions run is not a mandatory merge gate until the ruleset explicitly lists the exact **AI Review Policy** check context. Re-read the ruleset after editing to verify that it is active, targets the default branch, the check is required, human approvals remain 0, and bypass actors remain empty.
