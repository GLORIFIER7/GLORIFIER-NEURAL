"""Regression tests for least-privilege CI credentials on untrusted PR code."""

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "ci.yml"
).read_text(encoding="utf-8")


def _job_section(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        WORKFLOW,
    )
    assert match, f"CI job {name!r} must exist"
    return match.group(1)


def test_pull_requests_read_permission_is_limited_to_policy_job():
    top_level_permissions = re.search(
        r"(?ms)^permissions:\n((?:^  [^\n]+\n)+)",
        WORKFLOW,
    )
    assert top_level_permissions, "Workflow-level permissions must be explicit"
    assert "pull-requests:" not in top_level_permissions.group(1)

    policy_job = _job_section("ai-review-policy")
    assert re.search(r"(?m)^      pull-requests: read$", policy_job)


def test_untrusted_test_job_does_not_persist_github_token():
    test_job = _job_section("test")
    checkout = re.search(
        r"(?ms)^      - uses: actions/checkout@[^\n]+\n"
        r"        with:\n"
        r"          persist-credentials: false\s*$",
        test_job,
    )
    assert checkout, (
        "The test job executes pull-request-controlled code; "
        "actions/checkout must not persist GITHUB_TOKEN credentials"
    )
