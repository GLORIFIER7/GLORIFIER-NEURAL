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
    repository_root = workflow_path.parents[2]
    cloudflare_project = (repository_root / "cloudflare" / "pyproject.toml").read_text(encoding="utf-8")
    package_project = (repository_root / "cloudflare" / "neural_app" / "pyproject.toml").read_text(encoding="utf-8")
    preparation_script = (repository_root / "cloudflare" / "prepare_worker.py").read_text(encoding="utf-8")

    assert 'glorifier-neural-app = { path = "neural_app", editable = false }' in cloudflare_project
    assert 'include = ["app*"]' in package_project
    assert 'WORKER_APP = WORKER_ROOT / "neural_app" / "app"' in preparation_script

    required_runtime_checks = (
        "uv sync --locked --group dev --no-install-project",
        "Prepare Neural application source as local Worker dependency",
        "python prepare_worker.py",
        'glorifier-neural-app = { path = "neural_app", editable = false }',
        "uv run --locked pywrangler dev --ip 127.0.0.1 --port 8787",
        "test -f python_modules/app/api.py",
        "Verify Cloudflare Python Worker runtime startup without optional drivers",
        'importlib.util.find_spec("psycopg") is None',
        'importlib.util.find_spec("torch") is None',
        "uv run --locked pywrangler dev --ip 127.0.0.1 --port 8787",
        "http://127.0.0.1:8787/health",
        "uv run --locked pywrangler deploy --dry-run",
    )
    for check in required_runtime_checks:
        assert check in workflow, f"Cloudflare validation is missing runtime check: {check}"
