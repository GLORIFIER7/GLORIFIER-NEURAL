# Claude Code project integration

This directory adds Claude Code-native project agents and reusable skills to GLORIFIER-NEURAL.

- `AGENTS.md` is the shared coding-agent contract.
- `.claude/agents/` provides architecture, security, QA, implementation and PR-review specialists.
- `.claude/skills/` provides repository-audit, issue-repair, CI-repair and PR-review workflows.
- `.claude/settings.json` registers local permission boundaries and PreToolUse hooks for Bash and file-edit tool variants.
- `.claude/hooks/agent-policy.mjs` blocks protected path edits, force-push, git reset/clean, PR merge, secret mutation, deployment and publishing. Run its regression suite with `node --test .claude/hooks/agent-policy.test.mjs`.

These local hooks are supplemental guardrails, not a sandbox or replacement for GitHub rulesets, trusted review policy, server-side provider authorization, runtime controls or operator oversight. Shell indirection can make command intent difficult to infer; do not use it to bypass protected-path review.

Authenticate Claude Code on each developer machine. Local Claude Code sign-in, Anthropic API billing, GitHub Actions inference and the NEURAL Anthropic runtime are separate. This configuration grants no API credits, provider credentials, external-egress permission, model quota or paid-inference authorization. The configuration and hook tests do not call Anthropic.
