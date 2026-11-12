"""Regression tests for the single trusted AI-review enforcement workflow."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
TRUSTED_WORKFLOW = "trusted-ai-review-policy.yml"


def _top_level_block(workflow: str, section: str) -> list[str]:
    """Return a top-level YAML block without assuming a particular indent width."""
    lines = workflow.splitlines()
    header = re.compile(rf"^( *){re.escape(section)}\s*:\s*(?:#.*)?$")
    start = next(
        (index for index, line in enumerate(lines) if header.fullmatch(line)),
        None,
    )
    assert start is not None, f"Workflow is missing its top-level {section!r} block"
    header_indent = len(lines[start]) - len(lines[start].lstrip(" "))
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.lstrip().startswith("#"):
            indent = len(line) - len(line.lstrip(" "))
            if indent <= header_indent:
                break
        block.append(line)
    return block


def _section_keys(workflow: str, section: str) -> set[str]:
    """Return direct-child mapping keys, handling any consistent YAML indentation."""
    block = _top_level_block(workflow, section)
    candidates = []
    for line in block:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        match = re.match(r"^([^:#][^:]*):(?:\s*(?:#.*)?)?$", line.strip())
        if match:
            candidates.append((indent, match.group(1).strip().strip("'\"")))
    if not candidates:
        return set()
    direct_indent = min(indent for indent, _ in candidates)
    return {key for indent, key in candidates if indent == direct_indent}


def _job_section(workflow: str, name: str) -> str:
    lines = workflow.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line == f"  {name}:"),
        None,
    )
    assert start is not None, f"Workflow is missing job {name!r}"
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _read_workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_section_keys_are_independent_of_indentation_width():
    for indent in (2, 4, 6):
        prefix = " " * indent
        nested = " " * (indent + 2)
        workflow = "\n".join(
            [
                "on:",
                f"{prefix}pull_request_target:",
                f"{nested}types: [opened]",
                f"{prefix}workflow_dispatch:",
                f"{nested}inputs:",
                f"{nested}  sha:",
                f"{nested}    required: true",
                "jobs:",
            ]
        )
        assert _section_keys(workflow, "on") == {
            "pull_request_target",
            "workflow_dispatch",
        }


def test_only_trusted_base_workflow_enforces_ai_review_policy():
    ci = _read_workflow("ci.yml")
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    assert "ai-review-policy" not in _section_keys(ci, "jobs")
    assert _section_keys(trusted, "jobs") >= {"ai-review-policy", "publish-dispatch-result"}
    for path in WORKFLOWS.rglob("*.y*ml"):
        if path.name == TRUSTED_WORKFLOW:
            continue
        source = path.read_text(encoding="utf-8")
        assert "python -m app.ai_review_policy" not in source


def test_policy_code_is_loaded_from_main_and_never_checks_out_pr_code():
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    policy = _job_section(trusted, "ai-review-policy")
    assert "ref: main" in policy
    assert "persist-credentials: false" in policy
    assert "github.event.pull_request.head.sha" not in policy
    assert "github.event.pull_request.base.sha" not in policy
    assert "github.event.review.pull_request.base.sha" not in policy


def test_policy_enforcement_requires_successful_canonical_head_resolution():
    policy = _job_section(_read_workflow(TRUSTED_WORKFLOW), "ai-review-policy")
    resolver = policy.index("- name: Resolve canonical PR head SHA from GitHub")
    enforcement = policy.index(
        "- name: Enforce both AI reviewer findings on the exact current PR head"
    )
    guard = policy.index("if: steps.current-pr.outcome == 'success'", enforcement)
    assert resolver < enforcement < guard
    assert "id: current-pr" in policy[resolver:enforcement]
    assert "PR_HEAD_SHA: ${{ steps.current-pr.outputs.head_sha }}" in policy[enforcement:]


def test_review_event_resolves_canonical_pull_request_number():
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    expression = (
        "github.event_name == 'workflow_dispatch' && inputs.pull_request_number "
        "|| (github.event_name == 'pull_request_review' && "
        "github.event.review.pull_request.number) "
        "|| github.event.pull_request.number"
    )
    assert expression in trusted.split("\nconcurrency:", 1)[1]
    assert expression in _job_section(trusted, "ai-review-policy")
    assert "pull_request_target:" in trusted
    assert "pull_request_review:" in trusted


def test_policy_result_is_published_on_current_pr_head_for_all_pr_event_paths():
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    publisher = _job_section(trusted, "publish-dispatch-result")
    assert "github.event_name != 'workflow_dispatch'" in publisher
    assert "github.ref == 'refs/heads/main'" in publisher
    assert "always()" in publisher
    assert "checks: write" in publisher
    assert "needs.ai-review-policy.outputs.pr_head_sha" in publisher
    assert "needs.ai-review-policy.result" in publisher
    assert 'current_head_sha = (pr.get("head") or {}).get("sha", "")' in publisher
    assert '"head_sha": current_head_sha' in publisher
    assert "policy_head_matches" in publisher
    assert 'if policy_result == "success" and policy_head_matches' in publisher
    assert "PR_NUMBER: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_number || (github.event_name == 'pull_request_review' && github.event.review.pull_request.number) || github.event.pull_request.number }}" in publisher
    assert "EXPECTED_PR_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_head_sha || '' }}" in publisher


def test_publisher_reports_network_errors_without_bare_exception_swallowing():
    publisher = _job_section(_read_workflow(TRUSTED_WORKFLOW), "publish-dispatch-result")
    assert "except urllib.error.HTTPError as exc:" in publisher
    assert "except (urllib.error.URLError, TimeoutError, OSError)" in publisher
    assert "GitHub check publication failed (HTTP" in publisher
    assert "GitHub check publication is unavailable." in publisher
    assert "except Exception:" not in publisher
    assert "pass" not in publisher


def test_generated_pr_dispatch_emits_diagnostics_for_invalid_identifiers():
    maintenance = _read_workflow("ai-maintenance.yml")
    start = maintenance.index(
        "- name: Dispatch trusted CI and AI review for the exact PR head"
    )
    end = maintenance.find("\n      - name:", start + 1)
    step = maintenance[start:] if end < 0 else maintenance[start:end]
    sha_check = '[[ "$pr_head_sha" =~ ^[0-9a-fA-F]{40}$ ]]'
    number_check = '[[ "$pr_number" =~ ^[1-9][0-9]*$ ]]'
    sha_pos = step.index(sha_check)
    number_pos = step.index(number_check)
    assert "::error::The resolved PR head SHA" in step[sha_pos:number_pos]
    assert "exit 1" in step[sha_pos:number_pos]
    assert "::error::The resolved PR number" in step[number_pos:]
    assert "exit 1" in step[number_pos:]


def test_publisher_requires_exact_expected_sha_only_for_manual_dispatch():
    publisher = _job_section(_read_workflow(TRUSTED_WORKFLOW), "publish-dispatch-result")
    guard = (
        'if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch" '
        'and not re.fullmatch(r"[0-9a-fA-F]{40}", expected_head_sha):'
    )
    assert guard in publisher

    # Validate the guard inputs structurally; never execute text read from YAML.
    publisher_env = publisher.split("        env:", 1)[1].split("        run: |", 1)[0]
    assert "GITHUB_EVENT_NAME: ${{ github.event_name }}" in publisher_env
    assert (
        "EXPECTED_PR_HEAD_SHA: ${{ github.event_name == 'workflow_dispatch' && inputs.pull_request_head_sha || '' }}"
        in publisher_env
    )


def test_workflow_dispatch_provides_manual_reevaluation_fallback():
    """Regression: workflow_dispatch is the trusted manual re-evaluation path."""
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    maintenance = _read_workflow("ai-maintenance.yml")

    events = _section_keys(trusted, "on")
    assert "workflow_dispatch" in events
    policy_job = _job_section(trusted, "ai-review-policy")
    assert "github.ref == 'refs/heads/main'" in policy_job
    assert "pull_request_number:" in trusted
    assert "pull_request_head_sha:" in trusted
    assert "expected_head_sha.casefold() != head_sha.casefold()" in policy_job

    publisher = _job_section(trusted, "publish-dispatch-result")
    mismatch_start = publisher.index(
        "if expected_head_sha and current_head_sha.casefold() != expected_head_sha.casefold():"
    )
    next_step = publisher.index("\n          policy_head_matches =", mismatch_start)
    mismatch_branch = publisher[mismatch_start:next_step]
    assert "raise SystemExit(" in mismatch_branch
    assert "check-runs" not in mismatch_branch
    assert 'method="POST"' not in mismatch_branch

    dispatch_start = maintenance.index(
        "- name: Dispatch trusted CI and AI review for the exact PR head"
    )
    dispatch_end = maintenance.find("\n      - name:", dispatch_start + 1)
    dispatch_step = (
        maintenance[dispatch_start:]
        if dispatch_end < 0
        else maintenance[dispatch_start:dispatch_end]
    )
    assert "gh workflow run trusted-ai-review-policy.yml --ref main" in dispatch_step
    assert '--field pull_request_number="$pr_number"' in dispatch_step
    assert '--field pull_request_head_sha="$pr_head_sha"' in dispatch_step
    assert "ref: main" in policy_job
    assert "github.event.pull_request.head.sha" not in policy_job
    assert "github.event.pull_request.base.sha" not in policy_job


def test_manual_exact_head_dispatch_is_the_documented_review_re_evaluation_fallback():
    workflow = _read_workflow(TRUSTED_WORKFLOW)
    guide = (ROOT / "docs" / "AI_REVIEW_POLICY.md").read_text(encoding="utf-8")
    dispatch = _top_level_block(workflow, "workflow_dispatch")
    dispatch_text = "\n".join(dispatch)
    policy_job = _job_section(workflow, "ai-review-policy")
    publisher = _job_section(workflow, "publish-dispatch-result")

    assert "pull_request_number:" in dispatch_text
    assert "pull_request_head_sha:" in dispatch_text
    assert dispatch_text.count("required: true") >= 2
    assert "GITHUB_EVENT_NAME" in policy_job
    assert "workflow_dispatch" in policy_job
    assert "github.ref == 'refs/heads/main'" in policy_job
    assert "EXPECTED_PR_HEAD_SHA" in policy_job
    assert "current_head_sha" in publisher
    assert "expected_head_sha" in publisher

    # GitHub's pull_request_review_thread webhook is not an Actions workflow trigger.
    assert "pull_request_review_thread" not in _section_keys(workflow, "on")

    # The manual exact-head fallback must be documented for a resolved blocker.
    assert "Manual re-evaluation fallback" in guide
    assert "copy the current PR head SHA" in guide





def test_evaluator_and_canonical_publisher_have_distinct_check_names():
    """The required context must identify only the canonical publisher check."""
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    evaluator = _job_section(trusted, "ai-review-policy")
    publisher = _job_section(trusted, "publish-dispatch-result")

    assert "    name: Evaluate AI review evidence" in evaluator
    assert '"name": "Trusted AI Review Policy"' in publisher
    assert "    name: Trusted AI Review Policy" not in evaluator


def test_runbook_matches_live_ruleset_and_documents_check_identity_gap():
    guide = (ROOT / "docs" / "AI_REVIEW_POLICY.md").read_text(encoding="utf-8")

    assert "Current repository ruleset — read-back on 2026-11-12" in guide
    assert "`GLORIFIER-NEURAL main protection1`" in guide
    assert "`27086549`" in guide
    assert "`test (3.11)`" in guide
    assert "`test (3.12)`" in guide
    assert "`Trusted AI Review Policy`" in guide
    assert "GitHub Actions" in guide
    assert "15368" in guide
    assert "required contexts share the GitHub Actions source identity" in guide


def test_inline_review_comment_events_trigger_policy_reevaluation():
    """Inline review-comment changes must trigger a fresh trusted policy check."""
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    guide = (ROOT / "docs" / "AI_REVIEW_POLICY.md").read_text(encoding="utf-8")
    events = _section_keys(trusted, "on")

    assert "pull_request_review_comment" in events
    on_block = "\n".join(_top_level_block(trusted, "on"))
    prc_idx = on_block.find("pull_request_review_comment")
    assert prc_idx >= 0
    prc_block = on_block[prc_idx:]
    assert "created" in prc_block
    assert "edited" in prc_block
    assert "deleted" in prc_block

    pr_number_expression = (
        "github.event_name == 'workflow_dispatch' && inputs.pull_request_number "
        "|| (github.event_name == 'pull_request_review' && "
        "github.event.review.pull_request.number) "
        "|| github.event.pull_request.number"
    )
    concurrency = trusted.split("\nconcurrency:", 1)[1]
    assert pr_number_expression in concurrency
    publisher = _job_section(trusted, "publish-dispatch-result")
    assert pr_number_expression in publisher
    assert "zero Actions policies" in guide
