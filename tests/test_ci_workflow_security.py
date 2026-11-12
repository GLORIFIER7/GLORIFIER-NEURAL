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


def _assert_no_write_permissions(
    scope: str, *, allowed_write_permissions: set[str] | None = None
) -> None:
    assert not re.search(
        r"(?mi)^\s*permissions:\s*write-all\s*$",
        scope,
    ), "permissions: write-all is not permitted in this workflow scope"
    writes = set(re.findall(r"(?mi)^\s*([a-z0-9_-]+):\s*write\s*$", scope))
    allowed = allowed_write_permissions or set()
    assert writes <= allowed, (
        "Unexpected write-scoped GitHub permissions are not permitted: "
        + ", ".join(sorted(writes - allowed))
    )


def _assert_all_permission_scopes_are_read_only(workflow: str) -> None:
    top_level = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        workflow,
    )
    if top_level:
        _assert_no_write_permissions(top_level.group(1))

    jobs = _job_sections(workflow)
    packages_write_jobs = []
    for job_name, section in jobs.items():
        job_permissions = re.search(
            r"(?ms)^    permissions:\n((?:^      [^\n]+\n)+)",
            section,
        )
        if not job_permissions:
            continue

        permissions = job_permissions.group(1)
        allowed = {"packages"} if job_name == "publish-container" else set()
        _assert_no_write_permissions(
            permissions,
            allowed_write_permissions=allowed,
        )

        if "packages: write" in permissions:
            packages_write_jobs.append(job_name)
            assert job_name == "publish-container"
            assert {
                line.strip()
                for line in permissions.splitlines()
                if line.strip()
            } == {"contents: read", "packages: write"}
            assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in section
            assert "needs: [test]" in section

    if "publish-container" in jobs:
        assert packages_write_jobs == ["publish-container"], (
            "Only the main-branch image publisher may receive packages: write, "
            "and only after the test job succeeds"
        )
    else:
        assert not packages_write_jobs, (
            "The trusted policy workflow must not grant package-write permissions"
        )


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
    # Job-level grants override workflow-level permissions; inspect both workflows.
    publish_job = _job_section("publish-dispatch-result", trusted_workflow)
    trusted_policy_read_only = trusted_workflow.split(
        "\n  publish-dispatch-result:", 1
    )[0]
    _assert_all_permission_scopes_are_read_only(ci_workflow)
    _assert_all_permission_scopes_are_read_only(trusted_policy_read_only)
    publish_writes = set(
        re.findall(r"(?mi)^\s*([a-z0-9_-]+):\s*write\s*$", publish_job)
    )
    assert publish_writes == {"checks"}, (
        "Only the isolated dispatch-result job may write the PR check status."
    )

    policy_job = _job_section("ai-review-policy", trusted_workflow)
    assert "ref: main" in policy_job
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
    assert "ref: ${{ steps.current-pr.outputs.head_sha || github.sha }}" in test_job
    assert "pull-requests: read" in test_job
    assert "pull-requests: write" not in test_job


def test_review_events_use_trusted_base_context_and_documented_payload():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    assert {"opened", "reopened", "synchronize", "ready_for_review"} <= _event_types(
        trusted_workflow, "pull_request_target"
    )
    assert {"submitted", "edited", "dismissed"} <= _event_types(
        trusted_workflow, "pull_request_review"
    )
    assert "github.event.review.pull_request.number" in policy_job
    assert "ref: main" in policy_job
    assert "github.event.review.pull_request.base.sha" not in policy_job
    assert "github.event.pull_request.base.sha" not in policy_job
    pr_number_expression = (
        "github.event_name == 'workflow_dispatch' && inputs.pull_request_number "
        "|| (github.event_name == 'pull_request_review' && "
        "github.event.review.pull_request.number) "
        "|| github.event.pull_request.number"
    )
    assert policy_job.count(pr_number_expression) == 2
    assert pr_number_expression in trusted_workflow.split("\nconcurrency:", 1)[1]
    assert "EXPECTED_PR_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_head_sha || '' }}" in policy_job
    assert "workflow_dispatch:" in trusted_workflow
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


def test_policy_enforcement_step_requires_resolver_success():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    enforce_start = policy_job.find(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    assert enforce_start >= 0, "Enforcement step must be present"
    # The if: guard must appear in this step before the env: block
    env_start = policy_job.find("env:", enforce_start)
    guard_start = policy_job.find(
        "if: steps.current-pr.outcome == 'success'", enforce_start
    )
    assert guard_start >= 0, (
        "The enforcement step must carry 'if: steps.current-pr.outcome == \"success\"' "
        "so a failed resolver cannot invoke the evaluator."
    )
    assert guard_start < env_start, (
        "The if: guard must appear before the env: block of the enforcement step."
    )
    # Confirm the resolver step has the id that the guard references
    resolver_start = policy_job.find("- name: Resolve canonical PR head SHA from GitHub")
    assert resolver_start >= 0
    assert "id: current-pr" in policy_job[resolver_start:enforce_start]


def test_stale_head_rejected_without_publishing_a_pr_check():
    """A mismatched dispatch must fail closed without creating a PR check."""
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    publish_job = _job_section("publish-dispatch-result", trusted_workflow)
    mismatch_start = publish_job.index(
        "if expected_head_sha and current_head_sha.casefold() != expected_head_sha.casefold():"
    )
    next_step = publish_job.index("\n          policy_head_matches =", mismatch_start)
    mismatch_branch = publish_job[mismatch_start:next_step]

    assert "raise SystemExit(" in mismatch_branch
    assert "no policy check was published" in mismatch_branch
    assert "check-runs" not in mismatch_branch
    assert "stale_summary" not in mismatch_branch
    assert "stale_payload" not in mismatch_branch
    assert "urlopen(" not in mismatch_branch


def test_matching_head_publishes_check_with_policy_result():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    publish_job = _job_section("publish-dispatch-result", trusted_workflow)
    assert "policy_head_matches" in publish_job
    assert (
        'if policy_result == "success" and policy_head_matches'
        in publish_job
    ), "Success can only be published when policy result is success and heads match."
    assert '"name": "Trusted AI Review Policy"' in publish_job
    assert "checks: write" in publish_job
    # Checks:write is the only write permission
    assert publish_job.count(": write") == 1, (
        "Only checks:write is permitted in the publish-dispatch-result job."
    )

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


def test_dispatched_trusted_policy_publishes_result_to_exact_pr_head():
    trusted_workflow = _read_workflow(TRUSTED_POLICY_WORKFLOW_PATH)
    policy_job = _job_section("ai-review-policy", trusted_workflow)
    publish_job = _job_section("publish-dispatch-result", trusted_workflow)

    assert "outputs:" in policy_job
    assert "pr_head_sha: ${{ steps.current-pr.outputs.head_sha }}" in policy_job
    assert "checks: write" in publish_job
    assert "github.event_name == 'workflow_dispatch'" in publish_job
    assert "needs.ai-review-policy.outputs.pr_head_sha" in publish_job
    assert "needs.ai-review-policy.result" in publish_job
    assert "github.ref == 'refs/heads/main'" in publish_job
    assert "needs.ai-review-policy.outputs.pr_head_sha != ''" not in publish_job
    assert "PR_NUMBER: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_number || (github.event_name == 'pull_request_review' && github.event.review.pull_request.number) || github.event.pull_request.number }}" in publish_job
    assert "EXPECTED_PR_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_head_sha || '' }}" in publish_job
    assert 'current_head_sha = (pr.get("head") or {}).get("sha", "")' in publish_job
    assert "current_head_sha.casefold() != expected_head_sha.casefold()" in publish_job
    assert "policy_head_matches" in publish_job
    assert 'https://api.github.com/repos/{repository}/check-runs' in publish_job
    assert '"name": "Trusted AI Review Policy"' in publish_job
    assert '"head_sha": current_head_sha' in publish_job
    assert '"conclusion": conclusion' in publish_job


def test_manual_dispatch_rejects_partial_pr_identity_instead_of_skipping():
    ci_workflow = _read_workflow(CI_WORKFLOW_PATH)
    test_job = _job_section("test", ci_workflow)
    validation_step = test_job.split(
        "- name: Validate manual dispatch PR identity", 1
    )[1].split("\n      - name:", 1)[0]

    # Either input activates validation; both are then mandatory. This keeps
    # normal no-input dispatch available while rejecting a partial PR request.
    assert (
        "inputs.pull_request_number != '' || inputs.pull_request_head_sha != ''"
        in validation_step
    )
    assert '[[ "$PR_NUMBER" =~ ^[1-9][0-9]*$ ]]' in validation_step
    assert '[[ "$PR_HEAD_SHA" =~ ^[0-9a-fA-F]{40}$ ]]' in validation_step
    assert "id: validate-pr-identity" in validation_step
    verification_step = test_job.split(
        "- name: Verify dispatched PR head against GitHub", 1
    )[1].split("\n      - uses: actions/checkout", 1)[0]
    assert "steps.validate-pr-identity.outcome == 'success'" in verification_step
