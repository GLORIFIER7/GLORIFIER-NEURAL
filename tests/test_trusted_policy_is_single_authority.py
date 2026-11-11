"""Regression test: trusted PR policy must not be duplicated in PR-editable CI."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _jobs(workflow: str) -> set[str]:
    return set(
        re.findall(r"(?m)^  ([a-z0-9_-]+):\s*$", workflow.split("jobs:\n", 1)[1])
    )


def test_ci_does_not_define_a_pr_editable_ai_review_gate():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    jobs = _jobs(ci)

    assert "ai-review-policy" not in jobs, (
        "AI review enforcement must be defined only in the trusted-base "
        "workflow, never in the PR-editable CI workflow."
    )
    assert "name: AI Review Policy" not in ci


def test_trusted_policy_workflow_is_the_only_policy_enforcement_source():
    trusted = (WORKFLOWS / "trusted-ai-review-policy.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request_target:" in trusted
    assert "pull_request_review:" in trusted
    assert "ref: ${{ github.event.pull_request.base.sha }}" in trusted
    assert "persist-credentials: false" in trusted
    assert "python -m app.ai_review_policy" in trusted
    assert "pull_request:" not in trusted.split("permissions:", 1)[0]
