"""Centralized execution pipeline for task orchestration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal
from uuid import uuid4

from ai_core.agents import AnalysisAgent, CodingAgent, ExecutorAgent, PlannerAgent
from ai_core.core.approvals import ApprovalStore
from ai_core.core.rollback import RollbackManager
from ai_core.core.session import SessionManager
from ai_core.core.step_runner import StepRunner
from ai_core.core.types import ExecutionOutcome, ExecutionState, PlanStep, TaskResult
from ai_core.memory import TaskHistoryStore, VectorStore, WorkingMemoryStore
from ai_core.models.orchestrator import Orchestrator
from ai_core.models.router import ModelRouter
from ai_core.tools import ToolRegistry


class ExecutionEngine:
    """Own the end-to-end execution pipeline outside the FastAPI layer."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        planner: PlannerAgent,
        executor: ExecutorAgent,
        coding_agent: CodingAgent,
        analysis_agent: AnalysisAgent,
        approval_store: ApprovalStore,
        history_store: TaskHistoryStore,
        working_memory_store: WorkingMemoryStore,
        rollback_manager: RollbackManager,
        session_manager: SessionManager,
        vector_store: VectorStore | None = None,
        tool_registry: ToolRegistry | None = None,
        step_runner: StepRunner | None = None,
    ) -> None:
        self.router = router
        self.planner = planner
        self.approval_store = approval_store
        self.history_store = history_store
        self.vector_store = vector_store or VectorStore()
        self.working_memory_store = working_memory_store
        self.session_manager = session_manager
        self.step_runner = step_runner or StepRunner(
            executor=executor,
            coding_agent=coding_agent,
            analysis_agent=analysis_agent,
            approval_store=approval_store,
            history_store=history_store,
            rollback_manager=rollback_manager,
            tool_registry=tool_registry,
        )

    def run_task(self, user_input: str, context: dict[str, Any]) -> ExecutionOutcome:
        """Run the full task pipeline and return a domain execution outcome."""
        command = user_input
        cwd = self._require_cwd(context)
        task_id = f"task-{uuid4().hex[:8]}"
        result: TaskResult
        created_state = False

        try:
            routing_context = self._build_routing_context(cwd, command)
            parent_task_id = self._resolve_parent_task_id(command, routing_context)
            decision = self.router.classify(command, routing_context, session_id=cwd)
            routing = asdict(self.router.selection_for_decision(decision))
            routing["mode"] = decision.get("mode")
            routing["confidence"] = decision.get("confidence")

            if decision.get("mode") == "conversation":
                result = self._build_conversation_result(command, cwd, routing)
                self._update_session_task_state(
                    cwd,
                    status="conversation",
                    task_type=str(routing.get("task_type", "planning")),
                    agent=str(routing.get("role", "planning")),
                    active_command=command,
                )
            else:
                planning_result = self.planner.plan_task(command)
                state = ExecutionState(
                    task_id=task_id,
                    command=command,
                    cwd=cwd,
                    steps=list(planning_result.steps),
                    step_index=0,
                    step_results=[],
                    routing=routing,
                    planning_metadata={
                        "source": planning_result.source,
                        "validation": planning_result.validation,
                    },
                    context={
                        **dict(context),
                        "parent_task_id": parent_task_id,
                    },
                    status="running",
                )
                self._store_execution_state(state)
                self._update_session_task_state(
                    cwd,
                    status="running",
                    task_type=str(routing.get("task_type", "planning")),
                    agent=str(routing.get("role", "planning")),
                    active_command=command,
                    task_id=task_id,
                )
                created_state = True
                if state.steps:
                    self.history_store.record_scratchpad(
                        task_id=task_id,
                        step_index=0,
                        category="validation",
                        payload={
                            "planning_source": planning_result.source,
                            "planning_validation": planning_result.validation,
                        },
                    )
                result = self._run_plan(state)
        except (ValueError, RuntimeError) as exc:
            result = TaskResult(
                success=False,
                message=str(exc),
                data={"status": "failed", "error_type": "runtime_error"},
            )
            parent_task_id = None

        self.history_store.record_task(
            task_id,
            command,
            cwd,
            result,
            parent_task_id=parent_task_id,
        )
        self._index_completed_task_summary(task_id, cwd, result)
        self._sync_session_result(cwd, task_id, command, result)
        if created_state:
            self._finalize_working_memory(task_id, str(result.data.get("status", "failed")))
        return ExecutionOutcome(
            task_id=task_id,
            command=command,
            cwd=cwd,
            result=result,
        )

    def resolve_approval(
        self,
        approval_id: str,
        token: str,
        decision: Literal["approve", "deny"],
    ) -> ExecutionOutcome:
        """Resolve an approval request and continue or cancel execution."""
        pending = self.approval_store.reject(approval_id, token) if decision == "deny" else self.approval_store.consume(
            approval_id, token
        )
        state = self._copy_execution_state(pending.state)
        result: TaskResult

        if decision == "deny":
            step = state.steps[state.step_index]
            self.history_store.record_execution_log(
                task_id=state.task_id,
                step_index=state.step_index,
                role=step.role,
                tool_name=step.tool_name,
                status="cancelled",
                payload={"reason": "approval_denied"},
            )
            state.status = "cancelled"
            if self.working_memory_store.get(state.task_id) is not None:
                self.working_memory_store.set_status(state.task_id, "cancelled")
            result = TaskResult(
                success=False,
                message="Approval denied.",
                steps=state.steps,
                data={
                    "status": "cancelled",
                    "routing": state.routing,
                    "step_results": list(state.step_results),
                },
            )
        else:
            state.status = "running"
            self._store_execution_state(state)
            result = self._run_plan(state)

        self.history_store.record_task(
            state.task_id,
            state.command,
            state.cwd,
            result,
            parent_task_id=self._state_parent_task_id(state),
        )
        self._index_completed_task_summary(state.task_id, state.cwd, result)
        self._sync_session_result(state.cwd, state.task_id, state.command, result)
        self._finalize_working_memory(state.task_id, str(result.data.get("status", "failed")))
        return ExecutionOutcome(
            task_id=state.task_id,
            command=state.command,
            cwd=state.cwd,
            result=result,
        )

    def _run_plan(self, state: ExecutionState) -> TaskResult:
        for index in range(state.step_index, len(state.steps)):
            state.step_index = index
            state.status = "running"
            self._store_execution_state(state)

            step = state.steps[index]
            step_result = self.step_runner.run(state, step)

            if step_result.status == "pending_approval":
                state.status = "pending_approval"
                self._store_execution_state(state)
                self._update_session_task_state(
                    state.cwd,
                    status="pending_approval",
                    task_type=str(state.routing.get("task_type", "planning")),
                    agent=str(state.routing.get("role", "planning")),
                    active_command=state.command,
                    task_id=state.task_id,
                )
                return TaskResult(
                    success=False,
                    message="Approval required before continuing.",
                    steps=state.steps,
                    data={
                        "status": "pending_approval",
                        "routing": state.routing,
                        "step_results": list(state.step_results),
                        "approval_request": asdict(step_result.approval_request),
                    },
                )

            if step_result.step_result_entry:
                state.step_results.append(step_result.step_result_entry)

            if step_result.status == "failed":
                state.status = "failed"
                self._store_execution_state(state)
                self._update_session_task_state(
                    state.cwd,
                    status="failed",
                    task_type=str(state.routing.get("task_type", "planning")),
                    agent=str(state.routing.get("role", "planning")),
                    active_command=state.command,
                    task_id=state.task_id,
                )
                return TaskResult(
                    success=False,
                    message=f"Step failed after retries: {step.description}",
                    steps=state.steps,
                    data={
                        "status": "failed",
                        "routing": state.routing,
                        "step_results": list(state.step_results),
                        "failed_step_index": index,
                        "failure_analysis": step_result.failure_analysis or {},
                    },
                )

            self._store_execution_state(state)

        state.status = "completed"
        self._update_session_task_state(
            state.cwd,
            status="completed",
            task_type=str(state.routing.get("task_type", "planning")),
            agent=str(state.routing.get("role", "planning")),
            active_command=state.command,
            task_id=state.task_id,
        )
        return TaskResult(
            success=True,
            message="Task completed successfully.",
            steps=state.steps,
            data={
                "status": "completed",
                "routing": state.routing,
                "step_results": list(state.step_results),
            },
        )

    def _build_routing_context(self, cwd: str, command: str) -> dict[str, Any]:
        return {
            "cwd": cwd,
            **self.session_manager.get_context(cwd),
            "related_tasks": self.vector_store.get_related_tasks(command, cwd, limit=3),
        }

    @staticmethod
    def _resolve_parent_task_id(command: str, routing_context: dict[str, Any]) -> str | None:
        current_task_state = routing_context.get("current_task_state")
        if not isinstance(current_task_state, dict):
            return None
        task_id = current_task_state.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return None
        if not Orchestrator._looks_like_continuation(command.lower()):
            return None
        return task_id

    @staticmethod
    def _state_parent_task_id(state: ExecutionState) -> str | None:
        parent_task_id = state.context.get("parent_task_id")
        if isinstance(parent_task_id, str) and parent_task_id.strip():
            return parent_task_id
        return None

    def _update_session_task_state(
        self,
        session_id: str,
        *,
        status: str,
        task_type: str,
        agent: str,
        active_command: str,
        task_id: str | None = None,
    ) -> None:
        self.session_manager.update(
            session_id,
            "",
            current_task_state={
                "status": status,
                "task_type": task_type,
                "agent": agent,
                "active_command": active_command,
                **({"task_id": task_id} if task_id is not None else {}),
            },
        )

    def _sync_session_result(self, cwd: str, task_id: str, command: str, result: TaskResult) -> None:
        routing = result.data.get("routing", {})
        if not isinstance(routing, dict):
            routing = {}
        status = str(result.data.get("status", "completed" if result.success else "failed"))
        if isinstance(result.data.get("conversation"), dict):
            status = "conversation"
        self._update_session_task_state(
            cwd,
            status=status,
            task_type=str(routing.get("task_type", "planning")),
            agent=str(routing.get("role", "planning")),
            active_command=command,
            task_id=task_id,
        )

    def _index_completed_task_summary(self, task_id: str, cwd: str, result: TaskResult) -> None:
        status = str(result.data.get("status", "completed" if result.success else "failed"))
        if status != "completed":
            return
        if isinstance(result.data.get("conversation"), dict):
            return
        stored_task = self.history_store.get_task(task_id)
        if stored_task is None:
            return
        summary = stored_task.get("task_summary")
        if not isinstance(summary, str) or not summary.strip():
            return
        self.vector_store.index_task_summary(task_id, cwd, summary)

    @staticmethod
    def _build_conversation_result(command: str, cwd: str, routing: dict[str, Any]) -> TaskResult:
        role = str(routing.get("role", "planning"))
        guidance_by_role = {
            "planning": "Conversation mode active. Clarify requirements or say what to execute next.",
            "coding": "Conversation mode active. Describe the code change in more detail or say to apply it.",
            "analysis": "Conversation mode active. Share the error, logs, or state you want analyzed.",
        }
        return TaskResult(
            success=True,
            message="Conversation mode active.",
            steps=[],
            data={
                "status": "completed",
                "routing": routing,
                "conversation": {
                    "mode": "conversation",
                    "agent": role,
                    "message": guidance_by_role.get(role, guidance_by_role["planning"]),
                    "command": command,
                    "cwd": cwd,
                },
            },
        )

    def _store_execution_state(self, state: ExecutionState) -> None:
        self.working_memory_store.create(
            state.task_id,
            self._serialize_plan_steps(state.steps),
            context={
                **dict(state.context),
                "routing": dict(state.routing),
                "planning_metadata": dict(state.planning_metadata),
                "step_results": list(state.step_results),
            },
            step_index=state.step_index,
            status=state.status,
        )

    def _finalize_working_memory(self, task_id: str, status: str) -> None:
        if status in {"completed", "failed", "cancelled"}:
            self.working_memory_store.clear(task_id)
            return
        if self.working_memory_store.get(task_id) is not None:
            self.working_memory_store.set_status(task_id, status)

    @staticmethod
    def _serialize_plan_steps(steps: list[PlanStep]) -> list[dict[str, Any]]:
        return [
            {
                "description": step.description,
                "role": step.role,
                "tool_name": step.tool_name,
                "args": step.args,
                "needs_retrieval": step.needs_retrieval,
                "requires_approval": step.requires_approval,
                "approval_category": step.approval_category,
            }
            for step in steps
        ]

    @staticmethod
    def _copy_execution_state(state: ExecutionState) -> ExecutionState:
        return ExecutionState(
            task_id=state.task_id,
            command=state.command,
            cwd=state.cwd,
            steps=list(state.steps),
            step_index=state.step_index,
            step_results=list(state.step_results),
            routing=dict(state.routing),
            planning_metadata=dict(state.planning_metadata),
            context=dict(state.context),
            status=state.status,
        )

    @staticmethod
    def _require_cwd(context: dict[str, Any]) -> str:
        cwd = str(context.get("cwd", "")).strip()
        if not cwd:
            raise ValueError("context must include a non-empty cwd")
        return cwd
