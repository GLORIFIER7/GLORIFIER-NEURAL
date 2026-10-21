from app.policy import evaluate_task
from app.providers.registry import ProviderRegistry
from app.schemas import TaskRequest, TaskResponse


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
        except Exception as exc:
            # Avoid returning exception details that may contain prompts, URLs, or secrets.
            return TaskResponse(
                status="DEGRADED",
                provider=self._provider_name,
                message=f"Provider inference failed ({type(exc).__name__}); no result was accepted.",
                evidence=[f"provider:{self._provider_name}:error", "execution:failed"],
            )

        if not isinstance(result.text, str) or not result.text.strip():
            return TaskResponse(
                status="DEGRADED",
                provider=self._provider_name,
                message="Provider returned an empty or invalid result.",
                evidence=[f"provider:{self._provider_name}:invalid-result", "execution:rejected"],
            )
        return TaskResponse(
            status="VERIFIED",
            provider=result.provider,
            result=result.text,
            message="Provider returned a result; this verifies response receipt, not factual correctness.",
            evidence=[f"provider:{result.provider}:response-received", "execution:inference"],
        )
