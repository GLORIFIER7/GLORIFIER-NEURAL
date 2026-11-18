"""Fail-closed checks for the Cloudflare Neural production smoke workflow."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any


_REQUIRED_READY_CHECKS = ("providers", "database", "authentication", "rate_limit")
_REQUIRED_SAFE_MODE_CHECKS = ("database", "authentication", "rate_limit")
_SAFE_MODE_PROVIDER_MESSAGE = "Provider readiness checks are disabled by configuration."


def resolve_smoke_input_path(path: str) -> Path:
    """Resolve an existing smoke payload file, restricted to the OS temp directory.

    The smoke command consumes files created by its own workflow. It must not accept
    arbitrary repository, runner, or symlink-target paths from caller-controlled CLI
    arguments.
    """
    try:
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        resolved_path = Path(path).resolve(strict=True)
        resolved_path.relative_to(temporary_root)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("Smoke input files must resolve inside the system temporary directory.") from None
    if not resolved_path.is_file():
        raise ValueError("Smoke input path must identify an existing regular file.")
    return resolved_path


def require_worker_api_token_secret(secret_names: list[str]) -> None:
    """Require the API bearer token to exist without reading or printing its value."""
    if "GLORIFIER_API_TOKEN" not in secret_names:
        raise ValueError(
            "Missing Cloudflare Worker secret GLORIFIER_API_TOKEN; "
            "provision it in the Cloudflare Worker secret manager before deployment."
        )


def validate_health(health: dict[str, Any]) -> None:
    """Confirm process liveness without claiming provider or database readiness."""
    if health.get("service") != "glorifier-neural":
        raise ValueError("Unexpected service identity in /health response.")
    checks = health.get("checks")
    if not isinstance(checks, dict) or checks.get("process") != "VERIFIED":
        raise ValueError("Neural process liveness is not verified.")
    

def classify_readiness(status_code: int, readiness: dict[str, Any]) -> str:
    """Classify ready releases versus provider-readiness-disabled safe mode.

    Safe mode is accepted only when read-only provider readiness is disabled by
    configuration, no inference was performed, and database/authentication/rate-limit
    controls are verified. A missing token, missing binding, or degraded control is a failure.
    """
    checks = readiness.get("checks")
    execution = readiness.get("execution")
    status = readiness.get("status")
    message = readiness.get("message")
    if not isinstance(checks, dict) or not isinstance(execution, dict):
        raise TypeError("Neural readiness response is missing required structured checks.")
    if execution.get("inference_performed") is not False:
        raise ValueError("Readiness smoke check must not perform inference.")
    if any(checks.get(name) == "DEGRADED" for name in ("database", "authentication", "rate_limit", "audit", "task_runs")):
        raise ValueError("Neural readiness has a degraded production control.")

    if status_code == 200 and status == "READY":
        missing = [name for name in _REQUIRED_READY_CHECKS if checks.get(name) != "VERIFIED"]
        if missing:
            raise ValueError(f"READY response has non-verified checks: {', '.join(missing)}.")
        return "READY"

    if status_code == 503 and status == "NOT READY":
        if checks.get("providers") != "NOT VERIFIED" or message != _SAFE_MODE_PROVIDER_MESSAGE:
            raise ValueError("Neural readiness failed for a reason other than intentional provider-disabled safe mode.")
        missing = [
            name for name in _REQUIRED_SAFE_MODE_CHECKS
            if checks.get(name) != "VERIFIED"
        ]
        if missing:
            raise ValueError(
                "Safe mode requires verified database, authentication, and rate limiting; "
                f"unverified: {', '.join(missing)}."
            )
        return "SAFE_MODE_PROVIDER_READINESS_DISABLED"

    raise ValueError(f"Unexpected Neural readiness status: HTTP {status_code}, status={status!r}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-file", required=True)
    parser.add_argument("--readiness-file", required=True)
    parser.add_argument("--readiness-status", required=True, type=int)
    args = parser.parse_args()

    try:
        health_path = resolve_smoke_input_path(args.health_file)
        readiness_path = resolve_smoke_input_path(args.readiness_file)
        health = json.loads(health_path.read_text(encoding="utf-8"))
        readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
        if not isinstance(health, dict) or not isinstance(readiness, dict):
            raise TypeError("Neural health and readiness responses must be JSON objects.")
        validate_health(health)
        mode = classify_readiness(args.readiness_status, readiness)
    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        print(f"::error::{exc}")
        return 1

    if mode == "READY":
        print("Neural production readiness verified; no inference was performed.")
    else:
        print(
            "::warning::Neural Worker is deployed and security/database controls passed, "
            "but read-only provider readiness checks are disabled by configuration. "
            "No inference was performed; service is NOT READY for provider-backed task execution."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
