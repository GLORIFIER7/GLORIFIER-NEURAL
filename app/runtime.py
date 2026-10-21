"""Explicit, environment-driven runtime configuration.

No provider is enabled unless the operator sets both the enable flag and provider
name. Credentials are read from the deployment environment, never from requests.
"""
from __future__ import annotations

import os

from app.orchestrator import Orchestrator
from app.providers import NvidiaNimAdapter
from app.providers.registry import ProviderRegistry


def build_orchestrator_from_environment() -> Orchestrator:
    """Build an orchestrator using explicit opt-in configuration only."""
    enabled = os.getenv("GLORIFIER_ENABLE_INFERENCE", "").strip().casefold() == "true"
    provider_name = os.getenv("GLORIFIER_PROVIDER", "").strip().casefold() or None
    registry = ProviderRegistry()

    external_egress_allowed = (
        os.getenv("GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS", "").strip().casefold() == "true"
    )

    if enabled and external_egress_allowed and provider_name == NvidiaNimAdapter.name:
        registry.register(NvidiaNimAdapter())

    return Orchestrator(
        providers=registry,
        allow_inference=enabled,
        provider_name=provider_name,
    )
