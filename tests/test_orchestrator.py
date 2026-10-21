from app.orchestrator import Orchestrator
from app.providers.base import InferenceResult, ProviderAdapter
from app.providers.registry import ProviderRegistry
from app.schemas import TaskRequest


class FakeProvider(ProviderAdapter):
    name = "fake"

    def __init__(self, *, configured: bool = True, fail: bool = False) -> None:
        self.configured = configured
        self.fail = fail
        self.calls = 0

    def is_configured(self) -> bool:
        return self.configured

    def infer(self, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive provider error details")
        return InferenceResult(provider=self.name, text=f"answer: {prompt}")


def test_default_orchestrator_never_runs_inference():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    orchestrator = Orchestrator(registry)

    response = orchestrator.run(TaskRequest(task="summarize", require_approval=False))

    assert response.status == "NOT VERIFIED"
    assert response.evidence == ["inference:disabled", "execution:none"]
    assert provider.calls == 0


def test_approval_required_prevents_provider_call_even_when_enabled():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    orchestrator = Orchestrator(
        registry, allow_inference=True, provider_name="fake"
    )

    response = orchestrator.run(TaskRequest(task="summarize"))

    assert response.status == "NOT VERIFIED"
    assert response.evidence == ["policy:approval-required"]
    assert provider.calls == 0


def test_explicitly_enabled_and_selected_provider_can_return_result():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    orchestrator = Orchestrator(
        registry, allow_inference=True, provider_name="FAKE"
    )

    response = orchestrator.run(
        TaskRequest(task="summarize", require_approval=False)
    )

    assert response.status == "VERIFIED"
    assert response.provider == "fake"
    assert response.result == "answer: summarize"
    assert "factual correctness" in response.message
    assert provider.calls == 1


def test_unconfigured_provider_is_not_called():
    registry = ProviderRegistry()
    provider = FakeProvider(configured=False)
    registry.register(provider)
    orchestrator = Orchestrator(
        registry, allow_inference=True, provider_name="fake"
    )

    response = orchestrator.run(
        TaskRequest(task="summarize", require_approval=False)
    )

    assert response.status == "NOT VERIFIED"
    assert response.evidence == ["provider:fake:unavailable", "execution:none"]
    assert provider.calls == 0


def test_provider_exception_is_sanitized():
    registry = ProviderRegistry()
    provider = FakeProvider(fail=True)
    registry.register(provider)
    orchestrator = Orchestrator(
        registry, allow_inference=True, provider_name="fake"
    )

    response = orchestrator.run(
        TaskRequest(task="summarize", require_approval=False)
    )

    assert response.status == "DEGRADED"
    assert "sensitive provider error details" not in response.message
    assert response.evidence == ["provider:fake:error", "execution:failed"]
    assert provider.calls == 1


def test_blocked_action_prevents_provider_call():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    orchestrator = Orchestrator(
        registry, allow_inference=True, provider_name="fake"
    )

    response = orchestrator.run(
        TaskRequest(
            task="transfer funds",
            action_class="financial",
            require_approval=False,
        )
    )

    assert response.status == "DEGRADED"
    assert response.evidence == ["policy:deny"]
    assert provider.calls == 0
