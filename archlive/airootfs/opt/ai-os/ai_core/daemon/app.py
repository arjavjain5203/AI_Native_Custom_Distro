"""FastAPI application for the local AI daemon."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ai_core.agents import AnalysisAgent, CodingAgent, ExecutorAgent, PlannerAgent
from ai_core.core.approvals import ApprovalStore
from ai_core.core.execution_engine import ExecutionEngine
from ai_core.core.rollback import RollbackManager
from ai_core.core.session import SessionManager
from ai_core.core.types import ExecutionOutcome, PlanStep
from ai_core.mcp import MCPClient
from ai_core.memory import TaskHistoryStore, VectorStore, WorkingMemoryStore
from ai_core.models import ModelManager, Orchestrator
from ai_core.models.download_manager import ModelDownloadManager
from ai_core.models.router import ModelRouter
from ai_core.tools import ToolRegistry, build_tool_registry


class TaskRequest(BaseModel):
    """Incoming task payload from the CLI."""

    command: str = Field(..., min_length=1)
    cwd: str | None = None


class PlanStepResponse(BaseModel):
    """Serialized plan step for daemon responses."""

    description: str
    role: str
    tool_name: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    needs_retrieval: bool = False
    requires_approval: bool = False
    approval_category: str | None = None


class TaskResponse(BaseModel):
    """Task response returned to clients."""

    task_id: str
    status: Literal["completed", "failed", "pending_approval", "cancelled"]
    success: bool
    message: str
    command: str
    cwd: str
    steps: list[PlanStepResponse] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    approval_request: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    """Basic daemon health payload."""

    status: str
    service: str
    version: str


class StoredTaskResponse(BaseModel):
    """Serialized task history entry."""

    id: str
    command: str
    cwd: str
    success: bool
    message: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class RuntimeStatusResponse(BaseModel):
    """Current runtime selection state."""

    configured_runtime: str
    detected_ram_gb: float
    cpu_cores: int
    low_memory_threshold_gb: float
    selected_runtime_by_role: dict[str, str | None] = Field(default_factory=dict)
    issues: dict[str, str] = Field(default_factory=dict)


class RuntimeUpdateRequest(BaseModel):
    """Runtime update payload."""

    runtime: str = Field(..., min_length=1)


class ApprovalDecisionRequest(BaseModel):
    """Approval decision payload."""

    token: str = Field(..., min_length=1)
    decision: Literal["approve", "deny"]


class ModelRoleUpdateRequest(BaseModel):
    """Model role assignment update payload."""

    role: str = Field(..., min_length=1)
    runtime: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)


class ModelDownloadRequest(BaseModel):
    """Background model download request payload."""

    role: str | None = None


class RollbackRequest(BaseModel):
    """Rollback execution payload."""

    task_id: str = Field(..., min_length=1)
    step_index: int = Field(..., ge=0)


def create_app(
    planner: PlannerAgent | None = None,
    executor: ExecutorAgent | None = None,
    history_store: TaskHistoryStore | None = None,
    model_manager: ModelManager | None = None,
    router: ModelRouter | None = None,
    coding_agent: CodingAgent | None = None,
    analysis_agent: AnalysisAgent | None = None,
    approval_store: ApprovalStore | None = None,
    vector_store: VectorStore | None = None,
    session_manager: SessionManager | None = None,
    working_memory_store: WorkingMemoryStore | None = None,
    rollback_manager: RollbackManager | None = None,
    mcp_client: MCPClient | None = None,
    tool_registry: ToolRegistry | None = None,
    execution_engine: ExecutionEngine | None = None,
    download_manager: ModelDownloadManager | None = None,
) -> FastAPI:
    """Create the daemon application."""
    model_manager = model_manager or getattr(planner, "model_manager", None) or ModelManager()
    vector_store = vector_store or VectorStore()
    session_manager = session_manager or SessionManager()
    tool_registry = tool_registry or build_tool_registry(mcp_client=mcp_client)
    download_manager = download_manager or ModelDownloadManager(model_manager=model_manager)
    router = router or ModelRouter(
        model_manager=model_manager,
        orchestrator=Orchestrator(model_manager=model_manager, session_manager=session_manager),
    )
    planner = planner or PlannerAgent(model_manager=model_manager)
    executor = executor or ExecutorAgent()
    history_store = history_store or TaskHistoryStore()
    history_store.initialize()
    coding_agent = coding_agent or CodingAgent(
        model_manager=model_manager,
        vector_store=vector_store,
        tool_registry=tool_registry,
    )
    analysis_agent = analysis_agent or AnalysisAgent(model_manager=model_manager)
    approval_store = approval_store or ApprovalStore()
    working_memory_store = working_memory_store or WorkingMemoryStore()
    rollback_manager = rollback_manager or RollbackManager(history_store)
    execution_engine = execution_engine or ExecutionEngine(
        router=router,
        planner=planner,
        executor=executor,
        coding_agent=coding_agent,
        analysis_agent=analysis_agent,
        approval_store=approval_store,
        history_store=history_store,
        working_memory_store=working_memory_store,
        rollback_manager=rollback_manager,
        session_manager=session_manager,
        vector_store=vector_store,
        tool_registry=tool_registry,
        model_manager=model_manager,
        download_manager=download_manager,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        download_manager.start()
        try:
            model_manager.ensure_orchestrator_pinned()
        except RuntimeError:
            pass
        try:
            yield
        finally:
            download_manager.stop()

    app = FastAPI(
        title="AI-Native Developer Operating Environment",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.download_manager = download_manager

    def serialize_steps(steps: list[PlanStep]) -> list[PlanStepResponse]:
        return [
            PlanStepResponse(
                description=step.description,
                role=step.role,
                tool_name=step.tool_name,
                args=step.args,
                needs_retrieval=step.needs_retrieval,
                requires_approval=step.requires_approval,
                approval_category=step.approval_category,
            )
            for step in steps
        ]

    def to_task_response(outcome: ExecutionOutcome) -> TaskResponse:
        status = str(outcome.result.data.get("status", "completed" if outcome.result.success else "failed"))
        approval_request = outcome.result.data.get("approval_request")
        return TaskResponse(
            task_id=outcome.task_id,
            status=status,  # type: ignore[arg-type]
            success=outcome.result.success,
            message=outcome.result.message,
            command=outcome.command,
            cwd=outcome.cwd,
            steps=serialize_steps(outcome.result.steps),
            result=outcome.result.data,
            approval_request=approval_request if isinstance(approval_request, dict) else None,
        )

    @app.get("/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service="ai-daemon",
            version=app.version,
        )

    @app.post("/task", response_model=TaskResponse)
    async def create_task(payload: TaskRequest) -> TaskResponse:
        cwd_path = Path(payload.cwd or Path.cwd()).resolve()
        if not cwd_path.exists():
            raise HTTPException(status_code=400, detail=f"cwd does not exist: {cwd_path}")
        try:
            return to_task_response(execution_engine.run_task(payload.command, {"cwd": str(cwd_path)}))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/tasks/{task_id}", response_model=StoredTaskResponse)
    async def get_task(task_id: str) -> StoredTaskResponse:
        task = history_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
        return StoredTaskResponse(**task)

    @app.get("/tasks", response_model=list[StoredTaskResponse])
    async def list_tasks(limit: int = Query(default=20, ge=1, le=100)) -> list[StoredTaskResponse]:
        return [StoredTaskResponse(**task) for task in history_store.list_tasks(limit=limit)]

    @app.get("/runtime", response_model=RuntimeStatusResponse)
    async def get_runtime() -> RuntimeStatusResponse:
        return RuntimeStatusResponse(**model_manager.get_runtime_status())

    @app.post("/runtime", response_model=RuntimeStatusResponse)
    async def update_runtime(payload: RuntimeUpdateRequest) -> RuntimeStatusResponse:
        try:
            return RuntimeStatusResponse(**model_manager.set_runtime(payload.runtime))
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/models", response_model=dict[str, Any])
    async def get_models() -> dict[str, Any]:
        return model_manager.list_configured_models()

    @app.post("/models/downloads", response_model=dict[str, Any])
    async def trigger_model_downloads(payload: ModelDownloadRequest) -> dict[str, Any]:
        role = (payload.role or "all").strip()
        if role.lower() == "all":
            return download_manager.retry_all()
        try:
            response = download_manager.retry_role(role)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response["models"] = model_manager.list_configured_models()
        return response

    @app.get("/rollback", response_model=list[dict[str, Any]])
    async def list_rollback_candidates(limit: int = Query(default=20, ge=1, le=100)) -> list[dict[str, Any]]:
        return rollback_manager.list_candidates(limit=limit)

    @app.post("/rollback", response_model=dict[str, Any])
    async def rollback_task(payload: RollbackRequest) -> dict[str, Any]:
        try:
            result = rollback_manager.rollback(payload.task_id, payload.step_index)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "success": result.success,
            "task_id": result.task_id,
            "step_index": result.step_index,
            "reverted_snapshots": result.reverted_snapshots,
            "message": result.message,
        }

    @app.post("/models/roles", response_model=dict[str, Any])
    async def set_model_role(payload: ModelRoleUpdateRequest) -> dict[str, Any]:
        try:
            return model_manager.set_role_model(payload.role, payload.runtime, payload.model_name)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/approvals/{approval_id}", response_model=dict[str, Any])
    async def get_approval(approval_id: str) -> dict[str, Any]:
        pending = approval_store.get(approval_id)
        if pending is None:
            raise HTTPException(status_code=404, detail=f"approval not found: {approval_id}")
        return asdict(pending.approval)

    @app.post("/approvals/{approval_id}", response_model=TaskResponse)
    async def resolve_approval(approval_id: str, payload: ApprovalDecisionRequest) -> TaskResponse:
        try:
            return to_task_response(
                execution_engine.resolve_approval(
                    approval_id,
                    payload.token,
                    payload.decision,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()
