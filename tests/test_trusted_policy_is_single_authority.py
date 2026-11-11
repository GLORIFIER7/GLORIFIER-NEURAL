"""Regression tests for the single trusted AI-review enforcement workflow."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
TRUSTED_WORKFLOW = "trusted-ai-review-policy.yml"


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



def test_section_keys_recognizes_quoted_yaml_mapping_keys():
    workflow = (
        "on:\\n"
        "  \"pull_request_review\":\\n"
        "    types: [submitted]\\n"
        "  'pull_request_target':\\n"
        "    types: [opened]\\n"
        "jobs:\\n"
    )

    assert _section_keys(workflow, "on") == {
        "pull_request_review",
        "pull_request_target",
    }

def _workflow_files() -> list[Path]:
    return sorted(
        path
        for path in WORKFLOWS.rglob("*")
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )


def _defines_review_policy_enforcement(workflow: str) -> bool:
    return (
        "python -m app.ai_review_policy" in workflow
        or re.search(r"(?m)^  ai-review-policy:\s*$", workflow) is not None
        or re.search(r"(?m)^    name:\s*(?:Trusted )?AI Review Policy\s*$", workflow)
        is not None
    )


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


def test_no_other_workflow_defines_ai_review_policy_enforcement():
    files = _workflow_files()
    policy_sources = [
        path.relative_to(WORKFLOWS).as_posix()
        for path in files
        if _defines_review_policy_enforcement(path.read_text(encoding="utf-8"))
    ]

    assert policy_sources == [TRUSTED_WORKFLOW], (
        "Exactly trusted-ai-review-policy.yml must define AI review enforcement; "
        f"found {policy_sources!r}."
    )

    for path in files:
        if path.relative_to(WORKFLOWS).as_posix() == TRUSTED_WORKFLOW:
            continue
        events = _section_keys(path.read_text(encoding="utf-8"), "on")
        assert "pull_request_review" not in events, (
            f"{path.relative_to(WORKFLOWS).as_posix()} must not handle PR review events."
        )


def test_trusted_policy_workflow_is_the_only_policy_enforcement_source():
    trusted = (WORKFLOWS / TRUSTED_WORKFLOW).read_text(encoding="utf-8")
    events = _section_keys(trusted, "on")

    assert "pull_request_target" in events
    assert "pull_request_review" in events
    assert "workflow_dispatch" in events
    assert "pull_request" not in events
    assert "pull_request_number:" in trusted
    assert "pull_request_head_sha:" in trusted
    assert "inputs.pull_request_number" in trusted
    assert "inputs.pull_request_head_sha" in trusted
    assert "EXPECTED_PR_HEAD_SHA:" in trusted
    assert "expected_head_sha.casefold() != head_sha.casefold()" in trusted
    assert "github.event_name == 'workflow_dispatch' && 'main' || github.event.pull_request.base.sha" in trusted
    assert "persist-credentials: false" in trusted
    assert "python -m app.ai_review_policy" in trusted


def test_ai_maintenance_dispatches_trusted_policy_for_the_exact_generated_pr_head():
    maintenance = (WORKFLOWS / "ai-maintenance.yml").read_text(encoding="utf-8")
    dispatch_start = maintenance.index(
        "- name: Dispatch trusted CI and AI review for the exact PR head"
    )
    dispatch_end = maintenance.find("\n      - name:", dispatch_start + 1)
    dispatch_step = (
        maintenance[dispatch_start:]
        if dispatch_end < 0
        else maintenance[dispatch_start:dispatch_end]
    )

    assert '[[ "$pr_head_sha" =~ ^[0-9a-fA-F]{40}$ ]]' in dispatch_step
    assert 'pr_number="$(gh pr view "$PR_BRANCH" --json number --jq \'.number\')"' in dispatch_step
    assert 'gh workflow run ci.yml --ref main \\' in dispatch_step
    assert 'gh workflow run trusted-ai-review-policy.yml --ref main \\' in dispatch_step
    assert dispatch_step.count('--field pull_request_number="$pr_number"') == 2
    assert dispatch_step.count('--field pull_request_head_sha="$pr_head_sha"') == 2
    assert "gh pr merge" not in dispatch_step
    assert "--auto" not in dispatch_step

def test_pr_identity_lookup_fails_closed_on_github_api_errors():
    trusted = (WORKFLOWS / TRUSTED_WORKFLOW).read_text(encoding="utf-8")
    resolver = trusted.split(
        "      - name: Resolve canonical PR head SHA from GitHub", 1
    )[1].split("\n      - name: Enforce", 1)[0]

    assert "import urllib.error" in resolver
    assert "except urllib.error.HTTPError as exc:" in resolver
    assert "except (urllib.error.URLError, TimeoutError, OSError):" in resolver
    assert "except (json.JSONDecodeError, UnicodeDecodeError):" in resolver
    assert "GitHub PR identity lookup failed (HTTP" in resolver
    assert "GitHub PR identity lookup is unavailable." in resolver


def test_dispatch_check_publication_fails_closed_on_github_api_errors():
    trusted = (WORKFLOWS / TRUSTED_WORKFLOW).read_text(encoding="utf-8")
    publisher = trusted.split("  publish-dispatch-result:", 1)[1]

    assert "import urllib.error" in publisher
    assert "except urllib.error.HTTPError as exc:" in publisher
    assert "except (urllib.error.URLError, TimeoutError, OSError):" in publisher
    assert "except (json.JSONDecodeError, UnicodeDecodeError):" in publisher
    assert "GitHub check publication failed (HTTP" in publisher
    assert "GitHub check publication is unavailable." in publisher

def test_review_event_resolves_pull_request_number_from_review_payload():
    trusted = (WORKFLOWS / TRUSTED_WORKFLOW).read_text(encoding="utf-8")
    expression = (
        "github.event_name == 'workflow_dispatch' && inputs.pull_request_number "
        "|| (github.event_name == 'pull_request_review' && "
        "github.event.review.pull_request.number) "
        "|| github.event.pull_request.number"
    )

    assert trusted.count(expression) == 3
