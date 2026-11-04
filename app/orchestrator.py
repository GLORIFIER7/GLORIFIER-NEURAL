from collections.abc import Callable
import threading
import time

from app.policy import evaluate_task
from app.providers.base import InferenceResult
from app.providers.registry import ProviderRegistry
from app.schemas import TaskRequest, TaskResponse


_READINESS_CACHE_TTL_SECONDS = 30.0


class Orchestrator:
    """Safe orchestration shell; provider inference is disabled unless explicitly opted in."""

    def __init__(
        self,
        providers: ProviderRegistry | None = None,
        *,
        allow_inference: bool = False,
        provider_name: str | None = None,
    ) -> None:
        self._providers = providers or ProviderRegistry()
        self._allow_inference = allow_inference
        self._provider_name = provider_name
        self._readiness_lock = threading.Lock()
        self._readiness_cache: tuple[float, tuple[str, str]] | None = None

    def check_readiness(self) -> tuple[str, str]:
        """Return a short-lived cached provider check to protect the upstream credential."""
        with self._readiness_lock:
            now = time.monotonic()
            if (
                self._readiness_cache is not None
                and now - self._readiness_cache[0] < _READINESS_CACHE_TTL_SECONDS
            ):
                return self._readiness_cache[1]

            result = self._probe_readiness()
            # Start the TTL after the potentially slow upstream request completes.
            self._readiness_cache = (time.monotonic(), result)
            return result

    def _probe_readiness(self) -> tuple[str, str]:
        """Probe the selected provider without sending task content or running inference."""
        if not self._allow_inference:
            return "NOT VERIFIED", "Provider inference is disabled by configuration."
        if not self._provider_name:
            return "NOT VERIFIED", "No provider was explicitly selected."
        provider = self._providers.get(self._provider_name)
        if provider is None:
            return "NOT VERIFIED", "The selected provider is not configured."
        probe = getattr(provider, "check_readiness", None)
        if not callable(probe):
            return "NOT VERIFIED", "The selected provider has no read-only readiness probe."
        readiness_probe: Callable[[], None] = probe
        try:
            readiness_probe()
        except Exception as exc:  # noqa: BLE001 - readiness must not leak credentials or endpoints
            return "DEGRADED", f"Provider readiness probe failed ({type(exc).__name__})."
        return "VERIFIED", "Configured provider passed its read-only model availability probe."

    def run(self, request: TaskRequest) -> TaskResponse:
        decision = evaluate_task(
            require_approval=request.require_approval,
            action_class=request.action_class,
        )
        if not decision.allowed:
            return TaskResponse(
                status="DEGRADED",
                message=decision.reason,
                evidence=["policy:deny"],
            )
        if decision.requires_human_approval:
            return TaskResponse(
                status="NOT VERIFIED",
                message=decision.reason,
                evidence=["policy:approval-required"],
            )

        if not self._allow_inference:
            return TaskResponse(
                status="NOT VERIFIED",
                message="Provider inference is disabled by configuration; no inference was performed.",
                evidence=["inference:disabled", "execution:none"],
            )
        if not self._provider_name:
            return TaskResponse(
                status="NOT VERIFIED",
                message="No provider was explicitly selected; no inference was performed.",
                evidence=["provider:none", "execution:none"],
            )

        provider = self._providers.get(self._provider_name)
        if provider is None:
            return TaskResponse(
                status="NOT VERIFIED",
                message="The explicitly selected provider is unavailable or unconfigured.",
                evidence=[f"provider:{self._provider_name}:unavailable", "execution:none"],
            )

        try:
            result = provider.infer(request.task)
        except Exception as exc:  # noqa: BLE001
            # Avoid returning exception details that may contain prompts, URLs, or secrets.
            return TaskResponse(
                status="DEGRADED",
                provider=self._provider_name,
                message=f"Provider inference failed ({type(exc).__name__}); no result was accepted.",
                evidence=[f"provider:{self._provider_name}:error", "execution:failed"],
            )

        if not isinstance(result, InferenceResult):
            return TaskResponse(
                status="DEGRADED",
                provider=self._provider_name,
                message="Provider returned an invalid result object.",
                evidence=[f"provider:{self._provider_name}:invalid-result", "execution:rejected"],
            )
        if (
            not isinstance(result.provider, str)
            or result.provider.strip().casefold() != self._provider_name.strip().casefold()
            or not isinstance(result.text, str)
            or not result.text.strip()
            or len(result.text) > 20_000
        ):
            return TaskResponse(
                status="DEGRADED",
                provider=self._provider_name,
                message="Provider returned an empty, oversized, or mismatched result.",
                evidence=[f"provider:{self._provider_name}:invalid-result", "execution:rejected"],
            )
        return TaskResponse(
            status="VERIFIED",
            provider=provider.name,
            result=result.text,
            message="Provider returned a result; this verifies response receipt, not factual correctness.",
            evidence=[f"provider:{result.provider}:response-received", "execution:inference"],
        )
