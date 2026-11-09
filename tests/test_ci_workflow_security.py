"""Regression tests for least-privilege CI and trusted PR-review policy."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
TRUSTED_POLICY_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "trusted-ai-review-policy.yml"
)


def _read_workflow(path: Path) -> str:
    assert path.is_file(), f"Required workflow file is missing: {path.name}"
    return path.read_text(encoding="utf-8")


def _job_section(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert match, f"CI job {name!r} must exist"
    return match.group(1)


def _assert_no_write_permissions(scope: str) -> None:
    for permission in ("contents", "pull-requests", "actions", "id-token"):
        assert not re.search(
            rf"(?m)^\\s*{re.escape(permission)}:\\s*write\\s*$",
            scope,
        ), f"{permission}: write is not permitted in this workflow scope"


def test_untrusted_ci_workflow_has_only_read_only_repository_permissions():
    workflow = _read_workflow(CI_WORKFLOW_PATH)
    top_level_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        workflow,
    )
    assert top_level_permissions, "Workflow-level permissions must be explicit"
    assert "contents: read" in top_level_permissions.group(1)
    _assert_no_write_permissions(top_level_permissions.group(1))
    assert "pull-requests:" not in top_level_permissions.group(1)


def test_trusted_policy_permissions_are_read_only_and_minimal():
    workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        workflow,
    )
    assert permissions, "Trusted policy permissions must be explicit"
    assert "contents: read" in permissions.group(1)
    assert "pull-requests: read" in permissions.group(1)
    _assert_no_write_permissions(permissions.group(1))

    policy_job = _job_section(workflow, "ai-review-policy")
    _assert_no_write_permissions(policy_job)


def test_untrusted_test_job_does_not_persist_github_token():
    workflow = _read_workflow(CI_WORKFLOW_PATH)
    test_job = _job_section(workflow, "test")
    assert "contents: read" in test_job
    _assert_no_write_permissions(test_job)
    assert "persist-credentials: false" in test_job, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
    assert "inputs.pull_request_head_sha" in test_job
    assert "ref: ${{ github.event_name == 'workflow_dispatch'" in test_job


def test_review_events_use_the_separate_trusted_workflow_context():
    workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    assert "pull_request_target:" in workflow
    assert "pull_request_review:" in workflow
    assert "github.event.review.pull_request" not in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "github.event_name == 'workflow_dispatch'" not in workflow
    assert "inputs.pull_request_number" not in workflow


def test_trusted_policy_module_has_a_preflight_before_execution():
    workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section(workflow, "ai-review-policy")
    preflight = policy_job.find("- name: Verify trusted policy runner")
    runner = policy_job.find(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    assert preflight >= 0, "The trusted module import preflight must be present"
    assert runner >= 0, "The enforce-findings step must be present"
    assert runner > preflight, "The import preflight must run before the policy module"
    assert 'run: python -c "import app.ai_review_policy;' in policy_job
    assert policy_job.count("- name: Verify trusted policy runner") == 1


def test_policy_job_uses_canonical_pull_request_head_from_github_api():
    workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section(workflow, "ai-review-policy")
    assert "id: current-pr" in policy_job
    assert "pulls/{pull_number}" in policy_job
    assert 'head_sha = (payload.get("head") or {}).get("sha", "")' in policy_job
    assert 'head_sha = (payload.get("base") or {}).get("sha", "")' not in policy_job
    assert 'output.write("head_sha=" + head_sha + chr(10))' in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
    assert "github.event.pull_request.base.sha" in policy_job
