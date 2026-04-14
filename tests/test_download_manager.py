import json
from pathlib import Path
import time

from ai_core.models.download_manager import ModelDownloadManager
from ai_core.models.manager import ModelManager, ModelState


class FakeDownloadOllamaClient:
    def __init__(
        self,
        *,
        installed_models: set[str] | None = None,
        failures_before_success: dict[str, int] | None = None,
    ) -> None:
        self.installed_models = installed_models or set()
        self.failures_before_success = failures_before_success or {}
        self.pull_calls: list[str] = []
        self.pull_attempts: dict[str, int] = {}

    def generate(self, prompt: str, model: str | None = None, timeout_seconds: float | None = None) -> str:
        return "[]"

    def list_installed_models(self) -> set[str]:
        return set(self.installed_models)

    def pull_model_progress(self, model: str, *, timeout_seconds: float | None = None):
        self.pull_calls.append(model)
        self.pull_attempts[model] = self.pull_attempts.get(model, 0) + 1
        remaining_failures = self.failures_before_success.get(model, 0)
        if remaining_failures > 0:
            self.failures_before_success[model] = remaining_failures - 1
            raise RuntimeError(f"failed to pull {model}")
        yield {"status": "pulling manifest", "completed": 10, "total": 100}
        yield {"status": "success", "completed": 100, "total": 100}
        self.installed_models.add(model)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_manager(tmp_path: Path, ollama_client: FakeDownloadOllamaClient) -> ModelManager:
    system_path = tmp_path / "system-models.json"
    user_path = tmp_path / "user-models.json"
    write_json(
        user_path,
        {
            "runtime": "ollama",
            "intent": {"ollama": "phi3:mini"},
            "planning": {"ollama": "mistral:7b"},
            "coding": {"ollama": "qwen2.5-coder:1.5b"},
            "analysis": {"ollama": "mistral:7b"},
        },
    )
    return ModelManager(
        ollama_client=ollama_client,
        system_config_path=system_path,
        user_config_path=user_path,
        ram_gb_provider=lambda: 8.0,
    )


def wait_for(predicate, *, timeout_seconds: float = 1.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_download_manager_waits_for_activation_and_preserves_priority_order(tmp_path: Path) -> None:
    activation_marker = tmp_path / "installer-complete"
    ollama = FakeDownloadOllamaClient()
    manager = build_manager(tmp_path, ollama)
    download_manager = ModelDownloadManager(
        model_manager=manager,
        ollama_client=ollama,
        activation_marker=activation_marker,
        idle_sleep_seconds=0.01,
        retry_delays_seconds=(0.0, 0.01, 0.01),
    )
    download_manager.start()
    try:
        time.sleep(0.05)
        assert ollama.pull_calls == []

        activation_marker.touch()
        wait_for(lambda: manager.get_model_state("coding") == ModelState.INSTALLED)

        assert ollama.pull_calls == ["phi3:mini", "mistral:7b", "qwen2.5-coder:1.5b"]
        assert manager.get_model_state("intent") == ModelState.INSTALLED
        assert manager.get_model_state("planning") == ModelState.INSTALLED
        assert manager.get_model_state("analysis") == ModelState.INSTALLED
    finally:
        download_manager.stop()


def test_download_manager_marks_failed_model_and_allows_manual_retry(tmp_path: Path) -> None:
    activation_marker = tmp_path / "installer-complete"
    activation_marker.touch()
    ollama = FakeDownloadOllamaClient(
        installed_models={"mistral:7b", "qwen2.5-coder:1.5b"},
        failures_before_success={"phi3:mini": 3},
    )
    manager = build_manager(tmp_path, ollama)
    download_manager = ModelDownloadManager(
        model_manager=manager,
        ollama_client=ollama,
        activation_marker=activation_marker,
        idle_sleep_seconds=0.01,
        retry_delays_seconds=(0.0, 0.01, 0.01),
    )
    download_manager.start()
    try:
        wait_for(lambda: manager.get_model_state("intent") == ModelState.FAILED)
        assert manager.get_model_error("intent") == "failed to pull phi3:mini"

        response = download_manager.retry_role("intent")
        assert response["message"] == "Model phi3:mini is downloading. You can run basic tasks."
        wait_for(lambda: manager.get_model_state("intent") == ModelState.INSTALLED)
    finally:
        download_manager.stop()
