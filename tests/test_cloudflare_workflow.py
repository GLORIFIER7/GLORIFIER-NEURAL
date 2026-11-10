"""Regression tests for the Neural Cloudflare deployment workflow."""

import json
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


def test_cloudflare_validation_smoke_tests_pyodide_with_asyncpg_without_ml_drivers():
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
    assert '"asyncpg==0.31.0"' in cloudflare_project
    assert 'WORKER_APP = WORKER_ROOT / "neural_app" / "app"' in preparation_script

    required_runtime_checks = (
        "Resolve Cloudflare-only dependency lock",
        "run: uv lock",
        "Upload validated Cloudflare dependency lock",
        "cloudflare-neural-uv-lock",
        "uv sync --locked --group dev --no-install-project",
        "Prepare Neural application source as local Worker dependency",
        "python prepare_worker.py",
        "uv run --locked pywrangler dev --ip 127.0.0.1 --port 8787",
        "test -f python_modules/app/api.py",
        "Verify Cloudflare Python Worker runtime startup including asyncpg",
        "CLOUDFLARE_HYPERDRIVE_LOCAL_CONNECTION_STRING_NEON_READONLY",
        'importlib.util.find_spec("psycopg") is None',
        'importlib.util.find_spec("pg8000") is not None',
        'importlib.util.find_spec("asyncpg") is not None',
        'importlib.util.find_spec("torch") is None',
        "http://127.0.0.1:8787/health",
        "bash ./worker-build.sh --prepare-only",
        "npx wrangler deploy --dry-run",
        "bash ./worker-build.sh deploy",
    )
    for check in required_runtime_checks:
        assert check in workflow, f"Cloudflare validation is missing runtime check: {check}"

    # Dependabot may update the immutable action commit; pinning is the invariant.
    for artifact_action in ("upload-artifact", "download-artifact"):
        action_pin = re.search(
            rf"(?m)^\s+uses:\s+actions/{re.escape(artifact_action)}@[0-9a-f]{{40}}(?:\s+#.*)?$",
            workflow,
        )
        assert action_pin is not None, (
            f"Cloudflare workflow must pin actions/{artifact_action} to an immutable SHA"
        )

    assert "contents: write" not in workflow
    assert "git push origin" not in workflow
    assert "Verify committed Cloudflare dependency lock" not in workflow


def test_cloudflare_build_script_removes_host_venvs_before_wrangler_upload():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "worker-build.sh"
    )
    script = script_path.read_text(encoding="utf-8")

    assert "python prepare_worker.py" in script
    assert "uv run --locked pywrangler sync" in script
    assert "rm -rf -- .venv .venv-workers" in script
    assert 'exec npx wrangler "$mode"' in script
    assert "preview|deploy|--prepare-only" in script
    assert "--prepare-only" in script


def test_cloudflare_worker_preview_urls_are_explicitly_disabled():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "wrangler.jsonc"
    )
    config = config_path.read_text(encoding="utf-8")

    assert re.search(r'"preview_urls"\s*:\s*false', config), (
        "Production Worker preview URLs must be explicitly disabled"
    )



def test_cloudflare_worker_uses_native_rate_limit_binding():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "wrangler.jsonc"
    )
    config = config_path.read_text(encoding="utf-8")
    api_path = config_path.parents[1] / "app" / "api.py"
    api_source = api_path.read_text(encoding="utf-8")

    assert '"name": "GLORIFIER_RATE_LIMITER"' in config
    assert '"namespace_id": "47041104"' in config
    assert '"name": "GLORIFIER_READINESS_LIMITER"' in config
    assert '"namespace_id": "47041105"' in config
    assert '"limit": 10' in config
    assert '"limit": 60' in config
    assert '"period": 60' in config
    assert "GLORIFIER_RATE_LIMITER" in api_source
    assert "GLORIFIER_READINESS_LIMITER" in api_source
    assert "await rate_limit_binding.limit" in api_source


def test_cloudflare_worker_binds_existing_readonly_neon_hyperdrive():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "wrangler.jsonc"
    )
    config = config_path.read_text(encoding="utf-8")

    assert '"binding": "NEON_READONLY"' in config
    assert '"id": "eff847b6c3c64488a989f1fa67d966a0"' in config
    assert '"GLORIFIER_NEON_CONNECTIVITY_ENABLED": "true"' in config


def test_cloudflare_workflow_preflights_api_and_internal_service_secrets_and_smokes_safe_mode_truthfully():
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "cloudflare-neural-worker.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "Verify required Neural API and internal service tokens are provisioned before publishing" in workflow
    assert "/workers/scripts/glorifier-neural/secrets" in workflow
    assert 'required_secrets = {"GLORIFIER_API_TOKEN", "GLORIFIER_INTERNAL_SERVICE_TOKEN"}' in workflow
    assert "missing_secrets = sorted(required_secrets.difference(names))" in workflow
    assert "Required Neural API and internal service token secrets are present; their values were not read." in workflow

    assert "  smoke:" in workflow
    assert "needs: [validate, deploy]" in workflow
    assert "/health" in workflow
    assert "/ready" in workflow
    assert "Verify live readiness or explicitly configured provider-disabled safe mode" in workflow
    assert "cloudflare/deployment_smoke.py" in workflow
    assert "--health-file /tmp/neural-health.json" in workflow
    assert "--readiness-file /tmp/neural-ready.json" in workflow
    assert "--readiness-status" in workflow


def test_cloudflare_worker_excludes_duplicate_entry_point_metadata():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "wrangler.jsonc"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    excluded = config.get("python_modules", {}).get("exclude", [])

    assert "**/*.dist-info/*.txt" in excluded, (
        "Wrangler must not add duplicate optional Python distribution text metadata"
    )
    assert "**/*.dist-info/METADATA" not in excluded, (
        "Keep package METADATA available for runtime version and package inspection"
    )


def test_cloudflare_smoke_only_runs_after_manual_production_deployment():
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "cloudflare-neural-worker.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")
    smoke_job = re.search(
        r"(?ms)^  smoke:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    assert smoke_job is not None, "Cloudflare production smoke job must exist"
    smoke = smoke_job.group(1)

    assert "needs: [validate, deploy]" in smoke
    assert "timeout-minutes: 20" in smoke
    assert "github.event_name == 'workflow_dispatch'" in smoke
    assert "inputs.deploy == true" in smoke
    assert "github.ref == 'refs/heads/main'" in smoke
    assert "needs.validate.result == 'success'" in smoke
    assert "needs.deploy.result == 'success'" in smoke
    assert "github.event_name == 'push'" not in smoke, (
        "Ordinary pushes must not treat validation-only Workers Builds as a production deployment"
    )
    assert "Wait for Cloudflare Workers Builds production deployment" not in smoke
    assert "Workers Builds: glorifier-neural" not in smoke
    assert "deployed this exact main commit successfully" not in smoke
    assert "checks: read" not in workflow, (
        "The workflow no longer polls check runs and must not request checks:read"
    )


def test_readme_describes_workers_builds_as_validation_only():
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    readme = readme_path.read_text(encoding="utf-8")

    assert "bash ./worker-build.sh --prepare-only" in readme
    assert "workflow_dispatch" in readme
    assert "automatic `main`-branch production deployment" not in readme
    assert "A separate manual GitHub Actions" not in readme
    assert "main-branch production deployment configuration remains unchanged" not in readme


def test_cloudflare_worker_disables_provider_egress_and_inference_by_default():
    config_path = (
        Path(__file__).resolve().parents[1]
        / "cloudflare"
        / "wrangler.jsonc"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    variables = config.get("vars", {})

    assert variables.get("GLORIFIER_PROVIDER") == "openai"
    assert variables.get("GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS") == "false"
    assert variables.get("GLORIFIER_ENABLE_INFERENCE", "false").casefold() == "false"
