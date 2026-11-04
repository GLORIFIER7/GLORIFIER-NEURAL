"""Regression tests for the Neural Cloudflare deployment workflow."""

from pathlib import Path
import re


def test_cloudflare_production_deployment_is_restricted_to_main():
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "cloudflare-neural-worker.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    deploy_job = re.search(
        r"(?ms)^  deploy:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert deploy_job is not None, "Cloudflare production deploy job must exist"

    condition = re.search(r"(?m)^    if:\s*(.+)$", deploy_job.group(1))
    assert condition is not None, "Cloudflare production deploy job must have an explicit guard"
    expression = condition.group(1)

    assert "github.event_name == 'workflow_dispatch'" in expression
    assert "inputs.deploy == true" in expression
    assert "github.ref == 'refs/heads/main'" in expression, (
        "Production deployment must be restricted to the protected main branch"
    )


def test_cloudflare_validation_smoke_tests_pyodide_without_optional_drivers():
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "cloudflare-neural-worker.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    required_runtime_checks = (
        "uv sync --locked --group dev --no-install-project",
        "Prepare Neural application source beside the Worker entrypoint",
        "python prepare_worker.py",
        "WORKER_ROOT / \"python_modules\" / \"app\"",
        "Verify Cloudflare Python Worker runtime startup without optional drivers",
        'importlib.util.find_spec("psycopg") is None',
        'importlib.util.find_spec("torch") is None',
        "uv run --locked pywrangler dev --ip 127.0.0.1 --port 8787",
        "http://127.0.0.1:8787/health",
    )
    for check in required_runtime_checks:
        assert check in workflow, f"Cloudflare validation is missing runtime check: {check}"
