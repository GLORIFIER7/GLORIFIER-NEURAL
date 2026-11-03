"""Optional NVIDIA NIM hosted inference adapter.

This adapter is never registered or enabled automatically. Configure it only in a
secret manager and explicitly inject it into the provider registry.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from app.providers.base import InferenceResult, ProviderAdapter


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so bearer credentials cannot be forwarded to another host."""

    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _open_nvidia_request(request: urllib.request.Request, *, timeout: float):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


class NvidiaNimAdapter(ProviderAdapter):
    """Minimal OpenAI-compatible NVIDIA NIM chat-completions adapter."""

    name = "nvidia_nim"
    endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
    max_prompt_chars = 20_000
    max_output_tokens = 1_024

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("NVIDIA_NIM_API_KEY", "")).strip()
        self._model = (model if model is not None else os.getenv(
            "NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct"
        )).strip()
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than 0 and at most 30")
        self._timeout = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self._api_key and self._model)

    def check_readiness(self) -> None:
        """Verify the selected model is listed by NVIDIA without submitting inference."""
        if not self.is_configured():
            raise RuntimeError("NVIDIA NIM is not configured")

        request = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/models",
            method="GET",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
        )
        try:
            with _open_nvidia_request(request, timeout=min(self._timeout, 5.0)) as response:
                if response.status != 200:
                    raise RuntimeError("NVIDIA NIM readiness endpoint returned an unexpected status")
                raw = response.read(262_145)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"NVIDIA NIM readiness probe failed with HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("NVIDIA NIM readiness endpoint is unavailable") from None

        if len(raw) > 262_144:
            raise RuntimeError("NVIDIA NIM model catalogue exceeded the response size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("NVIDIA NIM returned an invalid model catalogue") from None
        models = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(models, list) or not any(
            isinstance(model, dict) and model.get("id") == self._model
            for model in models
        ):
            raise RuntimeError("Configured NVIDIA NIM model is not present in the available model catalogue")

    def infer(self, prompt: str, *, timeout_seconds: float = 30.0) -> InferenceResult:
        if not self.is_configured():
            raise RuntimeError("NVIDIA NIM is not configured")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.max_prompt_chars:
            raise ValueError("Prompt is empty or exceeds the supported limit")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than 0 and at most 30")

        body = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with _open_nvidia_request(request, timeout=min(timeout_seconds, self._timeout)) as response:
                if response.status != 200:
                    raise RuntimeError("NVIDIA NIM returned an unexpected status")
                raw = response.read(1_000_001)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"NVIDIA NIM request failed with HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("NVIDIA NIM request unavailable") from None

        if len(raw) > 1_000_000:
            raise RuntimeError("NVIDIA NIM response exceeded the response size limit")
        try:
            data = json.loads(raw.decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise RuntimeError("NVIDIA NIM returned an invalid response") from None
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            raise RuntimeError("NVIDIA NIM returned an empty or oversized response")
        return InferenceResult(provider=self.name, text=text)
