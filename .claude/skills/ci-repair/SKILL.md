---
name: ci-repair
description: Diagnose NEURAL workflow failures from exact job logs and commit evidence, while avoiding paid inference and unsafe retries.
---

# CI repair

1. Identify the exact workflow run, event, head SHA, job and failed step.
2. Inspect the failure log and classify source defects separately from missing credentials, provider billing, rate limits, external outages, runner issues and policy blocks.
3. Reproduce locally with `uv lock --check`, Ruff or the narrowest relevant pytest command when safe.
4. Repair reproducible source/test defects with regression coverage; do not relax security or required-check policy.
5. Do not rerun billable model jobs, access secrets, alter Actions allowlists, change deployment configuration, run migrations or trigger releases without separate owner authorization.
6. Report exact run/commit evidence. Pending, skipped or blocked is not passed.
