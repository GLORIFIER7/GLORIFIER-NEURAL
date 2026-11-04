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


def test_cloudflare_validation_imports_the_app_without_optional_native_drivers():
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "cloudflare-neural-worker.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    required_runtime_checks = (
        "Verify Cloudflare ASGI application startup without optional drivers",
        'importlib.util.find_spec("psycopg") is None',
        'importlib.util.find_spec("torch") is None',
        "from workers import asgi",
        "from app.api import app",
        "asgi.entrypoint(app)",
    )
    for check in required_runtime_checks:
        assert check in workflow, f"Cloudflare validation is missing runtime check: {check}"
