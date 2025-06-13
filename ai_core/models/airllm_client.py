"""Optional AirLLM runtime client."""

from __future__ import annotations

import importlib
from typing import Any


class AirLLMError(RuntimeError):
    """Raised when the AirLLM backend cannot satisfy a request."""


class AirLLMClient:
    """Minimal wrapper around the optional AirLLM Python package."""

    def __init__(
        self,
        module_name: str = "airllm",
        generation_defaults: dict[str, Any] | None = None,
    ) -> None:
        self.module_name = module_name
        self.generation_defaults = {"max_new_tokens": 256}
        if generation_defaults:
            self.generation_defaults.update(generation_defaults)
        self._module: Any | None = None
        self._model_cache: dict[str, Any] = {}

    def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        """Generate a non-streaming response from AirLLM."""
        if not model.strip():
            raise AirLLMError("model name is required for AirLLM generation")

        model_instance = self._get_or_load_model(model)
        generation_kwargs = dict(self.generation_defaults)
        generation_kwargs.update(kwargs)

        try:
            raw_output = self._run_generate(model_instance, prompt, generation_kwargs)
        except AirLLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise AirLLMError(f"airllm generation failed for model '{model}': {exc}") from exc

        return self._normalize_output(raw_output)

    def _get_or_load_model(self, model_name: str) -> Any:
        if model_name in self._model_cache:
            return self._model_cache[model_name]

        module = self._load_module()
        factory = self._resolve_model_factory(module)

        try:
            if hasattr(factory, "from_pretrained"):
                model_instance = factory.from_pretrained(model_name)
            elif callable(factory):
                model_instance = factory(model_name)
            else:  # pragma: no cover - guarded by _resolve_model_factory
                raise AirLLMError("resolved AirLLM model factory is not callable")
        except AirLLMError:
            raise
        except Exception as exc:
            raise AirLLMError(f"airllm failed to load model '{model_name}': {exc}") from exc

        self._model_cache[model_name] = model_instance
        return model_instance

    def _load_module(self) -> Any:
        if self._module is not None:
            return self._module

        try:
            self._module = importlib.import_module(self.module_name)
        except ModuleNotFoundError as exc:
            raise AirLLMError("airllm is not installed") from exc

        return self._module

    @staticmethod
    def _resolve_model_factory(module: Any) -> Any:
        for attribute in ("AutoModel", "AutoModelForCausalLM", "AirLLMModel"):
            factory = getattr(module, attribute, None)
            if factory is not None:
                return factory

        raise AirLLMError("airllm module does not expose a supported model factory")

    @staticmethod
    def _run_generate(model_instance: Any, prompt: str, kwargs: dict[str, Any]) -> Any:
        if hasattr(model_instance, "generate_text"):
            return model_instance.generate_text(prompt, **kwargs)

        if not hasattr(model_instance, "generate"):
            raise AirLLMError("loaded AirLLM model does not expose a supported generation method")

        generate = model_instance.generate
        try:
            return generate([prompt], **kwargs)
        except TypeError:
            return generate(prompt, **kwargs)

    @classmethod
    def _normalize_output(cls, raw_output: Any) -> str:
        if isinstance(raw_output, str):
            return raw_output.strip()

        if isinstance(raw_output, list):
            if not raw_output:
                return ""
            if len(raw_output) == 1:
                return cls._normalize_output(raw_output[0])
            return "\n".join(cls._normalize_output(item) for item in raw_output).strip()

        if isinstance(raw_output, dict):
            for key in ("response", "text", "generated_text", "output_text"):
                value = raw_output.get(key)
                if isinstance(value, str):
                    return value.strip()
            for key in ("outputs", "sequences"):
                value = raw_output.get(key)
                if value is not None:
                    return cls._normalize_output(value)

        for attribute in ("text", "generated_text", "output_text"):
            value = getattr(raw_output, attribute, None)
            if isinstance(value, str):
                return value.strip()

        if hasattr(raw_output, "sequences"):
            return cls._normalize_output(getattr(raw_output, "sequences"))

        return str(raw_output).strip()
