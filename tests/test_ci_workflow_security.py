"""Regression tests for least-privilege CI credentials on untrusted PR code."""

from pathlib import Path
import re


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CI_WORKFLOW = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
TRUSTED_POLICY_WORKFLOW = (
    WORKFLOWS / "trusted-ai-review-policy.yml"
).read_text(encoding="utf-8")


def _job_section(name: str, workflow: str = CI_WORKFLOW) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match, f"CI job {name!r} must exist"
    return match.group(1)


def test_pull_requests_read_permission_is_limited_to_trusted_policy_workflow():
    ci_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        CI_WORKFLOW,
    )
    assert ci_permissions, "CI workflow-level permissions must be explicit"
    assert "pull-requests:" not in ci_permissions.group(1)

    policy_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        TRUSTED_POLICY_WORKFLOW,
    )
    assert policy_permissions, "Trusted policy permissions must be explicit"
    assert re.search(r"(?m)^  contents: read$", policy_permissions.group(1))
    assert re.search(r"(?m)^  pull-requests: read$", policy_permissions.group(1))
    assert "contents: write" not in policy_permissions.group(1)
    assert "pull-requests: write" not in policy_permissions.group(1)

    policy_job = _job_section("ai-review-policy", TRUSTED_POLICY_WORKFLOW)
    assert "ref: ${{ github.event.pull_request.base.sha }}" in policy_job
    assert "persist-credentials: false" in policy_job


def test_untrusted_test_job_does_not_persist_github_token():
    test_job = _job_section("test")
    assert "persist-credentials: false" in test_job, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
    assert "inputs.pull_request_head_sha" in test_job
    assert "ref: ${{ github.event_name == 'workflow_dispatch'" in test_job
    assert "pull-requests:" not in test_job


def test_review_events_use_trusted_base_context_and_documented_payload():
    policy_job = _job_section("ai-review-policy", TRUSTED_POLICY_WORKFLOW)
    assert re.search(r"(?m)^  pull_request_target:", TRUSTED_POLICY_WORKFLOW)
    assert re.search(r"(?m)^  pull_request_review:", TRUSTED_POLICY_WORKFLOW)
    assert "github.event.review.pull_request" not in policy_job
    assert "github.event.pull_request.base.sha" in policy_job
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job


def test_trusted_policy_module_has_a_preflight_before_execution():
    policy_job = _job_section("ai-review-policy", TRUSTED_POLICY_WORKFLOW)
    preflight = policy_job.find("- name: Verify trusted policy runner")
    runner = policy_job.find(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    assert preflight >= 0, "The trusted module import preflight must be present"
    assert runner > preflight, "The import preflight must run before the policy module"
    assert 'run: python -c "import app.ai_review_policy;' in policy_job
    assert policy_job.count("- name: Verify trusted policy runner") == 1


def test_policy_job_uses_canonical_pull_request_head_from_github_api():
    policy_job = _job_section("ai-review-policy", TRUSTED_POLICY_WORKFLOW)
    assert "id: current-pr" in policy_job
    assert "pulls/{pull_number}" in policy_job
    assert 'output.write("head_sha=" + head_sha + chr(10))' in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
