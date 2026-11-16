"""Regression tests for least-privilege CI and advisory AI-review diagnostics."""

from pathlib import Path
import re


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CI_WORKFLOW_PATH = WORKFLOWS / "ci.yml"
ADVISORY_WORKFLOW_PATH = WORKFLOWS / "ai-review-policy-trusted.yml"
RETIRED_ENFORCEMENT_WORKFLOW_PATH = WORKFLOWS / "trusted-ai-review-policy.yml"


def _read(path: Path) -> str:
    assert path.is_file(), f"Required workflow file is missing: {path.name}"
    return path.read_text(encoding="utf-8")


def _job_sections(workflow: str) -> dict[str, str]:
    jobs_match = re.search(r"(?ms)^jobs:\n(.*)\Z", workflow)
    assert jobs_match, "Workflow must define a jobs section"
    matches = re.finditer(
        r"(?ms)^  ([a-z0-9_-]+):\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        jobs_match.group(1),
    )
    return {match.group(1): match.group(2) for match in matches}


def test_ci_has_no_formal_ai_review_enforcement():
    workflow = _read(CI_WORKFLOW_PATH)

    assert "ai-review-policy:" not in workflow
    assert "AI Review Policy" not in workflow
    assert "pull_request_review:" not in workflow
    assert not RETIRED_ENFORCEMENT_WORKFLOW_PATH.exists()


def test_ai_review_status_workflow_is_advisory_and_status_only():
    workflow = _read(ADVISORY_WORKFLOW_PATH)

    assert "name: AI Review Status Diagnostics" in workflow
    assert "python -m app.ai_review_status" in workflow
    assert "statuses: write" in workflow
    assert "checks: write" not in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "Enforce both AI reviewer findings" not in workflow

    jobs = _job_sections(workflow)
    assert set(jobs) == {"publish-trusted-policy-status"}
    assert "statuses: write" in jobs["publish-trusted-policy-status"]


def test_untrusted_ci_test_job_has_read_only_permissions_and_immutable_dispatch():
    workflow = _read(CI_WORKFLOW_PATH)
    jobs = _job_sections(workflow)

    assert "test" in jobs
    test_job = jobs["test"]
    assert "contents: read" in test_job
    assert "contents: write" not in test_job
    assert "packages: write" not in test_job
    assert "persist-credentials: false" in test_job
    assert "inputs.pull_request_head_sha" in test_job
    assert "inputs.pull_request_number" in test_job


def test_container_publisher_is_main_push_only_and_waits_for_tests():
    workflow = _read(CI_WORKFLOW_PATH)
    jobs = _job_sections(workflow)
    assert "publish-container" in jobs

    publisher = jobs["publish-container"]
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in publisher
    assert "needs: [test]" in publisher
    permissions = re.search(
        r"(?ms)^    permissions:\n((?:^      [^\n]+\n)+)",
        publisher,
    )
    assert permissions
    assert set(
        re.findall(r"(?m)^      ([a-z-]+): (read|write)$", permissions.group(1))
    ) == {("contents", "read"), ("packages", "write")}
    assert "docker push" in publisher


def test_dependency_audit_targets_the_locked_export_not_the_editable_project():
    workflow = _read(CI_WORKFLOW_PATH)
    jobs = _job_sections(workflow)
    test_job = jobs["test"]
    audit_step = (
        test_job.split("- name: Audit Python dependencies", 1)[1]
        .split("- name:", 1)[0]
    )

    assert "uvx --from pip-audit==2.9.0 pip-audit -r /tmp/requirements.txt" in audit_step
    editable_install = next(
        line for line in test_job.splitlines()
        if "pip install" in line and "-e ." in line
    )
    assert "--no-build-isolation" not in editable_install


def test_disposable_postgres_service_image_is_pinned_by_digest():
    workflow = _read(WORKFLOWS / "database-integration.yml")

    assert (
        "image: postgres:16@sha256:"
        "63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9"
    ) in workflow
    assert "image: postgres:16\n" not in workflow


def test_ai_review_document_matches_advisory_only_workflow_and_live_ruleset_readback():
    document = _read(Path(__file__).resolve().parents[1] / "docs" / "AI_REVIEW_POLICY.md")

    assert "advisory only" in document.casefold()
    assert "former blocking" in document.casefold()
    assert "no required status-check rule is configured" in document.casefold()
    assert "current_user_can_bypass: always" in document
    assert "27086549" in document
    assert "no `codeowners` file" in document.casefold()
    assert "code-owner coverage is not verified" in document.casefold()


def test_lockfile_verifier_job_has_a_bounded_timeout():
    workflow = _read(WORKFLOWS / "verify-lockfile.yml")

    assert "  verify:\n    runs-on: ubuntu-latest\n    timeout-minutes: 10" in workflow


def test_production_readiness_runbook_matches_current_ruleset_and_safe_mode():
    document = _read(Path(__file__).resolve().parents[1] / "docs" / "PRODUCTION_READINESS.md")

    assert "NEURAL ruleset 27086549" in document
    assert "test (3.11)" in document
    assert "test (3.12)" in document
    assert "signed commits" in document.casefold()
    assert "AI Review Policy" in document
    assert "advisory only" in document.casefold()
    assert "GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS=false" in document
    assert "GLORIFIER_ENABLE_INFERENCE=false" in document
    assert "GLORIFIER_PAID_INFERENCE_AUTHORIZED=false" in document
    assert "code-owner coverage is NOT VERIFIED" in document


def test_postgres_service_digest_has_a_documented_manual_refresh_process():
    document = _read(Path(__file__).resolve().parents[1] / "docs" / "PRODUCTION_READINESS.md")

    assert "Disposable PostgreSQL image digest" in document
    assert "database-integration.yml" in document
    assert "test_ci_workflow_security.py" in document
    assert "63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9" in document


def test_codeql_actions_use_the_verified_release_pin():
    workflow = _read(WORKFLOWS / "codeql.yml")
    lockfile = _read(WORKFLOWS / "actions.lock")

    assert workflow.count(
        "github/codeql-action/init@33d7b85da1a04171e211befe2c739303b9a4c066 # v4.39.3"
    ) == 1
    assert workflow.count(
        "github/codeql-action/analyze@33d7b85da1a04171e211befe2c739303b9a4c066 # v4.39.3"
    ) == 1
    assert "'github/codeql-action@33d7b85da1a04171e211befe2c739303b9a4c066'" in lockfile
    assert "'github/codeql-action@v4.39.3'" in lockfile
