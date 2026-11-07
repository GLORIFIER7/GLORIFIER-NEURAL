import asyncio
import json
from typing import ClassVar

import pytest

from app.providers.dynamo import NvidiaDynamoAdapter


class _FakeReader:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self._read = False

    async def read(self):
        if self._read:
            return type("ReadResult", (), {"done": True, "value": None})()
        self._read = True
        return type("ReadResult", (), {"done": False, "value": self._body})()

    async def cancel(self):
        return None

    def releaseLock(self):
        return None


class _FakeStream:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def getReader(self):
        return _FakeReader(self._body)


class _FakeResponse:
    def __init__(self, status: int, payload: dict | bytes, request_id: str = "req-dynamo-1"):
        self.status = status
        self.headers: ClassVar[dict[str, str]] = {"x-request-id": request_id}
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.body = _FakeStream(body)


def _adapter(**overrides) -> NvidiaDynamoAdapter:
    values = {
        "api_key": "dynamo-test-secret",
        "model": "Qwen/Qwen3-0.6B",
        "base_url": "https://dynamo.example/v1",
        "allowed_origin": "https://dynamo.example",
    }
    values.update(overrides)
    return NvidiaDynamoAdapter(**values)


def test_dynamo_adapter_requires_https_and_an_exact_origin_allowlist():
    assert _adapter().is_configured()
    assert not _adapter(base_url="http://dynamo.example/v1").is_configured()
    assert not _adapter(
        base_url="https://other.example/v1",
        allowed_origin="https://dynamo.example",
    ).is_configured()
    assert not _adapter(allowed_origin="https://*.example").is_configured()
    assert not _adapter(base_url="https://user:pass@dynamo.example/v1").is_configured()
    assert not _adapter(base_url="https://dynamo.example/v1?forward=1").is_configured()


def test_dynamo_adapter_is_unconfigured_without_all_explicit_settings():
    assert not _adapter(api_key="").is_configured()
    assert not _adapter(model="").is_configured()
    assert not _adapter(base_url="").is_configured()
    assert not _adapter(allowed_origin="").is_configured()


def test_dynamo_async_readiness_uses_only_the_model_catalogue():
    calls = []

    async def fake_fetch(url, *, method, headers, body=None, redirect="manual", **_kwargs):
        calls.append({
            "url": url,
            "method": method,
            "headers": headers,
            "body": body,
            "redirect": redirect,
        })
        return _FakeResponse(200, {
            "object": "list",
            "data": [{"id": "Qwen/Qwen3-0.6B", "object": "model"}],
        })

    adapter = _adapter(fetch_fn=fake_fetch)
    asyncio.run(adapter.acheck_readiness())

    assert len(calls) == 1
    assert calls[0]["url"] == "https://dynamo.example/v1/models"
    assert calls[0]["method"] == "GET"
    assert calls[0]["body"] is None
    assert calls[0]["headers"]["Authorization"] == "Bearer dynamo-test-secret"
    assert calls[0]["redirect"] == "manual"


def test_dynamo_async_inference_uses_openai_chat_completions_without_streaming():
    calls = []

    async def fake_fetch(url, *, method, headers, body=None, redirect="manual", **_kwargs):
        calls.append({
            "url": url,
            "method": method,
            "headers": headers,
            "body": json.loads(body) if body else None,
            "redirect": redirect,
        })
        return _FakeResponse(200, {
            "id": "chatcmpl-dynamo-1",
            "choices": [{"message": {"role": "assistant", "content": "Dynamo result"}}],
        })

    adapter = _adapter(fetch_fn=fake_fetch)
    result = asyncio.run(adapter.ainfer("controlled prompt", timeout_seconds=4))

    assert result.provider == "nvidia_dynamo"
    assert result.text == "Dynamo result"
    assert result.request_id == "req-dynamo-1"
    assert calls[0]["url"] == "https://dynamo.example/v1/chat/completions"
    assert calls[0]["method"] == "POST"
    assert calls[0]["headers"]["Authorization"] == "Bearer dynamo-test-secret"
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert calls[0]["body"] == {
        "model": "Qwen/Qwen3-0.6B",
        "messages": [{"role": "user", "content": "controlled prompt"}],
        "max_tokens": adapter.max_output_tokens,
        "stream": False,
    }
    assert calls[0]["redirect"] == "manual"


def test_dynamo_readiness_rejects_missing_model_without_running_inference():
    async def fake_fetch(_url, *, method, **_kwargs):
        assert method == "GET"
        return _FakeResponse(200, {"object": "list", "data": [{"id": "different-model"}]})

    with pytest.raises(RuntimeError, match="not present"):
        asyncio.run(_adapter(fetch_fn=fake_fetch).acheck_readiness())


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 500, 503])
def test_dynamo_adapter_rejects_redirects_and_http_failures_without_leaking_details(status):
    async def fake_fetch(*_args, **_kwargs):
        return _FakeResponse(status, {"error": "sensitive upstream response"})

    adapter = _adapter(fetch_fn=fake_fetch)
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as exc_info:
        asyncio.run(adapter.acheck_readiness())
    assert "dynamo-test-secret" not in str(exc_info.value)
    assert "sensitive upstream response" not in str(exc_info.value)


def test_dynamo_adapter_rejects_malformed_and_oversized_responses():
    async def malformed_fetch(*_args, **_kwargs):
        return _FakeResponse(200, b"not-json")

    with pytest.raises(RuntimeError, match="invalid JSON"):
        asyncio.run(_adapter(fetch_fn=malformed_fetch).acheck_readiness())

    async def oversized_fetch(*_args, **_kwargs):
        return _FakeResponse(200, b"x" * 262_145)

    with pytest.raises(RuntimeError, match="response size limit"):
        asyncio.run(_adapter(fetch_fn=oversized_fetch).acheck_readiness())


def test_dynamo_adapter_rejects_empty_or_oversized_prompts_before_network():
    calls = []

    async def fake_fetch(*args, **kwargs):
        calls.append(args)
        return _FakeResponse(200, {
            "id": "chatcmpl-dynamo-1",
            "choices": [{"message": {"content": "ok"}}],
        })

    adapter = _adapter(fetch_fn=fake_fetch)
    with pytest.raises(ValueError, match="empty"):
        asyncio.run(adapter.ainfer("   "))
    with pytest.raises(ValueError, match="exceeds"):
        asyncio.run(adapter.ainfer("x" * (adapter.max_prompt_chars + 1)))
    assert calls == []


def test_dynamo_adapter_sanitizes_transport_errors():
    async def failed_fetch(*_args, **_kwargs):
        raise RuntimeError("private endpoint and dynamo-test-secret")

    with pytest.raises(RuntimeError, match="unavailable") as exc_info:
        asyncio.run(_adapter(fetch_fn=failed_fetch).acheck_readiness())

    assert "dynamo-test-secret" not in str(exc_info.value)
    assert "private endpoint" not in str(exc_info.value)


def test_runtime_registers_dynamo_only_when_provider_and_egress_are_explicit():
    from app.runtime import build_orchestrator_from_environment

    environment = {
        "GLORIFIER_PROVIDER": "nvidia_dynamo",
        "GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS": "true",
        "GLORIFIER_ENABLE_INFERENCE": "false",
        "NVIDIA_DYNAMO_API_KEY": "dynamo-test-secret",
        "NVIDIA_DYNAMO_MODEL": "Qwen/Qwen3-0.6B",
        "NVIDIA_DYNAMO_BASE_URL": "https://dynamo.example/v1",
        "NVIDIA_DYNAMO_ALLOWED_ORIGIN": "https://dynamo.example",
    }
    orchestrator = build_orchestrator_from_environment(environment)

    provider = orchestrator._providers.get("nvidia_dynamo")
    assert provider is not None
    assert provider.is_configured()
    assert orchestrator._allow_inference is False
    assert orchestrator._allow_provider_readiness is True


def test_runtime_does_not_register_dynamo_when_external_egress_is_not_authorized():
    from app.runtime import build_orchestrator_from_environment

    environment = {
        "GLORIFIER_PROVIDER": "nvidia_dynamo",
        "GLORIFIER_ALLOW_EXTERNAL_DATA_EGRESS": "false",
        "GLORIFIER_ENABLE_INFERENCE": "true",
        "NVIDIA_DYNAMO_API_KEY": "dynamo-test-secret",
        "NVIDIA_DYNAMO_MODEL": "Qwen/Qwen3-0.6B",
        "NVIDIA_DYNAMO_BASE_URL": "https://dynamo.example/v1",
        "NVIDIA_DYNAMO_ALLOWED_ORIGIN": "https://dynamo.example",
    }
    orchestrator = build_orchestrator_from_environment(environment)

    assert orchestrator._providers.get("nvidia_dynamo") is None
