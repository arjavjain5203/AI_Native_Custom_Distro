import json
from pathlib import Path

import pytest

from ai_core.models.manager import ModelManager, ModelManagerError, ModelState


class FakeOllamaClient:
    def __init__(self, installed_models: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str, float | None]] = []
        self.installed_models = installed_models or set()

    def generate(self, prompt: str, model: str | None = None, timeout_seconds: float | None = None) -> str:
        self.calls.append((prompt, model or "", timeout_seconds))
        return f"ollama:{model}"

    def list_installed_models(self) -> set[str]:
        return set(self.installed_models)


class FakeAirLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, model: str, **kwargs: object) -> str:
        self.calls.append((prompt, model))
        return f"airllm:{model}"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_manager(
    tmp_path: Path,
    *,
    system_payload: dict[str, object] | None = None,
    user_payload: dict[str, object] | None = None,
    ram_gb: float = 16.0,
    installed_models: set[str] | None = None,
) -> tuple[ModelManager, FakeOllamaClient, FakeAirLLMClient]:
    system_path = tmp_path / "system-models.json"
    user_path = tmp_path / "user-models.json"
    if system_payload is not None:
        write_json(system_path, system_payload)
    if user_payload is not None:
        write_json(user_path, user_payload)

    ollama = FakeOllamaClient(installed_models=installed_models)
    airllm = FakeAirLLMClient()
    manager = ModelManager(
        ollama_client=ollama,
        airllm_client=airllm,
        system_config_path=system_path,
        user_config_path=user_path,
        ram_gb_provider=lambda: ram_gb,
    )
    return manager, ollama, airllm


def test_model_manager_merges_configs_and_exposes_public_intent_role(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        system_payload={
            "runtime": "auto",
            "planning": {"ollama": "mistral:7b", "airllm": "mistral-air"},
            "coding": {"ollama": "codellama:7b"},
        },
        user_payload={
            "coding": {"airllm": "codellama-air"},
            "intent": {"ollama": "gemma:2b"},
        },
        installed_models={"gemma:2b", "mistral:7b", "codellama:7b"},
    )

    models = manager.get_models()

    assert models["runtime"] == "auto"
    assert "orchestrator" not in models
    assert models["planning"]["configured"] == {"ollama": "mistral:7b", "airllm": "mistral-air"}
    assert models["coding"]["configured"] == {"ollama": "codellama:7b", "airllm": "codellama-air"}
    assert models["intent"]["configured"]["ollama"] == "gemma:2b"
    assert models["intent"]["installed"] is True
    assert manager.get_model_for_role("intent") == "gemma:2b"
    assert manager.get_model_for_role("orchestrator") == "gemma:2b"


def test_model_manager_prefers_airllm_for_low_ram_planning_and_coding(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "auto",
            "planning": {"ollama": "mistral:7b", "airllm": "mistral-air"},
            "coding": {"ollama": "codellama:7b", "airllm": "codellama-air"},
        },
        ram_gb=8.0,
        installed_models={"phi3:mini"},
    )

    assert manager.get_runtime_for_task("planning") == "airllm"
    assert manager.get_model_for_task("planning") == "mistral-air"
    assert manager.get_runtime_for_task("coding") == "airllm"
    assert manager.get_model_for_task("coding") == "codellama-air"


def test_model_manager_keeps_intent_on_ollama_in_auto_mode(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "auto",
            "intent": {"ollama": "gemma:2b", "airllm": "gemma-air"},
        },
        ram_gb=8.0,
        installed_models={"gemma:2b"},
    )

    assert manager.get_runtime_for_task("planning") == "ollama"
    assert manager.get_runtime_for_task("analysis") == "ollama"
    assert manager.get_runtime_for_task("system") == "ollama"
    assert manager.get_runtime_for_task("coding") == "ollama"
    assert manager.get_runtime_status()["selected_runtime_by_role"]["intent"] == "ollama"
    assert manager.get_models()["intent"]["configured"]["ollama"] == "gemma:2b"


def test_model_manager_keeps_intent_on_ollama_even_when_runtime_is_airllm(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "airllm",
            "intent": {"ollama": "gemma:2b", "airllm": "gemma-air"},
            "planning": {"ollama": "mistral:7b", "airllm": "mistral-air"},
        },
        installed_models={"gemma:2b"},
    )

    status = manager.get_runtime_status()

    assert status["selected_runtime_by_role"]["intent"] == "ollama"
    assert status["selected_runtime_by_role"]["planning"] == "airllm"


def test_model_manager_uses_planning_model_for_analysis_by_default(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "auto",
            "planning": {"ollama": "mistral:7b", "airllm": "mistral-air"},
        },
        ram_gb=8.0,
        installed_models={"phi3:mini"},
    )

    assert manager.get_runtime_for_task("analysis") == "airllm"
    assert manager.get_model_for_task("analysis") == "mistral-air"


def test_model_manager_routes_to_correct_runtime_backend(tmp_path: Path) -> None:
    manager, ollama, airllm = build_manager(
        tmp_path,
        user_payload={
            "runtime": "auto",
            "planning": {"ollama": "mistral:7b", "airllm": "mistral-air"},
        },
        ram_gb=8.0,
        installed_models={"gemma:2b"},
    )

    air_output = manager.run_model("mistral-air", "plan task", task_type="planning")
    ollama_output = manager.run_model("gemma:2b", "route task", runtime="ollama")

    assert air_output == "airllm:mistral-air"
    assert ollama_output == "ollama:gemma:2b"
    assert airllm.calls == [("plan task", "mistral-air")]
    assert ollama.calls == [("route task", "gemma:2b", None)]


def test_model_manager_runtime_status_exposes_hardware_info(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={"runtime": "auto"},
        ram_gb=10.0,
        installed_models={"phi3"},
    )

    status = manager.get_runtime_status()

    assert status["detected_ram_gb"] == 10.0
    assert isinstance(status["cpu_cores"], int)
    assert status["cpu_cores"] >= 1


def test_model_manager_raises_when_forced_airllm_has_no_configured_model(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "airllm",
            "planning": {"ollama": "mistral:7b"},
        },
    )

    with pytest.raises(ModelManagerError, match="no AirLLM model configured"):
        manager.get_runtime_for_task("planning")


def test_model_manager_raises_when_required_ollama_model_is_missing(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "ollama",
            "coding": {"ollama": "qwen2.5-coder:7b"},
        },
        installed_models={"phi3", "mistral:7b"},
    )

    with pytest.raises(ModelManagerError, match="coding model missing: qwen2.5-coder:7b"):
        manager.run_model("qwen2.5-coder:7b", "update code", task_type="coding")


def test_model_manager_set_role_model_persists_public_intent_alias(tmp_path: Path) -> None:
    manager, _, _ = build_manager(
        tmp_path,
        installed_models={"phi3:mini"},
    )

    payload = manager.set_role_model("intent", "ollama", "gemma:2b")
    stored = json.loads((tmp_path / "user-models.json").read_text(encoding="utf-8"))

    assert "intent" in stored
    assert "orchestrator" not in stored
    assert stored["intent"]["ollama"] == "gemma:2b"
    assert payload["intent"]["configured"]["ollama"] == "gemma:2b"


def test_model_manager_tracks_download_and_failure_state(tmp_path: Path) -> None:
    manager, ollama, _ = build_manager(
        tmp_path,
        user_payload={
            "runtime": "ollama",
            "planning": {"ollama": "mistral:7b"},
        },
        installed_models={"phi3:mini"},
    )

    assert manager.get_model_state("planning") == ModelState.NOT_INSTALLED
    assert manager.is_model_available("planning") is False

    manager.mark_model_downloading("planning", "mistral:7b", {"status": "pulling manifest", "completed": 10, "total": 100})
    assert manager.get_model_state("planning") == ModelState.DOWNLOADING
    models = manager.get_models()
    assert models["planning"]["state"] == "DOWNLOADING"
    assert models["planning"]["progress"]["status"] == "pulling manifest"

    manager.mark_model_failed("planning", "mistral:7b", "network timeout")
    assert manager.get_model_state("planning") == ModelState.FAILED
    assert manager.get_model_error("planning") == "network timeout"

    ollama.installed_models.add("mistral:7b")
    manager.mark_model_installed("planning", "mistral:7b")
    assert manager.get_model_state("planning") == ModelState.INSTALLED
    assert manager.is_model_available("planning") is True
