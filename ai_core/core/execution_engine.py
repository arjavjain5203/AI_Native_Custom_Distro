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
from ai_core.core.types import ExecutionOutcome, ExecutionState, PlanStep, PlanningResult, TaskResult
from ai_core.memory import TaskHistoryStore, VectorStore, WorkingMemoryStore
from ai_core.models.download_manager import ModelDownloadManager
from ai_core.models.manager import ModelManager, ModelManagerError, ModelState
from ai_core.models.orchestrator import Orchestrator
from ai_core.models.router import ModelRouter
from ai_core.tools import ToolRegistry

ORCHESTRATOR_MISSING_MESSAGE = (
    "Orchestrator model is not installed yet. Please wait while it is downloading. "
    "You can continue using normal terminal commands."
)
DOWNLOAD_MESSAGE_TEMPLATE = "Model {name} is downloading. You can run basic tasks."
FALLBACK_MESSAGE = "Using a smaller model because the preferred model is still downloading."
BLOCK_MESSAGE = "This task requires a more capable model. Please wait for the model to finish downloading."
FAILED_INSTALL_MESSAGE = "Required model failed to install. Please retry installation."


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
        model_manager: ModelManager | None = None,
        download_manager: ModelDownloadManager | None = None,
    ) -> None:
        self.router = router
        self.planner = planner
        self.approval_store = approval_store
        self.history_store = history_store
        self.vector_store = vector_store or VectorStore()
        self.working_memory_store = working_memory_store
        self.session_manager = session_manager
        self.model_manager = model_manager or getattr(router, "model_manager", None) or getattr(planner, "model_manager", None)
        self.download_manager = download_manager
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
        parent_task_id: str | None = None

        try:
            routing_context = self._build_routing_context(cwd, command)
            parent_task_id = self._resolve_parent_task_id(command, routing_context)

            orchestrator_gate = self._guard_orchestrator()
            if orchestrator_gate is not None:
                result = orchestrator_gate
                self._update_session_task_state(
                    cwd,
                    status="failed",
                    task_type="planning",
                    agent="planning",
                    active_command=command,
                    task_id=task_id,
                )
            else:
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
                    planning_result, model_notices, planning_block = self._plan_with_lifecycle(command)
                    if planning_block is not None or planning_result is None:
                        result = planning_block or self._build_lifecycle_failure(
                            message=BLOCK_MESSAGE,
                            errors=[{"message": BLOCK_MESSAGE, "type": "model_unavailable"}],
                            routing=routing,
                        )
                        self._update_session_task_state(
                            cwd,
                            status="failed",
                            task_type=str(routing.get("task_type", "planning")),
                            agent=str(routing.get("role", "planning")),
                            active_command=command,
                            task_id=task_id,
                        )
                    else:
                        task_complexity = "simple" if self._is_simple_task(planning_result.steps) else "complex"
                        state = ExecutionState(
                            task_id=task_id,
                            command=command,
                            cwd=cwd,
                            steps=list(planning_result.steps),
                            step_index=0,
                            step_results=[],
                            files_modified=[],
                            steps_completed=[],
                            errors=[],
                            routing=routing,
                            planning_metadata={
                                "source": planning_result.source,
                                "validation": planning_result.validation,
                            },
                            context={
                                **dict(context),
                                "parent_task_id": parent_task_id,
                                "task_complexity": task_complexity,
                                "model_notices": list(model_notices),
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
                                category="model_response",
                                payload={
                                    "routing_decision": decision,
                                    "planner_steps": self._serialize_plan_steps(state.steps),
                                },
                            )
                            self.history_store.record_scratchpad(
                                task_id=task_id,
                                step_index=0,
                                category="validation",
                                payload={
                                    "planning_source": planning_result.source,
                                    "planning_validation": planning_result.validation,
                                    "task_complexity": task_complexity,
                                    "model_notices": list(model_notices),
                                },
                            )
                        result = self._run_plan(state)
        except (ValueError, RuntimeError, ModelManagerError) as exc:
            result = TaskResult(
                success=False,
                message=str(exc),
                data={
                    "status": "failed",
                    "error_type": "runtime_error",
                    "files_modified": [],
                    "steps_completed": [],
                    "errors": [{"message": str(exc), "type": "runtime_error"}],
                },
            )

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
                    "files_modified": list(state.files_modified),
                    "steps_completed": list(state.steps_completed),
                    "errors": list(state.errors),
                    "model_notices": list(state.context.get("model_notices", [])),
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
        task_is_simple = str(state.context.get("task_complexity", "complex")) == "simple"

        for index in range(state.step_index, len(state.steps)):
            state.step_index = index
            state.status = "running"
            self._store_execution_state(state)

            step = state.steps[index]
            execution_step, block_result = self._prepare_step_for_execution(step, task_is_simple, state)
            if block_result is not None:
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
                return self._merge_state_into_result(state, block_result)
            state.steps[index] = execution_step

            step_result = self.step_runner.run(state, execution_step)

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
                        "files_modified": list(state.files_modified),
                        "steps_completed": list(state.steps_completed),
                        "errors": list(state.errors),
                        "model_notices": list(state.context.get("model_notices", [])),
                        "approval_request": asdict(step_result.approval_request),
                    },
                )

            if step_result.step_result_entry:
                state.step_results.append(step_result.step_result_entry)
            if step_result.status == "completed":
                state.steps_completed.append(
                    {
                        "step_index": index,
                        "step": step.description,
                        "role": step.role,
                        "tool_name": step.tool_name,
                    }
                )
            for modified_path in step_result.files_modified:
                if modified_path not in state.files_modified:
                    state.files_modified.append(modified_path)

            if step_result.status == "failed":
                state.errors.append(
                    {
                        "step_index": index,
                        "step": step.description,
                        "role": step.role,
                        "tool_name": step.tool_name,
                        "message": str(step_result.result.get("error", "")) if isinstance(step_result.result, dict) else "",
                    }
                )
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
                        "files_modified": list(state.files_modified),
                        "steps_completed": list(state.steps_completed),
                        "errors": list(state.errors),
                        "failed_step_index": index,
                        "failure_analysis": step_result.failure_analysis or {},
                        "model_notices": list(state.context.get("model_notices", [])),
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
        notices = list(state.context.get("model_notices", []))
        return TaskResult(
            success=True,
            message=notices[-1] if notices else "Task completed successfully.",
            steps=state.steps,
            data={
                "status": "completed",
                "routing": state.routing,
                "step_results": list(state.step_results),
                "files_modified": list(state.files_modified),
                "steps_completed": list(state.steps_completed),
                "errors": list(state.errors),
                "model_notices": notices,
            },
        )

    def _build_routing_context(self, cwd: str, command: str) -> dict[str, Any]:
        return {
            "cwd": cwd,
            **self.session_manager.get_context(cwd),
            "related_tasks": self.vector_store.get_related_tasks(command, cwd, limit=3),
        }

    def _guard_orchestrator(self) -> TaskResult | None:
        if self.model_manager is None:
            return None

        role = "orchestrator"
        state = self.model_manager.get_model_state(role)
        model_name = self.model_manager.get_model_name_for_role(role)
        if state == ModelState.INSTALLED:
            return None
        if state == ModelState.NOT_INSTALLED:
            self._enqueue_download(role)
            return self._build_lifecycle_failure(
                message=ORCHESTRATOR_MISSING_MESSAGE,
                role=role,
                model_name=model_name,
                model_state=ModelState.DOWNLOADING,
                notices=[self._download_message(model_name)],
            )
        if state == ModelState.DOWNLOADING:
            return self._build_lifecycle_failure(
                message=ORCHESTRATOR_MISSING_MESSAGE,
                role=role,
                model_name=model_name,
                model_state=state,
                notices=[self._download_message(model_name)],
            )
        return self._build_lifecycle_failure(
            message=FAILED_INSTALL_MESSAGE,
            role=role,
            model_name=model_name,
            model_state=state,
            errors=[{"message": FAILED_INSTALL_MESSAGE, "type": "model_install_failed"}],
        )

    def _plan_with_lifecycle(self, command: str) -> tuple[PlanningResult | None, list[str], TaskResult | None]:
        notices: list[str] = []
        planning_role = "planning"
        model_role = planning_role

        if self.model_manager is not None:
            state = self.model_manager.get_model_state(planning_role)
            model_name = self.model_manager.get_model_name_for_role(planning_role)
            if state == ModelState.FAILED:
                return None, notices, self._build_lifecycle_failure(
                    message=FAILED_INSTALL_MESSAGE,
                    role=planning_role,
                    model_name=model_name,
                    model_state=state,
                    errors=[{"message": FAILED_INSTALL_MESSAGE, "type": "model_install_failed"}],
                )
            if state in {ModelState.NOT_INSTALLED, ModelState.DOWNLOADING}:
                if state == ModelState.NOT_INSTALLED:
                    self._enqueue_download(planning_role)
                notices.extend([self._download_message(model_name), FALLBACK_MESSAGE])
                model_role = "orchestrator"

        planning_result = self._invoke_planner(command, model_role=model_role)
        if model_role == "orchestrator" and not self._is_simple_task(planning_result.steps):
            return None, notices, self._build_lifecycle_failure(
                message=BLOCK_MESSAGE,
                role=planning_role,
                model_name=self._model_name_for_role(planning_role),
                model_state=self._model_state_for_role(planning_role),
                notices=notices,
                errors=[{"message": BLOCK_MESSAGE, "type": "model_unavailable"}],
            )
        return planning_result, notices, None

    def _prepare_step_for_execution(
        self,
        step: PlanStep,
        task_is_simple: bool,
        state: ExecutionState,
    ) -> tuple[PlanStep, TaskResult | None]:
        execution_step = PlanStep(
            description=step.description,
            role=step.role,
            tool_name=step.tool_name,
            args=dict(step.args),
            needs_retrieval=step.needs_retrieval,
            requires_approval=step.requires_approval,
            approval_category=step.approval_category,
        )
        if self.model_manager is None or step.role not in {"analysis", "coding"}:
            return execution_step, None

        role = "analysis" if step.role == "analysis" else "coding"
        lifecycle = self._resolve_role_execution(role, task_is_simple=task_is_simple)
        if lifecycle["block"]:
            return execution_step, self._build_lifecycle_failure(
                message=str(lifecycle["message"]),
                role=role,
                model_name=str(lifecycle["model_name"]),
                model_state=lifecycle["state"],
                notices=list(lifecycle["notices"]),
                errors=[{"message": str(lifecycle["message"]), "type": "model_unavailable"}],
                routing=state.routing,
                step_results=list(state.step_results),
                files_modified=list(state.files_modified),
                steps_completed=list(state.steps_completed),
                existing_errors=list(state.errors),
            )
        override = lifecycle["fallback_role"]
        if isinstance(override, str):
            execution_step.args["_model_role_override"] = override
        self._append_model_notices(state, list(lifecycle["notices"]))
        return execution_step, None

    def _resolve_role_execution(self, role: str, *, task_is_simple: bool) -> dict[str, Any]:
        state = self._model_state_for_role(role)
        model_name = self._model_name_for_role(role)
        notices: list[str] = []

        if state == ModelState.INSTALLED:
            return {
                "block": False,
                "message": "",
                "fallback_role": None,
                "state": state,
                "model_name": model_name,
                "notices": notices,
            }

        if state == ModelState.NOT_INSTALLED:
            self._enqueue_download(role)
            state = ModelState.DOWNLOADING

        if state == ModelState.FAILED:
            return {
                "block": True,
                "message": FAILED_INSTALL_MESSAGE,
                "fallback_role": None,
                "state": state,
                "model_name": model_name,
                "notices": notices,
            }

        notices.append(self._download_message(model_name))
        if role == "coding":
            return {
                "block": True,
                "message": BLOCK_MESSAGE,
                "fallback_role": None,
                "state": state,
                "model_name": model_name,
                "notices": notices,
            }

        if task_is_simple:
            notices.append(FALLBACK_MESSAGE)
            return {
                "block": False,
                "message": FALLBACK_MESSAGE,
                "fallback_role": "orchestrator",
                "state": state,
                "model_name": model_name,
                "notices": notices,
            }

        return {
            "block": True,
            "message": BLOCK_MESSAGE,
            "fallback_role": None,
            "state": state,
            "model_name": model_name,
            "notices": notices,
        }

    def _invoke_planner(self, command: str, *, model_role: str) -> PlanningResult:
        try:
            return self.planner.plan_task(command, model_role=model_role)
        except TypeError:
            return self.planner.plan_task(command)

    def _enqueue_download(self, role: str) -> None:
        if self.download_manager is None:
            return
        try:
            self.download_manager.ensure_role_queued(role)
        except RuntimeError:
            return

    def _append_model_notices(self, state: ExecutionState, notices: list[str]) -> None:
        existing = list(state.context.get("model_notices", []))
        for notice in notices:
            if notice not in existing:
                existing.append(notice)
        state.context["model_notices"] = existing

    def _model_state_for_role(self, role: str) -> ModelState:
        if self.model_manager is None:
            return ModelState.INSTALLED
        return self.model_manager.get_model_state(role)

    def _model_name_for_role(self, role: str) -> str:
        if self.model_manager is None:
            return role
        return self.model_manager.get_model_name_for_role(role)

    @staticmethod
    def _download_message(model_name: str) -> str:
        return DOWNLOAD_MESSAGE_TEMPLATE.format(name=model_name)

    @staticmethod
    def _is_simple_task(steps: list[PlanStep]) -> bool:
        if len(steps) > 3:
            return False
        for step in steps:
            if step.role == "coding":
                return False
            if step.needs_retrieval:
                return False
            if step.requires_approval:
                return False
        return True

    @staticmethod
    def _build_lifecycle_failure(
        *,
        message: str,
        role: str | None = None,
        model_name: str | None = None,
        model_state: ModelState | None = None,
        notices: list[str] | None = None,
        errors: list[dict[str, Any]] | None = None,
        routing: dict[str, Any] | None = None,
        step_results: list[dict[str, Any]] | None = None,
        files_modified: list[str] | None = None,
        steps_completed: list[dict[str, Any]] | None = None,
        existing_errors: list[dict[str, Any]] | None = None,
    ) -> TaskResult:
        public_role = "intent" if role == "orchestrator" else role
        payload_errors = list(existing_errors or [])
        if errors is not None:
            payload_errors.extend(errors)
        elif message:
            payload_errors.append({"message": message, "type": "model_unavailable"})
        data: dict[str, Any] = {
            "status": "failed",
            "routing": routing or {},
            "step_results": list(step_results or []),
            "files_modified": list(files_modified or []),
            "steps_completed": list(steps_completed or []),
            "errors": payload_errors,
            "model_notices": list(notices or []),
            "blocked": True,
            "error_type": "model_unavailable",
        }
        if public_role is not None:
            data["role"] = public_role
        if model_name is not None:
            data["model_name"] = model_name
        if model_state is not None:
            data["model_state"] = model_state.value
        return TaskResult(success=False, message=message, data=data)

    @staticmethod
    def _merge_state_into_result(state: ExecutionState, result: TaskResult) -> TaskResult:
        payload = dict(result.data)
        model_notices = list(state.context.get("model_notices", []))
        for notice in payload.get("model_notices", []):
            if notice not in model_notices:
                model_notices.append(notice)
        payload["routing"] = dict(state.routing)
        payload["step_results"] = list(state.step_results)
        payload["files_modified"] = list(state.files_modified)
        payload["steps_completed"] = list(state.steps_completed)
        payload["errors"] = list(payload.get("errors", state.errors))
        payload["model_notices"] = model_notices
        return TaskResult(
            success=result.success,
            message=result.message,
            steps=state.steps,
            data=payload,
        )

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
                "files_modified": [],
                "steps_completed": [],
                "errors": [],
                "model_notices": [],
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
                "files_modified": list(state.files_modified),
                "steps_completed": list(state.steps_completed),
                "errors": list(state.errors),
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
            files_modified=list(state.files_modified),
            steps_completed=list(state.steps_completed),
            errors=list(state.errors),
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
