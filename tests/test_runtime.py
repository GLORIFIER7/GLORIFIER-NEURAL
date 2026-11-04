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


def test_cloudflare_runtime_uses_request_scoped_nvidia_bindings_and_fetch():
    import asyncio
    import json

    from app.runtime import build_orchestrator_from_environment

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status = 200
            self.headers = {"content-length": str(len(json.dumps(payload)))}
            self.payload = payload

        async def text(self):
            return json.dumps(self.payload)

    async def fake_fetch(url, *, method, headers, body=None, redirect="manual"):
        calls.append({
            "url": url,
            "method": method,
            "headers": headers,
            "body": json.loads(body) if body else None,
            "redirect": redirect,
        })
        if method == "GET":
            return FakeResponse({"data": [{"id": "nvidia/nemotron-3-super-120b-a12b"}]})
        return FakeResponse({
            "choices": [{"message": {"content": "Nemotron response"}}]
        })

    worker_env = {
        "GLORIFIER_ENABLE_INFERENCE": "true",
        "GLORIFIER_PROVIDER": "nvidia_nim",
        "GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS": "true",
        "NVIDIA_NIM_API_KEY": "request-scoped-secret",
        "NVIDIA_NIM_MODEL": "nvidia/nemotron-3-super-120b-a12b",
    }
    orchestrator = build_orchestrator_from_environment(
        worker_env,
        fetch_fn=fake_fetch,
    )

    async def run():
        readiness = await orchestrator.acheck_readiness()
        result = await orchestrator.arun(
            TaskRequest(task="controlled test prompt", require_approval=False)
        )
        return readiness, result

    readiness, result = asyncio.run(run())

    assert readiness[0] == "VERIFIED"
    assert result.status == "VERIFIED"
    assert result.provider == "nvidia_nim"
    assert result.result == "Nemotron response"
    assert len(calls) == 2
    assert calls[0]["method"] == "GET"
    assert calls[1]["method"] == "POST"
    assert calls[1]["headers"]["Authorization"] == "Bearer request-scoped-secret"
    assert calls[1]["body"]["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert calls[1]["redirect"] == "manual"
