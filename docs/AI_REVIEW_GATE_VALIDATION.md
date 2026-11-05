# AI review gate enforcement validation

This temporary document exists only to exercise the repository's protected-branch
required-check configuration.

Expected behavior:
- The exact `AI Review Policy` check must be present on this pull request.
- Both configured AI reviewers must submit formal reviews against the current head.
- Missing, stale, dismissed, changes-requested, or blocking findings must not pass.
- This validation pull request must not be merged.

This file is intended to be removed by closing the validation pull request.
