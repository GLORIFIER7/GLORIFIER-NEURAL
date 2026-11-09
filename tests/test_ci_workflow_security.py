"""Regression tests for least-privilege CI and trusted PR-review policy."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = (
    ROOT / ".github" / "workflows" / "ci.yml"
).read_text(encoding="utf-8")
TRUSTED_POLICY_WORKFLOW = (
    ROOT / ".github" / "workflows" / "trusted-ai-review-policy.yml"
).read_text(encoding="utf-8")


def _job_section(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match, f"CI job {name!r} must exist"
    return match.group(1)


def test_untrusted_ci_workflow_has_only_read_only_repository_permissions():
    top_level_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        CI_WORKFLOW,
    )
    assert top_level_permissions, "Workflow-level permissions must be explicit"
    assert "contents: read" in top_level_permissions.group(1)
    assert "pull-requests:" not in top_level_permissions.group(1)
    assert "contents: write" not in top_level_permissions.group(1)


def test_trusted_policy_permissions_are_read_only_and_minimal():
    permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        TRUSTED_POLICY_WORKFLOW,
    )
    assert permissions, "Trusted policy permissions must be explicit"
    assert "contents: read" in permissions.group(1)
    assert "pull-requests: read" in permissions.group(1)
    assert "contents: write" not in permissions.group(1)
    assert "pull-requests: write" not in permissions.group(1)


def test_untrusted_test_job_does_not_persist_github_token():
    test_job = _job_section(CI_WORKFLOW, "test")
    assert "persist-credentials: false" in test_job, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
    assert "inputs.pull_request_head_sha" in test_job
    assert "ref: ${{ github.event_name == 'workflow_dispatch'" in test_job
    assert "pull-requests: write" not in test_job


def test_review_events_use_the_separate_trusted_workflow_context():
    assert "pull_request_target:" in TRUSTED_POLICY_WORKFLOW
    assert "pull_request_review:" in TRUSTED_POLICY_WORKFLOW
    assert "github.event.review.pull_request" not in TRUSTED_POLICY_WORKFLOW
    assert "github.event.pull_request.base.sha" in TRUSTED_POLICY_WORKFLOW
    assert "github.event_name == 'workflow_dispatch'" not in TRUSTED_POLICY_WORKFLOW
    assert "inputs.pull_request_number" not in TRUSTED_POLICY_WORKFLOW


def test_trusted_policy_module_has_a_preflight_before_execution():
    policy_job = _job_section(TRUSTED_POLICY_WORKFLOW, "ai-review-policy")
    preflight = policy_job.find("- name: Verify trusted policy runner")
    runner = policy_job.find(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    assert preflight >= 0, "The trusted module import preflight must be present"
    assert runner > preflight, "The import preflight must run before the policy module"
    assert 'run: python -c "import app.ai_review_policy;' in policy_job
    assert policy_job.count("- name: Verify trusted policy runner") == 1


def test_policy_job_uses_canonical_pull_request_head_from_github_api():
    policy_job = _job_section(TRUSTED_POLICY_WORKFLOW, "ai-review-policy")
    assert "id: current-pr" in policy_job
    assert "pulls/{pull_number}" in policy_job
    assert 'output.write("head_sha=" + head_sha + chr(10))' in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
    assert "github.event.pull_request.base.sha" in policy_job
