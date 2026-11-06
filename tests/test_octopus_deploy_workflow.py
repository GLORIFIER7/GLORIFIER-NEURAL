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


def test_neural_main_ci_publishes_the_exact_image_that_passed_the_test_matrix():
    publish_start = CI_WORKFLOW.index("  publish-container:")
    job = CI_WORKFLOW[publish_start:]

    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in job
    assert "needs: [test]" in job
    assert "packages: write" in job
    assert "Download the exact image exported by the passing CI matrix" in job
    assert "docker load --input /tmp/glorifier-neural-image/glorifier-neural-ci.tar" in job
    assert "ghcr.io/glorifier7/glorifier-neural:0.0.0-${{ github.sha }}" in job
    assert "docker build" not in job, "The publisher must publish the tested artifact, not rebuild it"

    assert "Upload the CI-tested container image" in CI_WORKFLOW
    assert "matrix.python-version == '3.12'" in CI_WORKFLOW


def test_neural_octopus_requires_the_ci_image_publisher_to_succeed():
    assert "actions: read" in WORKFLOW
    assert 'job.get("name") == "publish-container"' in WORKFLOW
    assert 'step.get("name") == "Publish the immutable commit-versioned image"' in WORKFLOW


def test_octopus_preflight_rejects_multiple_deployment_environments():
    preflight_start = WORKFLOW.index("      - name: Validate Octopus deployment configuration")
    verify_start = WORKFLOW.index("      - name: Verify the upstream CI-tested image publication succeeded")
    assert preflight_start >= 0 and verify_start > preflight_start
    preflight = WORKFLOW[preflight_start:verify_start]

    expected_guard = r'''if [[ "$OCTOPUS_ENVIRONMENT" == *','* || "$OCTOPUS_ENVIRONMENT" == *$'\\n'* || "$OCTOPUS_ENVIRONMENT" == *$'\\r'* ]]; then'''
    assert expected_guard in preflight
    assert "exactly one environment name (no commas, CR, or LF)" in preflight


def test_octopus_workflow_contains_exactly_one_release_and_deployment_sequence():
    for step in (
        "      - name: Validate Octopus deployment configuration",
        "      - name: Authenticate to Octopus Deploy using GitHub OIDC",
        "      - name: Wait for the Octopus deployment to finish",
    ):
        assert WORKFLOW.count(step) == 1
