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

    expression = guard[len("if "):-1]
    for event_name in ("pull_request_target", "pull_request_review"):
        environment = type(
            "Environment",
            (),
            {"environ": {"GITHUB_EVENT_NAME": event_name}},
        )()
        assert not eval(expression, {
            "os": environment,
            "re": re,
            "expected_head_sha": "",
        })

    dispatch_environment = type(
        "Environment",
        (),
        {"environ": {"GITHUB_EVENT_NAME": "workflow_dispatch"}},
    )()
    assert eval(expression, {
        "os": dispatch_environment,
        "re": re,
        "expected_head_sha": "",
    })
    assert not eval(expression, {
        "os": dispatch_environment,
        "re": re,
        "expected_head_sha": "a" * 40,
    })


def test_workflow_dispatch_provides_manual_reevaluation_fallback():
    """Regression: workflow_dispatch on trusted-ai-review-policy.yml is the
    documented manual re-evaluation fallback when a blocking review thread is
    resolved.

    Invariants verified:
    - The trusted workflow accepts workflow_dispatch as a trigger.
    - Dispatch is restricted to refs/heads/main (untrusted branches cannot
      dispatch it).
    - Both pull_request_number and pull_request_head_sha inputs are declared.
    - The resolver validates the dispatched SHA against the live GitHub API and
      rejects a stale SHA before the evaluator is invoked.
    - A mismatched manual-dispatch SHA fails before any check is written, so a typo or unrelated SHA cannot create a false PR merge blocker.
    - ai-maintenance dispatches the trusted workflow from main with both required
      fields, completing the generated-PR manual re-evaluation chain.
    - Policy code is always loaded from main (never from the PR head).
    """
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    maintenance = _read_workflow("ai-maintenance.yml")

    # 1. workflow_dispatch trigger must be present.
    events = _section_keys(trusted, "on")
    assert "workflow_dispatch" in events, (
        "trusted-ai-review-policy.yml must accept workflow_dispatch so operators "
        "can manually re-evaluate a PR after a blocking review thread is resolved."
    )

    # 2. Dispatch is restricted to refs/heads/main.
    policy_job = _job_section(trusted, "ai-review-policy")
    assert "github.ref == 'refs/heads/main'" in policy_job, (
        "The ai-review-policy job must restrict workflow_dispatch runs to main "
        "so only trusted base code is executed."
    )

    # 3. Both required inputs are declared in the workflow.
    assert "pull_request_number:" in trusted, (
        "pull_request_number input must be declared for manual re-evaluation dispatch."
    )
    assert "pull_request_head_sha:" in trusted, (
        "pull_request_head_sha input must be declared for manual re-evaluation dispatch."
    )

    # 4. Resolver rejects a dispatched SHA that no longer matches the live PR head.
    assert "expected_head_sha.casefold() != head_sha.casefold()" in policy_job, (
        "The resolver must reject a stale dispatched SHA so the evaluator is never "
        "invoked against a head that has since advanced."
    )

    # 5. A mismatched dispatch SHA must fail without creating a check on the PR.
    publisher = _job_section(trusted, "publish-dispatch-result")
    mismatch_start = publisher.index(
        "if expected_head_sha and current_head_sha.casefold() != expected_head_sha.casefold():"
    )
    next_step = publisher.index("\n          policy_head_matches =", mismatch_start)
    mismatch_branch = publisher[mismatch_start:next_step]
    assert "raise SystemExit(" in mismatch_branch
    assert "check-runs" not in mismatch_branch
    assert "stale_payload" not in mismatch_branch
    assert "commits?per_page=100&page=" in mismatch_branch
    assert "prior_head_found" in mismatch_branch
    assert "urlopen(" in mismatch_branch  # Read-only PR history lookup is allowed.
    assert 'method="POST"' not in mismatch_branch
    assert "urlopen(stale_request" not in mismatch_branch


    # 6. ai-maintenance dispatches the trusted workflow from main with both fields,
    #    completing the generated-PR manual re-evaluation chain.
    dispatch_start = maintenance.index(
        "- name: Dispatch trusted CI and AI review for the exact PR head"
    )
    dispatch_end = maintenance.find("\n      - name:", dispatch_start + 1)
    dispatch_step = (
        maintenance[dispatch_start:]
        if dispatch_end < 0
        else maintenance[dispatch_start:dispatch_end]
    )
    assert "gh workflow run trusted-ai-review-policy.yml --ref main \\" in dispatch_step, (
        "ai-maintenance must dispatch the trusted policy workflow from main so the "
        "generated-PR manual re-evaluation path is complete."
    )
    assert '--field pull_request_number="$pr_number"' in dispatch_step, (
        "The trusted policy dispatch must include pull_request_number."
    )
    assert '--field pull_request_head_sha="$pr_head_sha"' in dispatch_step, (
        "The trusted policy dispatch must include pull_request_head_sha."
    )

    # 7. Policy code is always loaded from main, never from the PR head.
    assert "ref: main" in policy_job, (
        "Policy code must always be checked out from main, never from the PR head."
    )
    assert "github.event.pull_request.head.sha" not in policy_job, (
        "The policy job must never check out or reference the PR head code."
    )
    assert "github.event.pull_request.base.sha" not in policy_job, (
        "The policy job must not use the PR base SHA as checkout ref; use 'main'."
    )


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
    assert "Run workflow" in guide
 
 
def test_evaluator_and_canonical_publisher_have_distinct_check_names():
    """The required context must identify only the canonical publisher check."""
    trusted = _read_workflow(TRUSTED_WORKFLOW)
    evaluator = _job_section(trusted, "ai-review-policy")
    publisher = _job_section(trusted, "publish-dispatch-result")

    assert "    name: Evaluate AI review evidence" in evaluator
    assert "    name: Trusted AI Review Policy" not in evaluator
    assert '"name": "Trusted AI Review Policy"' in publisher
