import re
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "ai-review-policy-trusted.yml"
).read_text(encoding="utf-8")


def test_trusted_policy_runs_only_from_default_branch_events():
    assert "schedule:" in WORKFLOW
    assert "push:" in WORKFLOW
    assert "branches: [main]" in WORKFLOW
    assert "pull_request:" not in WORKFLOW
    assert "pull_request_target:" not in WORKFLOW


def test_trusted_policy_writes_only_the_required_commit_status_permissions():
    assert "pull-requests: read" in WORKFLOW
    assert "statuses: write" in WORKFLOW
    assert "contents: read" in WORKFLOW
    assert "contents: write" not in WORKFLOW
    assert not re.search(r"\\$\\{\\{\\s*secrets\\s*(?:\\.|\\[)", WORKFLOW, re.IGNORECASE)


def test_trusted_policy_does_not_checkout_or_execute_pull_request_code():
    assert "persist-credentials: false" in WORKFLOW
    assert "github.event.pull_request.head.sha" not in WORKFLOW
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in WORKFLOW
    assert "python -m app.ai_review_status" in WORKFLOW
