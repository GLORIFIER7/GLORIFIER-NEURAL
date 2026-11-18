"""Tests for fail-closed Cloudflare deployment preflight and smoke checks."""

import importlib.util
from pathlib import Path

import pytest

_smoke_path = Path(__file__).resolve().parents[1] / "cloudflare" / "deployment_smoke.py"
_smoke_spec = importlib.util.spec_from_file_location("deployment_smoke", _smoke_path)
if _smoke_spec is None or _smoke_spec.loader is None:
    raise ImportError("Unable to load Cloudflare deployment smoke helper.")
_smoke_module = importlib.util.module_from_spec(_smoke_spec)
_smoke_spec.loader.exec_module(_smoke_module)

classify_readiness = _smoke_module.classify_readiness
require_worker_api_token_secret = _smoke_module.require_worker_api_token_secret
validate_health = _smoke_module.validate_health
resolve_smoke_input_path = _smoke_module.resolve_smoke_input_path
run_smoke = _smoke_module.main


def test_deployment_smoke_accepts_fully_ready_worker():
    payload = {
        "status": "READY",
        "checks": {
            "providers": "VERIFIED",
            "database": "VERIFIED",
            "authentication": "VERIFIED",
            "rate_limit": "VERIFIED",
            "audit": "NOT CONFIGURED (OPTIONAL)",
            "task_runs": "NOT CONFIGURED (OPTIONAL)",
        },
        "execution": {"inference_performed": False},
    }

    assert classify_readiness(200, payload) == "READY"


def test_deployment_smoke_accepts_explicit_safe_mode_without_claiming_readiness():
    payload = {
        "status": "NOT READY",
        "checks": {
            "providers": "NOT VERIFIED",
            "database": "VERIFIED",
            "authentication": "VERIFIED",
            "rate_limit": "VERIFIED",
            "audit": "NOT CONFIGURED (OPTIONAL)",
            "task_runs": "NOT CONFIGURED (OPTIONAL)",
        },
        "execution": {"inference_performed": False},
        "message": "Provider readiness checks are disabled by configuration.",
    }

    assert classify_readiness(503, payload) == "SAFE_MODE_PROVIDER_READINESS_DISABLED"


@pytest.mark.parametrize(
    ("status_code", "payload"),
    [
        (
            503,
            {
                "status": "NOT READY",
                "checks": {
                    "providers": "NOT VERIFIED",
                    "database": "VERIFIED",
                    "authentication": "DEGRADED",
                    "rate_limit": "VERIFIED",
                    "audit": "NOT CONFIGURED (OPTIONAL)",
                    "task_runs": "NOT CONFIGURED (OPTIONAL)",
                },
                "execution": {"inference_performed": False},
                "message": "Provider inference is disabled by configuration.",
            },
        ),
        (
            503,
            {
                "status": "NOT READY",
                "checks": {
                    "providers": "DEGRADED",
                    "database": "VERIFIED",
                    "authentication": "VERIFIED",
                    "rate_limit": "VERIFIED",
                    "audit": "NOT CONFIGURED (OPTIONAL)",
                    "task_runs": "NOT CONFIGURED (OPTIONAL)",
                },
                "execution": {"inference_performed": False},
                "message": "Provider readiness probe failed (RuntimeError).",
            },
        ),
        (
            503,
            {
                "status": "NOT READY",
                "checks": {
                    "providers": "NOT VERIFIED",
                    "database": "DEGRADED",
                    "authentication": "VERIFIED",
                    "rate_limit": "VERIFIED",
                    "audit": "NOT CONFIGURED (OPTIONAL)",
                    "task_runs": "NOT CONFIGURED (OPTIONAL)",
                },
                "execution": {"inference_performed": False},
                "message": "Provider inference is disabled by configuration.",
            },
        ),
    ],
)
def test_deployment_smoke_rejects_degraded_controls(status_code, payload):
    with pytest.raises(ValueError):
        classify_readiness(status_code, payload)


def test_deployment_smoke_rejects_unexpected_readiness_status():
    with pytest.raises(ValueError):
        classify_readiness(
            401,
            {
                "status": "NOT READY",
                "checks": {},
                "execution": {"inference_performed": False},
                "message": "Unauthorized",
            },
        )


def test_deployment_smoke_requires_worker_api_token_secret():
    require_worker_api_token_secret(["GLORIFIER_API_TOKEN"])

    with pytest.raises(ValueError, match="GLORIFIER_API_TOKEN"):
        require_worker_api_token_secret([])


def test_deployment_smoke_validates_health_endpoint_without_overclaiming_dependencies():
    validate_health(
        {
            "service": "glorifier-neural",
            "checks": {
                "process": "VERIFIED",
                "providers": "NOT VERIFIED",
                "database": "NOT VERIFIED",
            },
        }
    )

    with pytest.raises(ValueError):
        validate_health(
            {
                "service": "glorifier-neural",
                "checks": {"process": "DEGRADED"},
            }
        )



def test_smoke_main_reports_non_object_endpoint_payload_without_traceback(
    monkeypatch, tmp_path, capsys
):
    import sys

    health_file = tmp_path / "health.json"
    readiness_file = tmp_path / "ready.json"
    health_file.write_text("[]", encoding="utf-8")
    readiness_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deployment_smoke.py",
            "--health-file",
            str(health_file),
            "--readiness-file",
            str(readiness_file),
            "--readiness-status",
            "503",
        ],
    )

    assert run_smoke() == 1
    output = capsys.readouterr().out
    assert output.startswith("::error::")
    assert "JSON objects" in output
    assert "Traceback" not in output


def test_deployment_smoke_rejects_missing_provider_check_in_safe_mode():
    payload = {
        "status": "NOT READY",
        "checks": {
            "database": "VERIFIED",
            "authentication": "VERIFIED",
            "rate_limit": "VERIFIED",
        },
        "execution": {"inference_performed": False},
        "message": "Provider readiness checks are disabled by configuration.",
    }

    with pytest.raises(ValueError, match="provider-disabled safe mode"):
        classify_readiness(503, payload)



def test_smoke_input_path_accepts_existing_regular_file_inside_system_temp(tmp_path):
    safe_file = tmp_path / "health.json"
    safe_file.write_text("{}", encoding="utf-8")

    assert resolve_smoke_input_path(str(safe_file)) == safe_file.resolve()


def test_smoke_input_path_rejects_files_outside_system_temp():
    outside_file = Path(__file__).resolve()

    with pytest.raises(ValueError, match="temporary directory"):
        resolve_smoke_input_path(str(outside_file))


def test_smoke_input_path_rejects_directory_inside_system_temp(tmp_path):
    directory = tmp_path / "payload-directory"
    directory.mkdir()

    with pytest.raises(ValueError, match="regular file"):
        resolve_smoke_input_path(str(directory))


def test_smoke_input_path_rejects_symlink_escape_from_system_temp(tmp_path):
    outside_file = Path(__file__).resolve()
    linked_file = tmp_path / "outside.json"
    linked_file.symlink_to(outside_file)

    with pytest.raises(ValueError, match="temporary directory"):
        resolve_smoke_input_path(str(linked_file))
