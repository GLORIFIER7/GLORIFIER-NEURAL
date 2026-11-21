---
name: repository-audit
description: Audit the NEURAL Python service, provider adapters, security, CI and production evidence without mutating live systems.
---

# Repository audit

1. Read `AGENTS.md`, `README.md`, `SECURITY.md` and `docs/PRODUCTION_READINESS.md`.
2. Record branch, commit, working-tree state, audit scope and observation time.
3. Trace the actual implementation through runtime, API, orchestrator, policy, provider adapters and persistence; do not infer behavior from names or docs alone.
4. Inspect current tests, lockfile validity, Ruff results, relevant CI workflows and current-head check status.
5. Do not access secret values, submit prompts to providers, enable external egress, run migrations, deploy or consume paid capacity.
6. Separate implemented, configured, test-passed, live-verified and NOT VERIFIED evidence.
7. Report prioritized findings with exact paths/symbols, impact, reproducible evidence and the next safe verification step.
