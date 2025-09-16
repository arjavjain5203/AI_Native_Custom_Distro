"""In-memory working memory for active tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass(slots=True)
class WorkingMemoryEntry:
    """Active task state kept in memory while a task is running."""

    current_task_id: str
    current_plan: list[dict[str, Any]]
    step_index: int
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_task_id": self.current_task_id,
            "current_plan": list(self.current_plan),
            "step_index": self.step_index,
            "context": dict(self.context),
            "status": self.status,
        }


class WorkingMemoryStore:
    """Track task-scoped working memory for the daemon runtime."""

    def __init__(self) -> None:
        self._entries: dict[str, WorkingMemoryEntry] = {}
        self._lock = RLock()

    def create(
        self,
        task_id: str,
        current_plan: list[dict[str, Any]],
        *,
        context: dict[str, Any] | None = None,
        step_index: int = 0,
        status: str = "running",
    ) -> dict[str, Any]:
        """Create or replace working memory for a task."""
        self._validate_task_id(task_id)
        self._validate_plan(current_plan)
        self._validate_step_index(step_index)
        self._validate_status(status)
        context_dict = self._validate_context(context or {})

        with self._lock:
            entry = WorkingMemoryEntry(
                current_task_id=task_id,
                current_plan=list(current_plan),
                step_index=step_index,
                context=context_dict,
                status=status,
            )
            self._entries[task_id] = entry
            return entry.to_dict()

    def get(self, task_id: str) -> dict[str, Any] | None:
        """Return working memory for a task if present."""
        self._validate_task_id(task_id)
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                return None
            return entry.to_dict()

    def update_step_index(self, task_id: str, step_index: int, *, status: str | None = None) -> dict[str, Any]:
        """Update the current step pointer for a task."""
        self._validate_task_id(task_id)
        self._validate_step_index(step_index)
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                raise ValueError(f"working memory not found for task: {task_id}")
            entry.step_index = step_index
            if status is not None:
                self._validate_status(status)
                entry.status = status
            return entry.to_dict()

    def update_context(self, task_id: str, context: dict[str, Any], *, merge: bool = True) -> dict[str, Any]:
        """Update working-memory context for a task."""
        self._validate_task_id(task_id)
        context_dict = self._validate_context(context)
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                raise ValueError(f"working memory not found for task: {task_id}")
            entry.context = {**entry.context, **context_dict} if merge else context_dict
            return entry.to_dict()

    def set_status(self, task_id: str, status: str) -> dict[str, Any]:
        """Set the lifecycle status for a task."""
        self._validate_task_id(task_id)
        self._validate_status(status)
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                raise ValueError(f"working memory not found for task: {task_id}")
            entry.status = status
            return entry.to_dict()

    def clear(self, task_id: str) -> None:
        """Remove working memory for a task."""
        self._validate_task_id(task_id)
        with self._lock:
            self._entries.pop(task_id, None)

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")

    @staticmethod
    def _validate_step_index(step_index: int) -> None:
        if not isinstance(step_index, int) or step_index < 0:
            raise ValueError("step_index must be a non-negative integer")

    @staticmethod
    def _validate_plan(current_plan: list[dict[str, Any]]) -> None:
        if not isinstance(current_plan, list) or not all(isinstance(step, dict) for step in current_plan):
            raise ValueError("current_plan must be a list of serialized step objects")

    @staticmethod
    def _validate_context(context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(context, dict):
            raise ValueError("context must be a JSON object")
        return dict(context)

    @staticmethod
    def _validate_status(status: str) -> None:
        if not isinstance(status, str) or not status.strip():
            raise ValueError("status must be a non-empty string")
