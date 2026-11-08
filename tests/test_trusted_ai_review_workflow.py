import re
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "ai-review-policy-trusted.yml"
).read_text(encoding="utf-8")


def test_trusted_policy_uses_default_branch_workflow_run_not_pr_workflow_code():
    assert "schedule:" in WORKFLOW
    assert "push:" in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "pull_request_target:" not in WORKFLOW
    workflow_run = WORKFLOW.partition("  workflow_run:")[2].partition(
        "permissions:"
    )[0]
    assert 'workflows: ["CI"]' in workflow_run
    assert "types: [completed]" in workflow_run
    assert "branches:" not in workflow_run
    assert "branches-ignore:" not in workflow_run


def test_trusted_policy_has_exact_least_privilege_permissions():
    top_level = re.search(
        r"(?ms)^permissions:\n((?:^  [a-z-]+: [a-z]+\n)+)",
        WORKFLOW,
    )
    job_level = re.search(
        r"(?ms)^    permissions:\n((?:^      [a-z-]+: [a-z]+\n)+)",
        WORKFLOW,
    )
    assert top_level
    assert job_level
    assert re.findall(r"(?m)^  ([a-z-]+): ([a-z]+)$", top_level.group(1)) == [
        ("contents", "read")
    ]
    assert re.findall(r"(?m)^      ([a-z-]+): ([a-z]+)$", job_level.group(1)) == [
        ("contents", "read"),
        ("pull-requests", "read"),
        ("statuses", "write"),
    ]
    assert not re.search(r"\$\{\{\s*secrets\s*(?:\.|\[)", WORKFLOW, re.IGNORECASE)


def test_trusted_policy_does_not_checkout_or_execute_pull_request_code():
    assert "persist-credentials: false" in WORKFLOW
    assert "github.event.pull_request.head.sha" not in WORKFLOW
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in WORKFLOW
    assert "python -m app.ai_review_status" in WORKFLOW


def test_trusted_policy_sweeps_do_not_overlap():
    assert "group: trusted-ai-review-status-" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_trusted_policy_rechecks_after_ci_completion():
    assert 'workflows: ["CI"]' in WORKFLOW
    assert "workflow_run:" in WORKFLOW
    assert "types: [completed]" in WORKFLOW


def test_trusted_policy_workflow_run_includes_pr_ci_completions():
    workflow_run = WORKFLOW.partition("  workflow_run:")[2].partition(
        "permissions:"
    )[0]
    assert 'workflows: ["CI"]' in workflow_run
    assert "types: [completed]" in workflow_run
    assert "branches:" not in workflow_run
