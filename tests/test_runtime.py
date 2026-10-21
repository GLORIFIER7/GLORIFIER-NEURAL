from app.providers import NvidiaNimAdapter
from app.runtime import build_orchestrator_from_environment
from app.schemas import TaskRequest


def clear_runtime_environment(monkeypatch):
    for name in ("GLORIFIER_ENABLE_INFERENCE", "GLORIFIER_PROVIDER", "GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS", "NVIDIA_NIM_API_KEY", "NVIDIA_NIM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_runtime_disables_inference_by_default(monkeypatch):
    clear_runtime_environment(monkeypatch)
    orchestrator = build_orchestrator_from_environment()
    result = orchestrator.run(TaskRequest(task="hello", require_approval=False))
    assert result.status == "NOT VERIFIED"
    assert result.evidence == ["inference:disabled", "execution:none"]


def test_provider_name_alone_does_not_enable_inference(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_PROVIDER", "nvidia_nim")
    orchestrator = build_orchestrator_from_environment()
    result = orchestrator.run(TaskRequest(task="hello", require_approval=False))
    assert result.status == "NOT VERIFIED"
    assert result.evidence == ["inference:disabled", "execution:none"]


def test_unknown_provider_never_falls_back_implicitly(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_ENABLE_INFERENCE", "true")
    monkeypatch.setenv("GLORIFIER_PROVIDER", "unknown-provider")
    orchestrator = build_orchestrator_from_environment()
    result = orchestrator.run(TaskRequest(task="hello", require_approval=False))
    assert result.status == "NOT VERIFIED"
    assert result.evidence == ["provider:unknown-provider:unavailable", "execution:none"]


def test_nim_requires_both_explicit_opt_in_and_credentials(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_ENABLE_INFERENCE", "true")
    monkeypatch.setenv("GLORIFIER_PROVIDER", NvidiaNimAdapter.name)
    orchestrator = build_orchestrator_from_environment()
    result = orchestrator.run(TaskRequest(task="hello", require_approval=False))
    assert result.status == "NOT VERIFIED"
    assert result.evidence == ["provider:nvidia_nim:unavailable", "execution:none"]


def test_nim_is_configured_only_after_explicit_opt_in_and_key(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_ENABLE_INFERENCE", "true")
    monkeypatch.setenv("GLORIFIER_PROVIDER", NvidiaNimAdapter.name)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-only-key")
    monkeypatch.setenv("GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS", "true")
    orchestrator = build_orchestrator_from_environment()
    # Verify runtime wiring without invoking the provider or making a network call.
    assert orchestrator._allow_inference is True
    assert orchestrator._provider_name == "nvidia_nim"
    assert orchestrator._providers.get("nvidia_nim") is not None


def test_nim_is_not_registered_without_external_egress_consent(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_ENABLE_INFERENCE", "true")
    monkeypatch.setenv("GLORIFIER_PROVIDER", NvidiaNimAdapter.name)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-only-key")
    orchestrator = build_orchestrator_from_environment()
    result = orchestrator.run(TaskRequest(task="hello", require_approval=False))
    assert result.status == "NOT VERIFIED"
    assert result.evidence == ["provider:nvidia_nim:unavailable", "execution:none"]


def test_nim_requires_explicit_external_egress_consent(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("GLORIFIER_ENABLE_INFERENCE", "true")
    monkeypatch.setenv("GLORIFIER_PROVIDER", NvidiaNimAdapter.name)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-only-key")
    monkeypatch.setenv("GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS", "true")
    orchestrator = build_orchestrator_from_environment()
    assert orchestrator._providers.get("nvidia_nim") is not None
