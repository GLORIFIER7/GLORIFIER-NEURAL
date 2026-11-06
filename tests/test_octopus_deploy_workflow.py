"""Regression tests for Octopus deployment workflow timeout budgeting."""

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "octopus-deploy.yml"
).read_text(encoding="utf-8")

CI_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "ci.yml"
).read_text(encoding="utf-8")


def test_octopus_job_timeout_leaves_headroom_after_await_action_timeout():
    deploy = re.search(
        r"(?ms)^  deploy:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        WORKFLOW,
    )
    assert deploy, "The Octopus deploy job must exist"

    job = deploy.group(1)
    job_timeout = re.search(r"(?m)^    timeout-minutes: (\d+)$", job)
    assert job_timeout, "The Octopus deploy job must have an explicit timeout"

    await_step = re.search(
        r"(?ms)^      - name: Wait for the Octopus deployment to finish\n"
        r"(.*?)(?=^      - name:|\Z)",
        job,
    )
    assert await_step, "The Octopus await-task step must exist"

    await_timeout = re.search(
        r"(?m)^\s+timeout_after: ['\"]?(\d+)['\"]?$",
        await_step.group(1),
    )
    assert await_timeout, "The Octopus await-task timeout must be explicit"

    job_seconds = int(job_timeout.group(1)) * 60
    await_seconds = int(await_timeout.group(1))
    required_headroom_seconds = 30 * 60

    assert job_seconds >= await_seconds + required_headroom_seconds, (
        "The GitHub job timeout must leave at least 30 minutes beyond the "
        "Octopus task wait timeout so setup and teardown cannot cut off the wait."
    )


def test_octopus_concurrency_is_job_scoped_and_normalized():
    assert not re.search(r"(?m)^concurrency:$", WORKFLOW), (
        "Skipped workflow_run events must not acquire the deployment concurrency group"
    )
    deploy = re.search(r"(?ms)^  deploy:\n(.*)\Z", WORKFLOW)
    assert deploy, "Octopus deploy job must exist"
    expected_group = (
        "    concurrency:\n"
        "      group: octopus-deploy-${{ github.workflow }}-"
        "${{ github.event.workflow_run.head_branch || github.ref_name }}"
    )
    assert expected_group in deploy.group(0), (
        "Manual and automatic main deployments must share a job-level concurrency group"
    )


def test_octopus_preflight_rejects_stale_source_commit_before_oidc():
    preflight = re.search(
        r"(?ms)^      - name: Validate Octopus deployment configuration\n"
        r"(.*?)(?=^      - name: Authenticate to Octopus Deploy using GitHub OIDC|\Z)",
        WORKFLOW,
    )
    assert preflight, "Octopus deployment configuration preflight must exist"
    source = preflight.group(1)

    assert "GH_TOKEN: ${{ github.token }}" in source
    assert 'gh api "repos/${GITHUB_REPOSITORY}/commits/main" --jq .sha' in source
    assert 'if [[ "$current_main_sha" != "$SOURCE_COMMIT" ]]; then' in source




def test_neural_octopus_only_deploys_a_successful_main_push():
    assert "github.event.workflow_run.event == 'push'" in WORKFLOW
    assert "github.event.workflow_run.head_sha == github.sha" in WORKFLOW


def test_both_octopus_release_paths_pin_package_version_to_ci_tested_source_commit():
    assert WORKFLOW.count("package_version: 0.0.0-${{ env.SOURCE_COMMIT }}") == 2


def test_octopus_integration_does_not_add_package_publication_permissions():
    assert "publish-container:" not in CI_WORKFLOW
    assert "packages: write" not in CI_WORKFLOW
    assert "Upload the exact CI-tested container image" not in CI_WORKFLOW
