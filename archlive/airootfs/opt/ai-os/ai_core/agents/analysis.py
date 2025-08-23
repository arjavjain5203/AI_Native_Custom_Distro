"""Analysis agent for diagnostic tasks."""

from __future__ import annotations

from ai_core.core.types import AnalysisStepResult
from typing import Any

from ai_core.models.manager import ModelManager


class AnalysisAgent:
    """Analyze tool failures and system issues."""

    def __init__(self, model_manager: ModelManager | None = None) -> None:
        self.model_manager = model_manager or ModelManager()

    def execute_step(self, instruction: str, step_args: dict[str, Any]) -> AnalysisStepResult:
        self._validate_inputs(instruction, step_args)
        prompt = self._build_prompt(instruction, step_args)
        model_name = self.model_manager.get_model_for_task("analysis")
        response = self.model_manager.run_model(model_name, prompt, task_type="analysis")
        result = AnalysisStepResult(
            success=True,
            analysis=response.strip(),
            context=dict(step_args),
            validation={
                "context_keys": sorted(step_args.keys()),
                "analysis_length": len(response.strip()),
            },
        )
        self._validate_result(result)
        return result

    @staticmethod
    def _build_prompt(instruction: str, step_args: dict[str, Any]) -> str:
        return f"""
You are a diagnostics assistant for a local developer operating environment.

Instruction:
{instruction}

Context:
{step_args}

Explain the issue and suggest a concise next step.
""".strip()

    @staticmethod
    def _validate_inputs(instruction: str, step_args: dict[str, Any]) -> None:
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("analysis instruction must be a non-empty string")
        if not isinstance(step_args, dict):
            raise ValueError("analysis step args must be an object")

    @staticmethod
    def _validate_result(result: AnalysisStepResult) -> None:
        if not result.analysis:
            raise ValueError("analysis result must not be empty")
        if not isinstance(result.context, dict):
            raise ValueError("analysis result context must be an object")
        if not isinstance(result.validation, dict):
            raise ValueError("analysis result validation must be an object")
