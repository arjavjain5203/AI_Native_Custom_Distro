"""Model manager for runtime selection and backend dispatch."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from ai_core.core.config import (
    DEFAULT_MODEL_RUNTIME,
    LOW_MEMORY_THRESHOLD_GB,
    OLLAMA_CODING_MODEL,
    OLLAMA_ORCHESTRATOR_MODEL,
    OLLAMA_PLANNING_MODEL,
    SYSTEM_MODELS_CONFIG_PATH,
    USER_MODELS_CONFIG_PATH,
)
from ai_core.core.hardware import detect_hardware_info
from ai_core.models.airllm_client import AirLLMClient
from ai_core.models.ollama import OllamaClient

SUPPORTED_TASK_TYPES = {"coding", "planning", "system", "analysis"}
SUPPORTED_RUNTIMES = {"auto", "ollama", "airllm"}
ROLE_BY_TASK_TYPE = {
    "coding": "coding",
    "planning": "planning",
    "system": "planning",
    "analysis": "analysis",
}


class ModelManagerError(RuntimeError):
    """Raised when model selection or execution cannot be completed."""


class ModelManager:
    """Central runtime selector for model execution."""

    def __init__(
        self,
        ollama_client: OllamaClient | None = None,
        airllm_client: AirLLMClient | None = None,
        system_config_path: str | Path = SYSTEM_MODELS_CONFIG_PATH,
        user_config_path: str | Path = USER_MODELS_CONFIG_PATH,
        default_runtime: str = DEFAULT_MODEL_RUNTIME,
        low_memory_threshold_gb: float = LOW_MEMORY_THRESHOLD_GB,
        ram_gb_provider: Callable[[], float] | None = None,
        hardware_provider: Callable[[], dict[str, int | float]] | None = None,
    ) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self.airllm_client = airllm_client or AirLLMClient()
        self.system_config_path = Path(system_config_path).expanduser()
        self.user_config_path = Path(user_config_path).expanduser()
        self.default_runtime = default_runtime
        self.low_memory_threshold_gb = low_memory_threshold_gb
        if hardware_provider is not None:
            self.hardware_provider = hardware_provider
        elif ram_gb_provider is not None:
            self.hardware_provider = lambda: {
                "ram_gb": ram_gb_provider(),
                "cpu_cores": self._detect_cpu_cores(),
            }
        else:
            self.hardware_provider = detect_hardware_info

    def get_models(self) -> dict[str, Any]:
        """Return the effective model configuration."""
        config = self._load_effective_config()
        return {
            "runtime": config["runtime"],
            "orchestrator": dict(config["orchestrator"]),
            "planning": dict(config["planning"]),
            "coding": dict(config["coding"]),
            "analysis": dict(config["analysis"]),
        }

    def get_runtime_status(self) -> dict[str, Any]:
        """Return configured and effective runtime information."""
        effective_by_role: dict[str, str | None] = {}
        issues: dict[str, str] = {}
        hardware_info = self.get_hardware_info()

        for role in ("orchestrator", "planning", "coding", "analysis"):
            try:
                effective_by_role[role] = self._select_runtime_for_role(role)
            except ModelManagerError as exc:
                effective_by_role[role] = None
                issues[role] = str(exc)

        return {
            "configured_runtime": self._load_effective_config()["runtime"],
            "detected_ram_gb": round(float(hardware_info["ram_gb"]), 2),
            "cpu_cores": int(hardware_info["cpu_cores"]),
            "low_memory_threshold_gb": self.low_memory_threshold_gb,
            "selected_runtime_by_role": effective_by_role,
            "issues": issues,
        }

    def get_hardware_info(self) -> dict[str, int | float]:
        """Return normalized hardware information for runtime routing."""
        try:
            hardware_info = self.hardware_provider()
        except RuntimeError as exc:
            raise ModelManagerError(str(exc)) from exc
        except OSError as exc:
            raise ModelManagerError(f"failed to read hardware information: {exc}") from exc

        ram_gb = hardware_info.get("ram_gb")
        cpu_cores = hardware_info.get("cpu_cores")
        if not isinstance(ram_gb, (int, float)) or ram_gb <= 0:
            raise ModelManagerError("hardware provider returned an invalid ram_gb value")
        if not isinstance(cpu_cores, int) or cpu_cores <= 0:
            raise ModelManagerError("hardware provider returned an invalid cpu_cores value")
        return {
            "ram_gb": float(ram_gb),
            "cpu_cores": cpu_cores,
        }

    def set_runtime(self, runtime: str) -> dict[str, Any]:
        """Persist the configured runtime mode in the user-level config."""
        normalized_runtime = self._normalize_runtime(runtime)
        user_config = self._load_json_file(self.user_config_path)
        user_config["runtime"] = normalized_runtime

        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_config_path.write_text(
            json.dumps(user_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        return self.get_runtime_status()

    def list_configured_models(self) -> dict[str, Any]:
        """Return persisted model configuration for CLI and API callers."""
        return self.get_models()

    def set_role_model(self, role: str, runtime: str, model_name: str) -> dict[str, Any]:
        """Persist a model assignment for a role/runtime pair."""
        normalized_role = role.strip().lower()
        if normalized_role not in ("orchestrator", "planning", "coding", "analysis"):
            raise ModelManagerError(f"unsupported model role: {role}")
        normalized_runtime = runtime.strip().lower()
        if normalized_runtime not in ("ollama", "airllm"):
            raise ModelManagerError(f"unsupported model runtime: {runtime}")
        if not model_name.strip():
            raise ModelManagerError("model name must be a non-empty string")

        user_config = self._load_json_file(self.user_config_path)
        role_config = user_config.get(normalized_role, {})
        if isinstance(role_config, str):
            role_config = {"ollama": role_config}
        if not isinstance(role_config, dict):
            raise ModelManagerError(f"invalid existing model config for role '{normalized_role}'")
        role_config[normalized_runtime] = model_name.strip()
        user_config[normalized_role] = role_config

        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_config_path.write_text(
            json.dumps(user_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return self.get_models()

    def get_model_for_task(self, task_type: str) -> str:
        """Return the configured model identifier for the task type."""
        role = self._get_role_for_task(task_type)
        runtime = self.get_runtime_for_task(task_type)
        return self._get_model_for_role(role, runtime)

    def get_runtime_for_task(self, task_type: str) -> str:
        """Return the runtime selected for the task type."""
        role = self._get_role_for_task(task_type)
        return self._select_runtime_for_role(role)

    def run_model(
        self,
        model_name: str,
        prompt: str,
        *,
        runtime: str | None = None,
        task_type: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        """Run a model through the selected backend."""
        selected_runtime = self._resolve_runtime_argument(runtime, task_type, model_name)

        if selected_runtime == "ollama":
            if timeout_seconds is None:
                return self.ollama_client.generate(prompt, model=model_name)
            return self.ollama_client.generate(
                prompt,
                model=model_name,
                timeout_seconds=timeout_seconds,
            )
        if selected_runtime == "airllm":
            return self.airllm_client.generate(prompt, model=model_name)

        raise ModelManagerError(f"unsupported runtime: {selected_runtime}")

    def _resolve_runtime_argument(self, runtime: str | None, task_type: str | None, model_name: str) -> str:
        if runtime is not None:
            if runtime not in SUPPORTED_RUNTIMES - {"auto"}:
                raise ModelManagerError(f"unsupported runtime override: {runtime}")
            return runtime

        if task_type is not None:
            return self.get_runtime_for_task(task_type)

        config_runtime = self._load_effective_config()["runtime"]
        if config_runtime == "auto":
            return "ollama"
        if config_runtime not in SUPPORTED_RUNTIMES:
            raise ModelManagerError(f"unsupported configured runtime: {config_runtime}")
        if not model_name.strip():
            raise ModelManagerError("model name is required")
        return config_runtime

    def _load_effective_config(self) -> dict[str, Any]:
        merged = self._default_config()

        for config_path in (self.system_config_path, self.user_config_path):
            file_config = self._load_json_file(config_path)
            if not file_config:
                continue

            runtime = file_config.get("runtime")
            if runtime is not None:
                merged["runtime"] = self._normalize_runtime(runtime)

            for role in ("orchestrator", "planning", "coding", "analysis"):
                if role in file_config:
                    merged[role] = self._normalize_role_models(role, file_config[role], merged[role])

        if not merged["analysis"]:
            merged["analysis"] = dict(merged["planning"])

        return merged

    def _default_config(self) -> dict[str, Any]:
        return {
            "runtime": self._normalize_runtime(self.default_runtime),
            "orchestrator": {"ollama": OLLAMA_ORCHESTRATOR_MODEL},
            "planning": {"ollama": OLLAMA_PLANNING_MODEL},
            "coding": {"ollama": OLLAMA_CODING_MODEL},
            "analysis": {},
        }

    def _get_model_for_role(self, role: str, runtime: str) -> str:
        config = self._load_effective_config()
        role_models = config[role]
        model_name = role_models.get(runtime)

        if isinstance(model_name, str) and model_name.strip():
            return model_name

        raise ModelManagerError(f"no model configured for role '{role}' using runtime '{runtime}'")

    def _select_runtime_for_role(self, role: str) -> str:
        config = self._load_effective_config()
        configured_runtime = config["runtime"]
        role_models = config[role]

        if role == "orchestrator":
            return "ollama"

        if configured_runtime == "ollama":
            return "ollama"
        if configured_runtime == "airllm":
            if role_models.get("airllm"):
                return "airllm"
            raise ModelManagerError(f"no AirLLM model configured for role '{role}'")
        if configured_runtime != "auto":
            raise ModelManagerError(f"unsupported configured runtime: {configured_runtime}")

        ram_gb = float(self.get_hardware_info()["ram_gb"])
        prefers_airllm = ram_gb < self.low_memory_threshold_gb

        if prefers_airllm and role_models.get("airllm"):
            return "airllm"
        if role_models.get("ollama"):
            return "ollama"
        if role_models.get("airllm"):
            return "airllm"
        return "ollama"

    @staticmethod
    def _normalize_runtime(value: Any) -> str:
        if not isinstance(value, str):
            raise ModelManagerError(f"runtime must be a string, got: {type(value).__name__}")
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_RUNTIMES:
            raise ModelManagerError(f"unsupported runtime: {value}")
        return normalized

    @staticmethod
    def _normalize_role_models(role: str, value: Any, previous: dict[str, str]) -> dict[str, str]:
        normalized = dict(previous)

        if isinstance(value, str):
            normalized["ollama"] = value
            return normalized

        if not isinstance(value, dict):
            raise ModelManagerError(f"model config for role '{role}' must be a string or object")

        for runtime_name in ("ollama", "airllm"):
            runtime_value = value.get(runtime_name)
            if runtime_value is None:
                continue
            if not isinstance(runtime_value, str) or not runtime_value.strip():
                raise ModelManagerError(f"model config for role '{role}' and runtime '{runtime_name}' must be a string")
            normalized[runtime_name] = runtime_value.strip()

        return normalized

    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ModelManagerError(f"invalid model config JSON in {path}: {exc}") from exc

    @staticmethod
    def _get_role_for_task(task_type: str) -> str:
        normalized = task_type.strip().lower()
        if normalized not in SUPPORTED_TASK_TYPES:
            raise ModelManagerError(f"unsupported task type: {task_type}")
        return ROLE_BY_TASK_TYPE[normalized]

    @staticmethod
    def _detect_cpu_cores() -> int:
        cpu_cores = os.cpu_count()
        if cpu_cores is None or cpu_cores < 1:
            return 1
        return int(cpu_cores)
