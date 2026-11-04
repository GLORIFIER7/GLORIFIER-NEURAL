"""Tests for fail-closed Cloudflare deployment preflight and smoke checks."""

import pytest

from cloudflare.deployment_smoke import (
    classify_readiness,
    require_worker_api_token_secret,
    validate_health,
)


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
        "message": "Provider inference is disabled by configuration.",
    }

    assert classify_readiness(503, payload) == "SAFE_MODE_PROVIDER_DISABLED"


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
