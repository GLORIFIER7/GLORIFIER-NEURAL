"""Optional NVIDIA NIM hosted inference adapter.

This adapter is never registered or enabled automatically. Configure it only in a
secret manager and explicitly inject it into the provider registry.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
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


def _read_response_before_deadline(
    response,
    *,
    deadline: float,
    max_bytes: int,
) -> bytes:
    """Read a bounded HTTP body while applying the remaining absolute deadline."""
    response_file = getattr(response, "fp", None)
    raw_stream = getattr(response_file, "raw", None)
    response_socket = getattr(raw_stream, "_sock", None)
    read_once = getattr(response, "read1", None)
    if response_socket is None or not callable(read_once):
        raise OSError("NVIDIA NIM response does not expose a deadline-capable stream")

    body = bytearray()
    while len(body) < max_bytes + 1:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("NVIDIA NIM readiness probe exceeded its deadline")
        response_socket.settimeout(remaining)
        chunk = read_once(min(8_192, max_bytes + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)

    if time.monotonic() > deadline:
        raise TimeoutError("NVIDIA NIM readiness probe exceeded its deadline")
    return bytes(body)


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
        fetch_fn=None,
    ) -> None:
        self._fetch_fn = fetch_fn
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
        timeout = min(self._timeout, 5.0)
        deadline = time.monotonic() + timeout
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("NVIDIA NIM readiness probe exceeded its deadline")
            with _open_nvidia_request(request, timeout=remaining) as response:
                if response.status != 200:
                    raise RuntimeError("NVIDIA NIM readiness endpoint returned an unexpected status")
                raw = _read_response_before_deadline(
                    response,
                    deadline=deadline,
                    max_bytes=262_144,
                )
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


    async def _fetch_json(
        self,
        url: str,
        *,
        method: str,
        body: str | None,
        timeout_seconds: float,
        max_bytes: int,
        readiness: bool = False,
    ) -> dict:
        """Use the Worker Fetch API with a bounded timeout and no redirects."""
        fetch_fn = self._fetch_fn
        if fetch_fn is None:
            try:
                from workers import fetch as fetch_fn
            except ImportError:
                raise RuntimeError("Cloudflare Fetch transport is unavailable") from None

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        options = {
            "method": method,
            "headers": headers,
            "redirect": "manual",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
            options["body"] = body

        try:
            response = await asyncio.wait_for(
                fetch_fn(url, **options),
                timeout=min(timeout_seconds, self._timeout),
            )
            status = int(response.status)
            if status != 200:
                label = "readiness probe" if readiness else "request"
                raise RuntimeError(f"NVIDIA NIM {label} failed with HTTP {status}")

            response_headers = getattr(response, "headers", None)
            content_length = None
            if response_headers is not None:
                getter = getattr(response_headers, "get", None)
                if callable(getter):
                    content_length = getter("content-length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise RuntimeError("NVIDIA NIM response exceeded the response size limit")
                except ValueError:
                    raise RuntimeError("NVIDIA NIM returned an invalid content length") from None

            raw = await response.text()
        except TimeoutError:
            raise RuntimeError("NVIDIA NIM request exceeded its timeout") from None
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 - upstream details may contain secrets
            label = "readiness endpoint" if readiness else "request"
            raise RuntimeError(f"NVIDIA NIM {label} is unavailable") from None

        if not isinstance(raw, str) or len(raw.encode("utf-8")) > max_bytes:
            raise RuntimeError("NVIDIA NIM response exceeded the response size limit")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("NVIDIA NIM returned an invalid JSON response") from None
        if not isinstance(payload, dict):
            raise TypeError("NVIDIA NIM returned an invalid JSON response")
        return payload

    async def acheck_readiness(self) -> None:
        """Verify model catalogue availability using request-context Fetch, without inference."""
        if not self.is_configured():
            raise RuntimeError("NVIDIA NIM is not configured")
        payload = await self._fetch_json(
            "https://integrate.api.nvidia.com/v1/models",
            method="GET",
            body=None,
            timeout_seconds=min(self._timeout, 5.0),
            max_bytes=262_144,
            readiness=True,
        )
        models = payload.get("data")
        if not isinstance(models, list) or not any(
            isinstance(model, dict) and model.get("id") == self._model
            for model in models
        ):
            raise RuntimeError(
                "Configured NVIDIA NIM model is not present in the available model catalogue"
            )

    async def ainfer(
        self,
        prompt: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> InferenceResult:
        """Run bounded NVIDIA NIM inference through the Cloudflare Fetch API."""
        if not self.is_configured():
            raise RuntimeError("NVIDIA NIM is not configured")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > self.max_prompt_chars:
            raise ValueError("Prompt is empty or exceeds the supported limit")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be greater than 0 and at most 30")

        body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_output_tokens,
                "stream": False,
            },
            separators=(",", ":"),
        )
        data = await self._fetch_json(
            self.endpoint,
            method="POST",
            body=body,
            timeout_seconds=min(timeout_seconds, self._timeout),
            max_bytes=1_000_000,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("NVIDIA NIM returned an invalid response") from None
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000:
            raise RuntimeError("NVIDIA NIM returned an empty or oversized response")
        return InferenceResult(provider=self.name, text=text)

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
