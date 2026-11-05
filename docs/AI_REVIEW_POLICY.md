# AI-only pull request review policy

The policy is implemented by the GitHub Actions job named **AI Review Policy** in the existing CI workflow. It becomes a mandatory merge gate only after the repository ruleset explicitly requires this status check.

## Required AI reviewers

Both independently configured reviewer identities must submit a formal review against the exact current pull request head SHA:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

A review on an older commit does not count. Human reviews do not substitute for either AI reviewer and no human approval count is required.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed review submissions because the configured bots currently submit `COMMENTED` reviews in this repository.
- `CHANGES_REQUESTED`, dismissed, missing, or stale reviews fail the check.
- Explicit blocker markers in current-head AI review text or inline comments fail the check. Markers include `:stop_sign:`, `Security/Cost Risk`, `[blocker]`, `blocker:`, `critical:`, `severity: critical`, `high severity`, `do not merge`, `must not merge`, and `::error::`.
- The job waits up to 15 minutes for both configured reviewers to submit current-head reviews. GitHub API errors or malformed responses fail closed.
- Human review submissions do not satisfy the two AI-review requirements.

## Ruleset configuration still required

In repository ruleset **GLORIFIER-NEURAL** (ID `26492703`), retain the existing deletion, non-fast-forward, CodeQL code-scanning, code-quality, and pull-request rules. Keep required human approvals at **0** and bypass actors empty.

Add **AI Review Policy** as a required status check and require the latest commit to be checked (strict status checks). The required check must be produced by GitHub Actions. Do not add a human or team reviewer requirement.

A successful workflow run alone does not make this check mandatory: the ruleset must explicitly list the check. Re-read the ruleset after the setting change to confirm it is active and the required status-check context is present.
