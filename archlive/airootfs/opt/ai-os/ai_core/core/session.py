"""Lightweight in-memory session tracking for orchestrator context."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass(slots=True)
class SessionState:
    """Short-lived session state for a single interaction scope."""

    session_id: str
    last_mode: str | None = None
    last_task_type: str | None = None
    last_agent: str | None = None
    recent_messages: list[str] = field(default_factory=list)
    current_task_state: dict[str, Any] | None = None

    def to_context(self) -> dict[str, object]:
        """Return a JSON-serializable context snapshot."""
        return {
            "last_mode": self.last_mode,
            "last_task_type": self.last_task_type,
            "last_agent": self.last_agent,
            "recent_messages": list(self.recent_messages),
            "current_task_state": dict(self.current_task_state) if self.current_task_state is not None else None,
        }


class SessionManager:
    """Manage short-lived session context for orchestrator prompts."""

    def __init__(self, max_messages: int = 6) -> None:
        self.max_messages = max_messages
        self._sessions: dict[str, SessionState] = {}
        self._lock = RLock()

    def get_context(self, session_id: str) -> dict[str, object]:
        """Return the current context for a session."""
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                return {
                    "last_mode": None,
                    "last_task_type": None,
                    "last_agent": None,
                    "recent_messages": [],
                    "current_task_state": None,
                }
            return state.to_context()

    def update(
        self,
        session_id: str,
        user_input: str,
        *,
        mode: str | None = None,
        task_type: str | None = None,
        agent: str | None = None,
        current_task_state: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        """Update a session with the latest input and routing metadata."""
        cleaned_input = user_input.strip()
        with self._lock:
            state = self._sessions.setdefault(session_id, SessionState(session_id=session_id))
            if cleaned_input:
                state.recent_messages.append(cleaned_input)
                if len(state.recent_messages) > self.max_messages:
                    state.recent_messages = state.recent_messages[-self.max_messages :]
            if mode is not None:
                state.last_mode = mode
            if task_type is not None:
                state.last_task_type = task_type
            if agent is not None:
                state.last_agent = agent
            if current_task_state is not None:
                state.current_task_state = self._validate_current_task_state(current_task_state)
            return state.to_context()

    def clear(self, session_id: str) -> None:
        """Remove a session and its context."""
        with self._lock:
            self._sessions.pop(session_id, None)

    @staticmethod
    def _validate_current_task_state(current_task_state: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(current_task_state, dict):
            raise ValueError("current_task_state must be a JSON object")
        return dict(current_task_state)
