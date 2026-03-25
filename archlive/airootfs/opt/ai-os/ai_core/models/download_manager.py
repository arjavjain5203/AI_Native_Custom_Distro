"""Background lifecycle manager for sequential Ollama model downloads."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from pathlib import Path
import threading
import time
from typing import Any

from ai_core.models.manager import ModelManager, ModelManagerError, ModelState
from ai_core.models.ollama import OllamaClient, OllamaError

DOWNLOAD_PRIORITY = ("orchestrator", "planning", "coding", "analysis")
RETRY_DELAYS_SECONDS = (0.0, 30.0, 120.0)
DEFAULT_ACTIVATION_MARKER = "/var/lib/ai-os/installer-complete"


@dataclass(order=True, slots=True)
class _DownloadQueueItem:
    priority: int
    sequence: int
    role: str = field(compare=False)
    model_name: str = field(compare=False)


class ModelDownloadManager:
    """Manage model downloads in a single background worker."""

    def __init__(
        self,
        *,
        model_manager: ModelManager,
        ollama_client: OllamaClient | None = None,
        activation_marker: str | Path = DEFAULT_ACTIVATION_MARKER,
        idle_sleep_seconds: float = 1.0,
        retry_delays_seconds: tuple[float, ...] = RETRY_DELAYS_SECONDS,
    ) -> None:
        self.model_manager = model_manager
        self.ollama_client = ollama_client or model_manager.ollama_client
        self.activation_marker = Path(activation_marker)
        self.idle_sleep_seconds = idle_sleep_seconds
        self.retry_delays_seconds = retry_delays_seconds
        self._queue: list[_DownloadQueueItem] = []
        self._queued_models: set[str] = set()
        self._current_model: str | None = None
        self._sequence = 0
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background worker."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="ai-os-model-downloads",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """Stop the background worker."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_seconds)

    def ensure_role_queued(self, role: str, *, clear_failed: bool = False) -> bool:
        """Ensure the configured role model is queued for download."""
        canonical_role = self._canonical_priority_role(role)
        runtime = self.model_manager.get_runtime_for_role(canonical_role)
        if runtime != "ollama":
            return False

        model_name = self.model_manager.get_model_name_for_role(canonical_role)
        state = self.model_manager.get_model_state(canonical_role)
        if state == ModelState.INSTALLED:
            return False
        if state == ModelState.FAILED and not clear_failed:
            return False
        if clear_failed:
            self.model_manager.clear_model_failure(canonical_role)

        with self._lock:
            if model_name == self._current_model or model_name in self._queued_models:
                return False
            self._sequence += 1
            heapq.heappush(
                self._queue,
                _DownloadQueueItem(
                    priority=DOWNLOAD_PRIORITY.index(canonical_role),
                    sequence=self._sequence,
                    role=canonical_role,
                    model_name=model_name,
                ),
            )
            self._queued_models.add(model_name)
            return True

    def ensure_configured_bundle_queued(self, *, clear_failed: bool = False) -> list[str]:
        """Queue all configured role models in priority order."""
        queued_roles: list[str] = []
        for role in DOWNLOAD_PRIORITY:
            try:
                if self.ensure_role_queued(role, clear_failed=clear_failed):
                    queued_roles.append(role)
            except ModelManagerError:
                continue
        return queued_roles

    def retry_role(self, role: str) -> dict[str, Any]:
        """Clear failure state and re-queue a role download."""
        queued = self.ensure_role_queued(role, clear_failed=True)
        model_name = self.model_manager.get_model_name_for_role(role)
        return {
            "queued": queued,
            "role": self._public_role_name(role),
            "model_name": model_name,
            "message": f"Model {model_name} is downloading. You can run basic tasks.",
        }

    def retry_all(self) -> dict[str, Any]:
        """Clear failures and re-queue the configured model bundle."""
        queued_roles = self.ensure_configured_bundle_queued(clear_failed=True)
        payload = self.model_manager.get_models()
        payload["queued_roles"] = [self._public_role_name(role) for role in queued_roles]
        payload["message"] = "Model downloads resumed."
        return payload

    def _run(self) -> None:
        while not self._stop_event.is_set():
            if not self._activation_ready():
                self._stop_event.wait(self.idle_sleep_seconds)
                continue

            self.ensure_configured_bundle_queued()
            item = self._pop_next_item()
            if item is None:
                self._stop_event.wait(self.idle_sleep_seconds)
                continue

            self._download_item(item)

    def _activation_ready(self) -> bool:
        return self.activation_marker.exists() and self.model_manager.has_complete_ollama_bundle()

    def _pop_next_item(self) -> _DownloadQueueItem | None:
        with self._lock:
            if not self._queue:
                return None
            item = heapq.heappop(self._queue)
            self._queued_models.discard(item.model_name)
            self._current_model = item.model_name
            return item

    def _download_item(self, item: _DownloadQueueItem) -> None:
        try:
            if self.model_manager.get_model_state(item.role) == ModelState.INSTALLED:
                return

            last_error = "download failed"
            for attempt, delay_seconds in enumerate(self.retry_delays_seconds, start=1):
                if self._stop_event.wait(delay_seconds):
                    return
                self.model_manager.mark_model_downloading(
                    item.role,
                    item.model_name,
                    progress={
                        "status": "starting",
                        "attempt": attempt,
                    },
                )
                try:
                    for progress in self.ollama_client.pull_model_progress(item.model_name):
                        self.model_manager.mark_model_downloading(
                            item.role,
                            item.model_name,
                            progress=self._normalize_progress(progress, attempt),
                        )
                    self.model_manager.refresh_installed_models()
                    self.model_manager.mark_model_installed(item.role, item.model_name)
                    return
                except (ModelManagerError, OllamaError, RuntimeError) as exc:
                    last_error = str(exc)
                    if attempt == len(self.retry_delays_seconds):
                        break
                    self.model_manager.mark_model_downloading(
                        item.role,
                        item.model_name,
                        progress={
                            "status": "retrying",
                            "attempt": attempt,
                            "error": last_error,
                            "next_retry_in_seconds": int(self.retry_delays_seconds[attempt]),
                        },
                    )

            self.model_manager.mark_model_failed(item.role, item.model_name, last_error)
        finally:
            with self._lock:
                if self._current_model == item.model_name:
                    self._current_model = None

    @staticmethod
    def _normalize_progress(progress: dict[str, Any], attempt: int) -> dict[str, Any]:
        payload = dict(progress)
        payload["attempt"] = attempt
        completed = payload.get("completed")
        total = payload.get("total")
        if isinstance(completed, int) and isinstance(total, int) and total > 0:
            payload["percent"] = round((completed / total) * 100, 2)
        return payload

    @staticmethod
    def _canonical_priority_role(role: str) -> str:
        normalized = role.strip().lower()
        if normalized == "intent":
            return "orchestrator"
        if normalized not in DOWNLOAD_PRIORITY:
            raise ModelManagerError(f"unsupported model role: {role}")
        return normalized

    @staticmethod
    def _public_role_name(role: str) -> str:
        return "intent" if role == "orchestrator" else role
