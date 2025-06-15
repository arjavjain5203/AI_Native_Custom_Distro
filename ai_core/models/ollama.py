"""Minimal Ollama HTTP client."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from ai_core.core.config import OLLAMA_BASE_URL, OLLAMA_PLANNING_MODEL


class OllamaError(RuntimeError):
    """Raised when the local Ollama runtime cannot satisfy a request."""


class OllamaClient:
    """Minimal wrapper around the local Ollama runtime."""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, default_model: str = OLLAMA_PLANNING_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        """Generate a non-streaming response from Ollama."""
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
        }
        response = self._post_json("/api/generate", payload, timeout_seconds=timeout_seconds)
        text = response.get("response")
        if not isinstance(text, str):
            raise OllamaError("ollama response did not include text output")
        return text.strip()

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=timeout_seconds or 60) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"ollama returned HTTP {exc.code}: {details}") from exc
        except error.URLError as exc:
            raise OllamaError(f"could not reach ollama at {self.base_url}: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"ollama returned invalid JSON: {raw}") from exc

        if isinstance(data, dict) and data.get("error"):
            raise OllamaError(str(data["error"]))

        return data
