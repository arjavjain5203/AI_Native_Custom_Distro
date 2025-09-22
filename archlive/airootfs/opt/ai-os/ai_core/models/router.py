"""Task classifier and model router."""

from __future__ import annotations

from typing import Any

from ai_core.core.types import ModelSelection
from ai_core.models.manager import ModelManager
from ai_core.models.orchestrator import Orchestrator


class ModelRouter:
    """Classify a task and resolve the model/provider that should handle it."""

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        orchestrator: Orchestrator | None = None,
    ) -> None:
        self.model_manager = model_manager or ModelManager()
        self.orchestrator = orchestrator or Orchestrator(model_manager=self.model_manager)

    def route(self, task: str, context: dict[str, Any] | None = None) -> ModelSelection:
        decision = self.classify(task, context)
        return self.selection_for_decision(decision)

    def classify(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the validated orchestrator decision."""
        routing_context = context or {}
        return self._classify_with_orchestrator(task, routing_context, session_id=session_id)

    def selection_for_decision(self, decision: dict[str, Any]) -> ModelSelection:
        """Resolve a model selection from a validated routing decision."""
        task_type = str(decision["task_type"])
        agent = str(decision["agent"])
        provider = self.model_manager.get_runtime_for_task(task_type)
        model_name = self.model_manager.get_model_for_task(task_type)
        return ModelSelection(
            task_type=task_type,
            role=agent,
            provider=provider,
            model_name=model_name,
        )

    def _classify_with_orchestrator(
        self,
        task: str,
        context: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            decision = self.orchestrator.classify_input(task, context, session_id=session_id)
        except Exception:
            decision = self.orchestrator.fallback_classification(task, context, session_id=session_id)
        return self._normalize_decision(decision)

    @staticmethod
    def _normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
        task_type = str(decision["task_type"])
        agent = str(decision["agent"])
        mode = str(decision["mode"])
        confidence = float(decision["confidence"])
        if task_type not in {"planning", "coding", "analysis", "system"}:
            raise ValueError(f"invalid orchestrator task type: {task_type}")
        if agent not in {"planning", "coding", "analysis"}:
            raise ValueError(f"invalid orchestrator agent: {agent}")
        if mode not in {"conversation", "execution"}:
            raise ValueError(f"invalid orchestrator mode: {mode}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("invalid orchestrator confidence")
        return {
            "mode": mode,
            "task_type": task_type,
            "agent": agent,
            "confidence": confidence,
        }
