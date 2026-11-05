# AI-only pull request review policy

The GitHub Actions job named **AI Review Policy** evaluates two independently configured AI reviewer identities against the exact current pull request head SHA:

- Amazon Q Developer: `amazon-q-developer[bot]`
- CodeAnt AI: `codeant-ai[bot]`

Human reviews never substitute for either bot, and no human approval count is required.

## Review outcome

- `APPROVED` and `COMMENTED` are accepted as completed formal reviews because both bots have submitted `COMMENTED` reviews in this repository.
- Missing or stale formal reviews fail. The latest current-head review must be `APPROVED` or `COMMENTED`; `CHANGES_REQUESTED` and dismissed/unknown states fail.
- An explicit `:stop_sign:` annotation from either AI reviewer blocks while its review thread is unresolved and current to the head commit.
- Resolved and outdated threads do not block. Ambiguous phrases such as "critical" or "high severity" do not independently block.
- The gate reads review threads through the fixed GitHub.com API endpoint, fails closed on API errors, and waits up to 15 minutes for both reviewers. Its Actions job timeout is 20 minutes.

## Required ruleset configuration

In repository ruleset **GLORIFIER-NEURAL** (ID `26492703`), preserve deletion protection, non-fast-forward protection, CodeQL code scanning, and code-quality rules. Keep required human approvals at **0** and bypass actors empty.

Add **AI Review Policy** as a required status check with strict/latest-commit checking enabled. Do not add human or team reviewer requirements.

A successful Actions run is not a mandatory merge gate until the ruleset explicitly lists the exact **AI Review Policy** check context. Re-read the ruleset after editing to verify that it is active, the check is required, human approvals remain 0, and bypass actors remain empty.
