---
name: pull-request-review
description: Review NEURAL pull requests, Python changes, provider safety and exact-head CI evidence without merging.
---

# Pull request review

1. Read PR metadata, all changed paths, complete patches, discussions and current-head checks.
2. Apply repository instructions and the relevant security, provider, runtime and release contracts.
3. Review async/sync boundaries, bounded I/O, timeouts, redirect behavior, authentication, authorization, data handling, rate limits and test coverage.
4. Verify claims against the exact tested commit. A provider adapter or configured API key does not prove readiness or inference.
5. Report blocking findings first with severity, precise file/line, impact and a minimal fix.
6. Do not approve, merge, deploy, change secrets or alter branch protection. Preserve human review and owner authority.
