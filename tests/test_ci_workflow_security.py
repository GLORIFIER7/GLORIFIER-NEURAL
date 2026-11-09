"""Regression tests for least-privilege CI and trusted PR-review policy."""

from pathlib import Path
import re


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CI_WORKFLOW_PATH = WORKFLOWS / "ci.yml"
TRUSTED_POLICY_WORKFLOW_PATH = WORKFLOWS / "trusted-ai-review-policy.yml"


def _read_workflow(path: Path) -> str:
    assert path.is_file(), f"Required workflow file is missing: {path.name}"
    return path.read_text(encoding="utf-8")


def _job_sections(workflow: str) -> dict[str, str]:
    matches = re.finditer(
        r"(?ms)^  ([a-z0-9_-]+):\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return {match.group(1): match.group(2) for match in matches}


def _job_section(name: str, workflow: str) -> str:
    jobs = _job_sections(workflow)
    assert name in jobs, f"CI job {name!r} must exist"
    return jobs[name]


def _assert_no_write_permissions(scope: str) -> None:
    assert not re.search(
        r"(?mi)^\s*(?:[a-z0-9_-]+:\s*write|write-all\s*$)",
        scope,
    ), "Write-scoped GitHub permissions are not permitted in this workflow scope"


def _assert_all_permission_scopes_are_read_only(workflow: str) -> None:
    top_level = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        workflow,
    )
    if top_level:
        _assert_no_write_permissions(top_level.group(1))
    for section in _job_sections(workflow).values():
        job_permissions = re.search(
            r"(?ms)^    permissions:\n((?:^      [^\n]+\n)+)",
            section,
        )
        if job_permissions:
            _assert_no_write_permissions(job_permissions.group(1))


def _event_types(workflow: str, event: str) -> set[str]:
    match = re.search(
        rf"(?m)^  {re.escape(event)}:\n    types: \[([^\]]+)\]",
        workflow,
    )
    assert match, f"{event} activity types must be explicit"
    return {item.strip() for item in match.group(1).split(",")}


def test_pull_requests_read_permission_is_limited_to_trusted_policy_workflow():
    ci_workflow = _read_workflow(CI_WORKFLOW_PATH)
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    ci_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)", ci_workflow
    )
    assert ci_permissions, "CI workflow-level permissions must be explicit"
    assert re.search(r"(?m)^  contents: read$", ci_permissions.group(1))
    assert "pull-requests:" not in ci_permissions.group(1)

    policy_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)", trusted_workflow
    )
    assert policy_permissions, "Trusted policy permissions must be explicit"
    assert re.search(r"(?m)^  contents: read$", policy_permissions.group(1))
    assert re.search(r"(?m)^  pull-requests: read$", policy_permissions.group(1))

    # Job-level permissions override workflow-level grants in GitHub Actions.
    # Inspect every permission scope in both workflows, not just the top level.
    _assert_all_permission_scopes_are_read_only(trusted_workflow)

    policy_job = _job_section("ai-review-policy", trusted_workflow)
    assert "ref: ${{ github.event.pull_request.base.sha }}" in policy_job
    assert "persist-credentials: false" in policy_job


def test_untrusted_test_job_does_not_persist_github_token():
    ci_workflow = _read_workflow(CI_WORKFLOW_PATH)
    test_job = _job_section("test", ci_workflow)
    _assert_no_write_permissions(test_job)
    assert "persist-credentials: false" in test_job, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
    assert "inputs.pull_request_head_sha" in test_job
    assert "ref: ${{ github.event_name == 'workflow_dispatch'" in test_job
    assert "pull-requests:" not in test_job


def test_review_events_use_trusted_base_context_and_documented_payload():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    assert {"opened", "reopened", "synchronize", "ready_for_review"} <= _event_types(
        trusted_workflow, "pull_request_target"
    )
    assert {"submitted", "edited", "dismissed"} <= _event_types(
        trusted_workflow, "pull_request_review"
    )
    assert "github.event.review.pull_request" not in policy_job
    assert "github.event.pull_request.base.sha" in policy_job
    assert "PR_NUMBER: ${{ github.event.pull_request.number }}" in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job


def test_trusted_policy_module_has_a_preflight_before_execution():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    preflight = policy_job.find("- name: Verify trusted policy runner")
    runner = policy_job.find(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    assert preflight >= 0, "The trusted module import preflight must be present"
    assert runner >= 0, "The policy enforcement step must be present"
    assert runner > preflight, "The import preflight must run before the policy module"
    assert 'run: python -c "import app.ai_review_policy;' in policy_job
    assert policy_job.count("- name: Verify trusted policy runner") == 1


def test_policy_job_uses_canonical_pull_request_head_from_github_api():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    assert "id: current-pr" in policy_job
    assert "pulls/{pull_number}" in policy_job
    assert 'head_sha = (payload.get("head") or {}).get("sha", "")' in policy_job
    assert 'head_sha = (payload.get("base") or {}).get("sha", "")' not in policy_job
    assert 'output.write("head_sha=" + head_sha + chr(10))' in policy_job
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
