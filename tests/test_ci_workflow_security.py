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
    matches = re.finditer(
        r"(?ms)^  ([a-z0-9_-]+):\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        workflow,
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
