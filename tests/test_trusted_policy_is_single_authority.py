"""Regression test: trusted PR policy must not be duplicated in PR-editable CI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _top_level_block(workflow: str, section: str) -> list[str]:
    lines = workflow.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.rstrip() == f"{section}:"),
        None,
    )
    assert start is not None, f"Workflow is missing its top-level {section!r} block"

    block = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        block.append(line)
    return block


def _section_keys(workflow: str, section: str) -> set[str]:
    return {
        line.strip()[:-1]
        for line in _top_level_block(workflow, section)
        if line.startswith("  ")
        and not line.startswith("    ")
        and line.strip().endswith(":")
    }


def test_ci_does_not_define_a_pr_editable_ai_review_gate():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    jobs = _section_keys(ci, "jobs")
    events = _section_keys(ci, "on")

    assert "ai-review-policy" not in jobs, (
        "AI review enforcement must be defined only in the trusted-base "
        "workflow, never in the PR-editable CI workflow."
    )
    assert "name: AI Review Policy" not in ci
    assert "pull_request_review" not in events, (
        "PR review events must be handled only by the trusted policy workflow."
    )


def test_trusted_policy_workflow_is_the_only_policy_enforcement_source():
    trusted = (WORKFLOWS / "trusted-ai-review-policy.yml").read_text(
        encoding="utf-8"
    )
    events = _section_keys(trusted, "on")

    assert "pull_request_target" in events
    assert "pull_request_review" in events
    assert "pull_request" not in events
    assert "ref: ${{ github.event.pull_request.base.sha }}" in trusted
    assert "persist-credentials: false" in trusted
    assert "python -m app.ai_review_policy" in trusted
