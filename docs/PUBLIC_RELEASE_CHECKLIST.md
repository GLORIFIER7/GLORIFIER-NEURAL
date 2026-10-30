# Public Repository Release Checklist

This checklist is required before changing this repository from private to public. Public visibility can expose source, commit history, pull requests, issues, discussions, workflow files, and any other content GitHub makes available to visitors. Reverting to private cannot guarantee that copies or forks are removed.

## Required owner and maintainer checks

- [ ] Select and approve an explicit open-source license. No license is implied by making the repository public; do not add a license without the rights holder's decision.
- [ ] Review the full Git history, all branches, tags, releases, pull requests, and workflow artifacts for credentials, private data, internal hostnames, and content that must remain confidential.
- [ ] Review GitHub Secret Scanning alerts and push-protection configuration. Resolve every alert and rotate any exposed credential; removing a value from the current tree is not sufficient.
- [ ] Confirm CodeQL has completed successfully on the exact release commit and that SARIF results are uploaded when repository visibility permits it.
- [ ] Confirm the complete CI matrix, dependency audit, and container build pass on the exact release commit.
- [ ] Review dependencies and redistribution obligations, including licenses and notices.
- [ ] Review repository collaborators, branch rules, workflow permissions, deployment environments, and public issue/discussion settings.
- [ ] Confirm README instructions, examples, and security-reporting instructions contain no live endpoints, private identifiers, or credentials.
- [ ] Obtain explicit owner approval for the visibility change.

## Operating constraints

- Keep production secrets in the deployment secret manager; never commit them or paste them into issues.
- Keep inference and external data egress disabled unless explicitly approved and securely configured.
- Do not connect production databases, perform migrations, deploy, publish images, or perform financial or blockchain actions as part of the visibility change.
- Treat a missing or inaccessible security scan as **NOT VERIFIED**, not as a clean result.

A public release is ready only when every required check above is supported by current evidence for the exact release commit.
