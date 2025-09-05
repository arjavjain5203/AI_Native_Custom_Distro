"""Isolated single-step execution lifecycle."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_core.agents import AnalysisAgent, CodingAgent, ExecutorAgent
from ai_core.core.approvals import ApprovalStore
from ai_core.core.rollback import RollbackManager
from ai_core.core.types import ExecutionState, PlanStep, StepRunResult
from ai_core.memory.store import TaskHistoryStore
from ai_core.tools import ToolDefinition, ToolExecutionContext, ToolRegistry, ToolRegistryError, build_tool_registry


class StepRunner:
    """Handle approval, retry, rollback, and execution for one plan step."""

    def __init__(
        self,
        *,
        executor: ExecutorAgent,
        coding_agent: CodingAgent,
        analysis_agent: AnalysisAgent,
        approval_store: ApprovalStore,
        history_store: TaskHistoryStore,
        rollback_manager: RollbackManager,
        tool_registry: ToolRegistry | None = None,
        max_retries: int = 2,
    ) -> None:
        self.executor = executor
        self.coding_agent = coding_agent
        self.analysis_agent = analysis_agent
        self.approval_store = approval_store
        self.history_store = history_store
        self.rollback_manager = rollback_manager
        self.tool_registry = tool_registry or build_tool_registry()
        self.max_retries = max_retries

    def run(self, state: ExecutionState, step: PlanStep) -> StepRunResult:
        """Execute one step using the current execution state."""
        step_index = state.step_index
        tool_definition: ToolDefinition | None = None

        if step.role == "executor":
            try:
                tool_definition = self._prepare_executor_tool(step)
            except ToolRegistryError as exc:
                return self._build_failure_result(
                    state=state,
                    step=step,
                    error=str(exc),
                    attempt=0,
                )

        if step.requires_approval:
            approval = self.approval_store.create(state=state)
            self.history_store.record_execution_log(
                task_id=state.task_id,
                step_index=step_index,
                role=step.role,
                tool_name=step.tool_name,
                status="pending_approval",
                payload={"approval_category": step.approval_category},
            )
            self.history_store.record_scratchpad(
                task_id=state.task_id,
                step_index=step_index,
                category="validation",
                payload={"approval_required": True, "approval_category": step.approval_category},
            )
            return StepRunResult(
                status="pending_approval",
                step_index=step_index,
                step=step,
                approval_request=approval,
            )

        snapshot = None
        if step.role == "coding" or (tool_definition is not None and tool_definition.rollback_supported):
            snapshot = self.rollback_manager.maybe_create_snapshot(state.task_id, step_index, step, state.cwd)
        if snapshot is not None:
            self.history_store.record_scratchpad(
                task_id=state.task_id,
                step_index=step_index,
                category="validation",
                payload={"rollback_snapshot": snapshot},
            )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            self.history_store.record_execution_log(
                task_id=state.task_id,
                step_index=step_index,
                role=step.role,
                tool_name=step.tool_name,
                status="started",
                payload={
                    "description": step.description,
                    "args": step.args,
                    "attempt": attempt,
                },
            )
            try:
                step_output = self._dispatch_step(step, state.cwd, tool_definition=tool_definition)
                output_payload = self._normalize_payload(step_output)
                if step.role == "coding" and output_payload.get("success") is False:
                    self.history_store.record_execution_log(
                        task_id=state.task_id,
                        step_index=step_index,
                        role=step.role,
                        tool_name=step.tool_name,
                        status="failed",
                        payload=output_payload,
                    )
                    self.history_store.record_scratchpad(
                        task_id=state.task_id,
                        step_index=step_index,
                        category="tool_output",
                        payload=output_payload,
                    )
                    return self._build_failure_result(
                        state=state,
                        step=step,
                        error=str(output_payload.get("error") or "coding step failed"),
                        attempt=attempt,
                    )
                self.history_store.record_execution_log(
                    task_id=state.task_id,
                    step_index=step_index,
                    role=step.role,
                    tool_name=step.tool_name,
                    status="completed",
                    payload=output_payload,
                )
                self.history_store.record_scratchpad(
                    task_id=state.task_id,
                    step_index=step_index,
                    category="tool_output",
                    payload=output_payload,
                )
                return StepRunResult(
                    status="completed",
                    step_index=step_index,
                    step=step,
                    result=step_output,
                    step_result_entry={
                        "step": step.description,
                        "role": step.role,
                        "tool_name": step.tool_name,
                        "result": step_output,
                    },
                )
            except Exception as exc:
                last_error = exc
                self.history_store.record_execution_log(
                    task_id=state.task_id,
                    step_index=step_index,
                    role=step.role,
                    tool_name=step.tool_name,
                    status="retrying" if attempt <= self.max_retries else "failed",
                    payload={"error": str(exc), "attempt": attempt},
                )
                if snapshot is not None and attempt <= self.max_retries:
                    self.rollback_manager.restore_snapshot_payload(snapshot["type"], snapshot["state"])
                if attempt <= self.max_retries:
                    continue

                return self._build_failure_result(
                    state=state,
                    step=step,
                    error=str(exc),
                    attempt=attempt,
                )

        if last_error is not None:
            raise last_error
        raise RuntimeError("step runner ended without producing a result")

    def _dispatch_step(self, step: PlanStep, cwd: str, *, tool_definition: ToolDefinition | None) -> Any:
        instruction = str(step.args.get("instruction", step.description))
        if step.role == "coding":
            return asdict(self.coding_agent.execute_step(instruction, cwd, step.args))
        if step.role == "analysis":
            return asdict(self.analysis_agent.execute_step(instruction, step.args))
        return self._execute_tool_step(step, cwd, tool_definition=tool_definition)

    def _prepare_executor_tool(self, step: PlanStep) -> ToolDefinition:
        if not step.tool_name:
            raise ToolRegistryError(f"missing tool for step: {step.description}")
        if not isinstance(step.args, dict):
            raise ToolRegistryError("executor step args must be an object")

        tool_definition = self.tool_registry.require(step.tool_name)
        self.tool_registry.validate_args(step.tool_name, step.args)

        if tool_definition.requires_approval:
            step.requires_approval = True
            if not step.approval_category:
                step.approval_category = tool_definition.category

        return tool_definition

    def _execute_tool_step(self, step: PlanStep, cwd: str, *, tool_definition: ToolDefinition | None) -> dict[str, Any]:
        if tool_definition is None:
            raise ToolRegistryError("executor step missing tool definition")

        result = self.tool_registry.execute(
            tool_definition.name,
            step.args,
            ToolExecutionContext(
                cwd=cwd,
                metadata={
                    "role": step.role,
                    "tool_name": step.tool_name,
                },
            ),
        )
        if not result.success:
            raise RuntimeError(result.error or f"tool execution failed: {tool_definition.name}")

        return {
            "success": True,
            "tool_name": tool_definition.name,
            "output": result.output,
            "validation": {
                "cwd": cwd,
                "args_validated": True,
                "tool_supported": True,
                "tool_source": tool_definition.source,
                "tool_category": tool_definition.category,
                "requires_approval": step.requires_approval,
                "rollback_supported": tool_definition.rollback_supported,
            },
        }

    def _build_failure_result(
        self,
        *,
        state: ExecutionState,
        step: PlanStep,
        error: str,
        attempt: int,
    ) -> StepRunResult:
        failure_context = {
            "error": error,
            "attempts": attempt,
            "tool_name": step.tool_name,
            "role": step.role,
            "args": step.args,
        }
        failure_analysis = asdict(
            self.analysis_agent.execute_step(
                f"Analyze failure for step: {step.description}",
                failure_context,
            )
        )
        return StepRunResult(
            status="failed",
            step_index=state.step_index,
            step=step,
            result={
                "error": error,
                "retry_attempts": attempt,
                "analysis": failure_analysis,
            },
            step_result_entry={
                "step": step.description,
                "role": step.role,
                "tool_name": step.tool_name,
                "result": {
                    "error": error,
                    "retry_attempts": attempt,
                    "analysis": failure_analysis,
                },
            },
            failure_analysis=failure_analysis,
        )

    @staticmethod
    def _normalize_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {"value": value}
