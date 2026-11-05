# AI-only pull request review policy

The **AI Review Policy** job in `.github/workflows/ci.yml` evaluates two independently configured AI reviewer identities against the exact current pull request head SHA. It runs on `pull_request` events and re-evaluates on `pull_request_review` submissions, edits, and dismissals.

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Human reviews never substitute for either bot, and no human approval count is required.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed formal reviews because the configured bots have submitted `COMMENTED` reviews in this repository.
- Missing or stale formal reviews fail. The latest current-head review must be `APPROVED` or `COMMENTED`; `CHANGES_REQUESTED` and dismissed/unknown states fail.
- An explicit `:stop_sign:` annotation from either AI reviewer blocks while its review thread is unresolved and current to the head commit. GitHub's formal-review and inline-thread login forms are normalized to the same configured bot identity.
- Resolved and outdated threads do not block. Ambiguous prose such as "critical" or "high severity" does not independently block.
- GitHub API errors and malformed review-thread responses fail closed. The policy uses a fixed GitHub.com API endpoint.
- The policy job is part of CI, waits up to 15 minutes for both reviewers, and has a 30-minute job timeout. Normal CI test jobs do not run for `pull_request_review` events.
- CI concurrency groups include the event name so a review-event recheck cannot cancel the in-progress pull-request test run.

## Required ruleset configuration

In repository ruleset **GLORIFIER-NEURAL** (ID `26492703`), preserve deletion protection, non-fast-forward protection, CodeQL code scanning, and code-quality rules. Keep required human approvals at **0** and bypass actors empty.

Target only `~DEFAULT_BRANCH`. Add **AI Review Policy** as a required status check from GitHub Actions with strict/latest-commit checking enabled. Do not add human or team reviewer requirements.

A successful Actions run is not a mandatory merge gate until the ruleset explicitly lists the exact **AI Review Policy** check context. Re-read the ruleset after editing to verify that it is active, targets the default branch, the check is required, human approvals remain 0, and bypass actors remain empty.
