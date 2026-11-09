"""Regression tests for least-privilege CI credentials on untrusted PR code."""

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "ci.yml"
).read_text(encoding="utf-8")

TRUSTED_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "trusted-ai-review-policy.yml"
).read_text(encoding="utf-8")


def _job_section(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        WORKFLOW,
    )
    assert match, f"CI job {name!r} must exist"
    return match.group(1)


def _trusted_job_section(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        TRUSTED_WORKFLOW,
    )
    assert match, f"Trusted policy job {name!r} must exist"
    return match.group(1)


def test_pull_requests_read_permission_is_limited_to_trusted_policy_workflow():
    ci_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        WORKFLOW,
    )
    assert ci_permissions, "CI workflow permissions must be explicit"
    assert "pull-requests:" not in ci_permissions.group(1)

    trusted_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        TRUSTED_WORKFLOW,
    )
    assert trusted_permissions, "Trusted policy permissions must be explicit"
    assert "pull-requests: read" in trusted_permissions.group(1)
    _trusted_job_section("ai-review-policy")

def test_untrusted_test_job_does_not_persist_github_token():
    test_job = _job_section("test")
    assert "persist-credentials: false" in test_job, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
    assert "inputs.pull_request_head_sha" in test_job
    assert "ref: ${{ github.event_name == 'workflow_dispatch'" in test_job

def test_review_event_uses_trusted_base_and_current_pull_request_context():
    policy_job = _trusted_job_section("ai-review-policy")
    assert "pull_request_target:" in TRUSTED_WORKFLOW
    assert "pull_request_review:" in TRUSTED_WORKFLOW
    assert "github.event.review.pull_request" not in policy_job
    assert "github.event.pull_request.base.sha" in policy_job
    assert "github.event_name == 'workflow_dispatch'" not in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job

def test_trusted_policy_module_has_a_preflight_before_execution():
    policy_job = _trusted_job_section("ai-review-policy")
    preflight = policy_job.find("- name: Verify trusted policy runner")
    runner = policy_job.find("- name: Enforce both AI reviewer findings on the exact current PR head")
    assert preflight >= 0, "The trusted module import preflight must be present"
    assert runner > preflight, "The import preflight must run before the policy module"
    assert 'run: python -c "import app.ai_review_policy;' in policy_job
    assert policy_job.count("- name: Verify trusted policy runner") == 1

def test_policy_job_uses_canonical_pull_request_head_from_github_api():
    policy_job = _trusted_job_section("ai-review-policy")
    assert "id: current-pr" in policy_job
    assert "pulls/{pull_number}" in policy_job
    assert 'output.write("head_sha=" + head_sha + chr(10))' in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
