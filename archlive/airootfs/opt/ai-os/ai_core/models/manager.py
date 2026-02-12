"""Model manager for runtime selection, lifecycle state, and backend dispatch."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
import threading
from typing import Any, Callable

from ai_core.core.config import (
    DEFAULT_MODEL_RUNTIME,
    LOW_MEMORY_THRESHOLD_GB,
    OLLAMA_ANALYSIS_MODEL,
    OLLAMA_CODING_MODEL,
    OLLAMA_INTENT_MODEL,
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
CANONICAL_ROLES = ("orchestrator", "planning", "coding", "analysis")
PUBLIC_ROLE_BY_CANONICAL = {
    "orchestrator": "intent",
    "planning": "planning",
    "coding": "coding",
    "analysis": "analysis",
}
CANONICAL_ROLE_BY_PUBLIC = {
    "intent": "orchestrator",
    "orchestrator": "orchestrator",
    "planning": "planning",
    "coding": "coding",
    "analysis": "analysis",
}
ROLE_BY_TASK_TYPE = {
    "coding": "coding",
    "planning": "planning",
    "system": "planning",
    "analysis": "analysis",
}


class ModelState(str, Enum):
    """Lifecycle state for a configured role model."""

    NOT_INSTALLED = "NOT_INSTALLED"
    DOWNLOADING = "DOWNLOADING"
    INSTALLED = "INSTALLED"
    FAILED = "FAILED"


class ModelManagerError(RuntimeError):
    """Raised when model selection or execution cannot be completed."""


class ModelManager:
    """Central runtime selector and lifecycle state owner for model execution."""

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
        self._state_lock = threading.RLock()
        self._installed_models_cache: set[str] = set()
        self._downloading_models: dict[str, dict[str, Any]] = {}
        self._failed_models: dict[str, str] = {}
        if hardware_provider is not None:
            self.hardware_provider = hardware_provider
        elif ram_gb_provider is not None:
            self.hardware_provider = lambda: {
                "ram_gb": ram_gb_provider(),
                "cpu_cores": self._detect_cpu_cores(),
            }
        else:
            self.hardware_provider = detect_hardware_info

        try:
            self.refresh_installed_models()
        except ModelManagerError:
            # Startup should remain non-blocking when Ollama is not ready yet.
            pass

    def get_models(self) -> dict[str, Any]:
        """Return the effective model configuration plus lifecycle status."""
        config = self._load_effective_config()
        payload: dict[str, Any] = {"runtime": config["runtime"]}
        installed_models_error: str | None = None
        try:
            self.refresh_installed_models()
        except ModelManagerError as exc:
            installed_models_error = str(exc)
        for role in CANONICAL_ROLES:
            payload[self._public_role_name(role)] = self._build_role_status(
                role,
                config,
                installed_models_error=installed_models_error,
            )
        return payload

    def get_runtime_status(self) -> dict[str, Any]:
        """Return configured and effective runtime information."""
        effective_by_role: dict[str, str | None] = {}
        issues: dict[str, str] = {}
        hardware_info = self.get_hardware_info()

        for role in CANONICAL_ROLES:
            try:
                effective_by_role[self._public_role_name(role)] = self.get_runtime_for_role(role)
            except ModelManagerError as exc:
                effective_by_role[self._public_role_name(role)] = None
                issues[self._public_role_name(role)] = str(exc)

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
        normalized_role = self._canonical_role_name(role)
        normalized_runtime = runtime.strip().lower()
        if normalized_runtime not in ("ollama", "airllm"):
            raise ModelManagerError(f"unsupported model runtime: {runtime}")
        if not model_name.strip():
            raise ModelManagerError("model name must be a non-empty string")

        user_config = self._load_json_file(self.user_config_path)
        role_key = self._public_role_name(normalized_role)
        role_config = user_config.get(role_key, user_config.get(normalized_role, {}))
        if isinstance(role_config, str):
            role_config = {"ollama": role_config}
        if not isinstance(role_config, dict):
            raise ModelManagerError(f"invalid existing model config for role '{normalized_role}'")
        role_config[normalized_runtime] = model_name.strip()
        user_config[role_key] = role_config
        if role_key != normalized_role:
            user_config.pop(normalized_role, None)

        self.user_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_config_path.write_text(
            json.dumps(user_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return self.get_models()

    def get_model_for_task(self, task_type: str) -> str:
        """Return the configured model identifier for the task type."""
        role = self._get_role_for_task(task_type)
        return self.get_model_for_role(role)

    def get_model_for_role(self, role: str) -> str:
        """Return the configured model identifier for the role."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        return self._get_model_for_role(canonical_role, runtime)

    def get_model_name_for_role(self, role: str) -> str:
        """Return the configured model name for the role."""
        return self.get_model_for_role(role)

    def get_runtime_for_task(self, task_type: str) -> str:
        """Return the runtime selected for the task type."""
        role = self._get_role_for_task(task_type)
        return self.get_runtime_for_role(role)

    def get_runtime_for_role(self, role: str) -> str:
        """Return the runtime selected for the role."""
        canonical_role = self._canonical_role_name(role)
        return self._select_runtime_for_role(canonical_role)

    def get_model_state(self, role: str) -> ModelState:
        """Return the lifecycle state for the configured role model."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        if runtime != "ollama":
            return ModelState.INSTALLED

        try:
            self.refresh_installed_models()
        except ModelManagerError:
            pass

        model_name = self._get_model_for_role(canonical_role, runtime)
        with self._state_lock:
            return self._state_for_model_locked(model_name)

    def is_model_available(self, role: str) -> bool:
        """Return whether the role model can be executed immediately."""
        return self.get_model_state(role) == ModelState.INSTALLED

    def get_model_progress(self, role: str) -> dict[str, Any] | None:
        """Return the latest download progress snapshot for a role, if any."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        if runtime != "ollama":
            return None
        model_name = self._get_model_for_role(canonical_role, runtime)
        with self._state_lock:
            progress = self._downloading_models.get(model_name)
            if progress is None:
                return None
            return dict(progress)

    def get_model_error(self, role: str) -> str | None:
        """Return the recorded failure for a role model, if any."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        if runtime != "ollama":
            return None
        model_name = self._get_model_for_role(canonical_role, runtime)
        with self._state_lock:
            return self._failed_models.get(model_name)

    def configured_ollama_models_by_role(self) -> dict[str, str]:
        """Return configured Ollama model names keyed by canonical role."""
        config = self._load_effective_config()
        models: dict[str, str] = {}
        for role in CANONICAL_ROLES:
            role_models = config[role]
            model_name = role_models.get("ollama")
            if isinstance(model_name, str) and model_name.strip():
                models[role] = model_name.strip()
        return models

    def has_complete_ollama_bundle(self) -> bool:
        """Return whether every canonical role has an Ollama model configured."""
        configured = self.configured_ollama_models_by_role()
        return all(role in configured for role in CANONICAL_ROLES)

    def refresh_installed_models(self) -> set[str]:
        """Refresh the installed-model cache from Ollama."""
        installed = self._list_installed_ollama_models()
        with self._state_lock:
            self._installed_models_cache = set(installed)
            for model_name in list(self._downloading_models):
                if model_name in self._installed_models_cache:
                    self._downloading_models.pop(model_name, None)
            for model_name in list(self._failed_models):
                if model_name in self._installed_models_cache:
                    self._failed_models.pop(model_name, None)
            return set(self._installed_models_cache)

    def mark_model_downloading(
        self,
        role: str,
        model_name: str,
        progress: dict[str, Any] | None = None,
    ) -> None:
        """Mark a model as downloading and store the latest progress snapshot."""
        canonical_role = self._canonical_role_name(role)
        payload = {
            "role": self._public_role_name(canonical_role),
            "status": "downloading",
            **(dict(progress) if progress is not None else {}),
        }
        with self._state_lock:
            self._failed_models.pop(model_name, None)
            self._downloading_models[model_name] = payload

    def mark_model_installed(self, role: str, model_name: str) -> None:
        """Mark a model as installed."""
        self._canonical_role_name(role)
        with self._state_lock:
            self._installed_models_cache.add(model_name)
            self._downloading_models.pop(model_name, None)
            self._failed_models.pop(model_name, None)

    def mark_model_failed(self, role: str, model_name: str, error: str) -> None:
        """Mark a model download as failed."""
        self._canonical_role_name(role)
        with self._state_lock:
            self._downloading_models.pop(model_name, None)
            self._failed_models[model_name] = error

    def clear_model_failure(self, role: str) -> None:
        """Clear a recorded model failure for the role's configured model."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        if runtime != "ollama":
            return
        model_name = self._get_model_for_role(canonical_role, runtime)
        with self._state_lock:
            self._failed_models.pop(model_name, None)

    def run_role_model(
        self,
        role: str,
        prompt: str,
        *,
        timeout_seconds: float | None = None,
    ) -> str:
        """Run the configured model for a role through the selected backend."""
        canonical_role = self._canonical_role_name(role)
        runtime = self.get_runtime_for_role(canonical_role)
        model_name = self._get_model_for_role(canonical_role, runtime)
        return self.run_model(
            model_name,
            prompt,
            runtime=runtime,
            role=canonical_role,
            timeout_seconds=timeout_seconds,
        )

    def run_model(
        self,
        model_name: str,
        prompt: str,
        *,
        runtime: str | None = None,
        task_type: str | None = None,
        role: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        """Run a model through the selected backend."""
        selected_runtime = self._resolve_runtime_argument(runtime, task_type, role, model_name)

        if selected_runtime == "ollama":
            self._require_installed_ollama_model(model_name, task_type=task_type, role=role)
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

    def _resolve_runtime_argument(
        self,
        runtime: str | None,
        task_type: str | None,
        role: str | None,
        model_name: str,
    ) -> str:
        if runtime is not None:
            if runtime not in SUPPORTED_RUNTIMES - {"auto"}:
                raise ModelManagerError(f"unsupported runtime override: {runtime}")
            return runtime

        if role is not None:
            return self.get_runtime_for_role(role)

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
        explicit_analysis_config = False

        for config_path in (self.system_config_path, self.user_config_path):
            file_config = self._load_json_file(config_path)
            if not file_config:
                continue

            runtime = file_config.get("runtime")
            if runtime is not None:
                merged["runtime"] = self._normalize_runtime(runtime)

            for role in CANONICAL_ROLES:
                if role in file_config:
                    merged[role] = self._normalize_role_models(role, file_config[role], merged[role])
                    if role == "analysis":
                        explicit_analysis_config = True
            if "intent" in file_config:
                merged["orchestrator"] = self._normalize_role_models(
                    "orchestrator",
                    file_config["intent"],
                    merged["orchestrator"],
                )
            if "orchestrator" in file_config:
                merged["orchestrator"] = self._normalize_role_models(
                    "orchestrator",
                    file_config["orchestrator"],
                    merged["orchestrator"],
                )

        if not explicit_analysis_config:
            merged["analysis"] = dict(merged["planning"])

        return merged

    def _default_config(self) -> dict[str, Any]:
        analysis_defaults = {"ollama": OLLAMA_ANALYSIS_MODEL}
        if not analysis_defaults["ollama"]:
            analysis_defaults = {"ollama": OLLAMA_PLANNING_MODEL}
        return {
            "runtime": self._normalize_runtime(self.default_runtime),
            "orchestrator": {"ollama": OLLAMA_ORCHESTRATOR_MODEL or OLLAMA_INTENT_MODEL},
            "planning": {"ollama": OLLAMA_PLANNING_MODEL},
            "coding": {"ollama": OLLAMA_CODING_MODEL},
            "analysis": analysis_defaults,
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

    def _build_role_status(
        self,
        role: str,
        config: dict[str, Any],
        *,
        installed_models_error: str | None = None,
    ) -> dict[str, Any]:
        role_models = dict(config[role])
        runtime: str | None = None
        error: str | None = None
        model_name: str | None = None
        installed = False
        public_role = self._public_role_name(role)
        state = ModelState.NOT_INSTALLED
        progress: dict[str, Any] | None = None

        try:
            runtime = self.get_runtime_for_role(role)
            model_name = self._get_model_for_role(role, runtime)
            state = self.get_model_state(role)
            progress = self.get_model_progress(role)
            installed = state == ModelState.INSTALLED or runtime != "ollama"
            if runtime == "ollama":
                if state == ModelState.FAILED:
                    error = self.get_model_error(role) or "download failed"
                elif state == ModelState.NOT_INSTALLED:
                    error = f"{public_role} model missing: {model_name}"
                elif installed_models_error is not None and state != ModelState.DOWNLOADING:
                    error = installed_models_error
        except ModelManagerError as exc:
            error = str(exc)

        payload: dict[str, Any] = {
            "configured": role_models,
            "runtime": runtime,
            "model_name": model_name,
            "installed": installed,
            "state": state.value,
        }
        if progress is not None:
            payload["progress"] = progress
        if error is not None:
            payload["error"] = error
        return payload

    def _require_installed_ollama_model(
        self,
        model_name: str,
        *,
        task_type: str | None = None,
        role: str | None = None,
    ) -> None:
        try:
            self.refresh_installed_models()
        except ModelManagerError:
            pass
        with self._state_lock:
            state = self._state_for_model_locked(model_name)

        if state == ModelState.INSTALLED:
            return
        if state == ModelState.DOWNLOADING:
            raise ModelManagerError(f"Model {model_name} is downloading. You can run basic tasks.")
        if state == ModelState.FAILED:
            raise ModelManagerError("Required model failed to install. Please retry installation.")
        if role is not None:
            role_name = self._public_role_name(self._canonical_role_name(role))
        elif task_type is not None:
            role_name = self._public_role_name(self._get_role_for_task(task_type))
        else:
            role_name = "model"
        raise ModelManagerError(f"{role_name} model missing: {model_name}")

    def _list_installed_ollama_models(self) -> set[str]:
        try:
            return self.ollama_client.list_installed_models()
        except AttributeError as exc:
            raise ModelManagerError("ollama client does not support installed model lookup") from exc
        except RuntimeError as exc:
            raise ModelManagerError(str(exc)) from exc

    def _state_for_model_locked(self, model_name: str) -> ModelState:
        if model_name in self._installed_models_cache:
            return ModelState.INSTALLED
        if model_name in self._downloading_models:
            return ModelState.DOWNLOADING
        if model_name in self._failed_models:
            return ModelState.FAILED
        return ModelState.NOT_INSTALLED

    @staticmethod
    def _public_role_name(role: str) -> str:
        return PUBLIC_ROLE_BY_CANONICAL[role]

    @staticmethod
    def _canonical_role_name(role: str) -> str:
        normalized = role.strip().lower()
        if normalized not in CANONICAL_ROLE_BY_PUBLIC:
            raise ModelManagerError(f"unsupported model role: {role}")
        return CANONICAL_ROLE_BY_PUBLIC[normalized]

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
