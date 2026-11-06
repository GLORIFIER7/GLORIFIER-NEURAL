# Octopus Deploy integration

GitHub Actions remains the CI authority. The GLORIFIER-owned Octopus Cloud instance coordinates releases and executes deployments.

## Workflow behavior

The Octopus Deploy workflow:
- Starts automatically only after the **CI** workflow completes successfully for a push to main, including its image-publishing job.
- Can also be started manually from main.
- Does not deploy pull requests, failed CI runs, scheduled CI runs, or manual CI runs.
- Creates a release, deploys it to one configured Octopus environment, and waits for the deployment task to finish.
- Runs only when the repository Actions variable `OCTOPUS_ENABLED` is exactly `true` and the required project/environment variables are present. Manual dispatch is also gated at the job level and is accepted only from `main`.
- Checks the Octopus service-account ID from the `octopus-deploy` Environment secret before requesting an OIDC token.
- Uses GitHub OIDC and a dedicated Octopus service account; no long-lived Octopus API key is stored in GitHub.

The workflow pins the official Octopus GitHub Actions to commit SHAs. It does not bypass branch protection, merge pull requests, or modify repository rulesets.

## One-time setup

1. In https://glorifier.octopus.app, create a dedicated service account for this repository. Restrict it to this repository's Octopus Space, Project, and deployment Environment. Do not reuse the GLORIFIER service account.
2. On that service account, create an OpenID Connect identity with issuer type **GitHub Actions**. Use this exact GitHub subject:

   `repo:GLORIFIER7/GLORIFIER-NEURAL:environment:octopus-deploy`

   Let Octopus provide the required audience and remaining identity settings. Do not broaden the subject to all repositories or refs.
3. In GitHub, create the repository Environment named **octopus-deploy** and restrict it to the **main** branch. Add required reviewers or other environment protections only when required by the deployment policy.
4. In the GitHub `octopus-deploy` Environment, add the environment **Secret** `OCTOPUS_SERVICE_ACCOUNT_ID` containing the dedicated Octopus service-account ID. Keep this ID out of repository variables and workflow logs.
5. Add these repository Actions **Variables**:

   | Variable | Value |
   |---|---|
   | OCTOPUS_ENABLED | Set to `true` only after the Octopus project, target and OIDC trust are configured |
   | OCTOPUS_SPACE | Exact Octopus Space name |
   | OCTOPUS_PROJECT | Exact Octopus Project name |
   | OCTOPUS_ENVIRONMENT | Exact single target Environment name |
   | OCTOPUS_CONFIG_AS_CODE | `true` only if the Octopus Project configuration is stored in Git; otherwise `false` or unset |

6. Create and configure the Octopus Project deployment process, package feeds, deployment targets, variables, and lifecycle. For Config as Code, connect the project to its source repository through Octopus's GitHub connection and align its default branch with main.

## Deployment boundary

NEURAL CI builds the container image in its test matrix. On a push to `main`, the Python 3.12 test job saves that exact image as a short-lived Actions artifact. The `publish-container` job waits for the complete test matrix to pass, downloads that image (without rebuilding it), and publishes it to GitHub Container Registry as `ghcr.io/glorifier7/glorifier-neural:0.0.0-<full-commit-sha>` using the job-scoped `GITHUB_TOKEN` permission `packages: write`.

Configure an Octopus Docker/OCI feed for `ghcr.io/glorifier7/glorifier-neural` and a project deployment package step that consumes that image. Both Octopus release paths pass `package_version: 0.0.0-${SOURCE_COMMIT}` so Octopus selects the exact image produced by the passing CI run, never `latest`. If the GHCR package is private, store a read-only GitHub Packages credential in the Octopus feed settings, not in GitHub Actions or the repository. Release creation should fail if the exact image tag is absent. Preflight also compares the triggering source SHA with the current `main` head and refuses stale CI completions before OIDC authentication.

A successful CI run or created release is not proof that the live application is healthy. The workflow waits for the Octopus deployment task result; a separate post-deployment application health check is still required.

Verify the first deployment against a non-production target before setting OCTOPUS_ENVIRONMENT to production. Confirm artifact provenance, rollback behavior, target permissions, and operational costs before enabling recurring production deployments.

## Evidence states

- **Not configured:** required repository variables or the Octopus OIDC identity are missing; automatic deployment is skipped or manual preflight fails.
- **Configured:** variables and identity exist; this is not proof of successful deployment.
- **Deployment verified:** the Octopus task finishes successfully for the intended release and environment.
- **Application health verified:** an independent post-deployment health check succeeds. This workflow does not claim this state.
