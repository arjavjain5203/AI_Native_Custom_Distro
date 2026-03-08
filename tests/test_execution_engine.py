from pathlib import Path

from ai_core.agents.coding import CodingStepResult
from ai_core.agents.executor import ExecutorAgent
from ai_core.core.approvals import ApprovalStore
from ai_core.core.execution_engine import ExecutionEngine
from ai_core.core.rollback import RollbackManager
from ai_core.core.session import SessionManager
from ai_core.core.types import AnalysisStepResult, ModelSelection, PlanStep, PlanningResult
from ai_core.memory.store import TaskHistoryStore
from ai_core.memory.vector_store import VectorStore
from ai_core.memory.working_memory import WorkingMemoryStore
from ai_core.models.manager import ModelState


class StubRouter:
    def __init__(self, *, mode: str = "execution") -> None:
        self.mode = mode

    def classify(self, task: str, context: dict[str, object], *, session_id: str | None = None) -> dict[str, object]:
        return {
            "mode": self.mode,
            "task_type": "planning" if self.mode == "conversation" else "system",
            "agent": "planning",
            "confidence": 0.9,
        }

    def selection_for_decision(self, decision: dict[str, object]) -> ModelSelection:
        return ModelSelection(
            task_type=str(decision["task_type"]),  # type: ignore[arg-type]
            role=str(decision["agent"]),  # type: ignore[arg-type]
            provider="ollama",
            model_name="gemma:2b",
        )

    def route(self, task: str, context: dict[str, object]) -> ModelSelection:
        return self.selection_for_decision(self.classify(task, context))


class StubPlanningAgent:
    def __init__(self, steps: list[PlanStep]) -> None:
        self.steps = steps

    def plan_task(self, command: str) -> PlanningResult:
        return PlanningResult(
            steps=self.steps,
            source="fallback",
            validation={"step_count": len(self.steps)},
        )


class StubCodingAgent:
    def execute_step(self, instruction: str, cwd: str, step_args: dict[str, object]) -> object:
        raise AssertionError("coding agent should not be used in this test")


class FailingCodingAgent:
    def execute_step(self, instruction: str, cwd: str, step_args: dict[str, object]) -> CodingStepResult:
        return CodingStepResult(
            success=False,
            error="Validation failed after retries",
            changed_files=[],
            diffs={},
            retrieved_files=[],
            validation={
                "syntax_ok": False,
                "imports_ok": True,
                "retries_used": 2,
                "warnings": [],
            },
            tests={"executed": False, "passed": False, "failures": []},
        )


class StubAnalysisAgent:
    def execute_step(self, instruction: str, step_args: dict[str, object]) -> AnalysisStepResult:
        return AnalysisStepResult(
            success=True,
            analysis="diagnosed",
            context=dict(step_args),
            validation={"analysis_length": 9},
        )


class LifecycleModelManager:
    def __init__(self, states: dict[str, ModelState], names: dict[str, str] | None = None) -> None:
        self.states = dict(states)
        self.names = names or {
            "orchestrator": "phi3:mini",
            "planning": "mistral:7b",
            "coding": "qwen2.5-coder:1.5b",
            "analysis": "gemma:2b",
        }

    def get_model_state(self, role: str) -> ModelState:
        normalized = "orchestrator" if role in {"intent", "orchestrator"} else role
        return self.states[normalized]

    def get_model_name_for_role(self, role: str) -> str:
        normalized = "orchestrator" if role in {"intent", "orchestrator"} else role
        return self.names[normalized]


class RecordingDownloadManager:
    def __init__(self) -> None:
        self.queued_roles: list[str] = []

    def ensure_role_queued(self, role: str) -> bool:
        self.queued_roles.append(role)
        return True


def build_engine(
    tmp_path: Path,
    *,
    steps: list[PlanStep],
    mode: str = "execution",
    coding_agent: object | None = None,
) -> tuple[ExecutionEngine, TaskHistoryStore, WorkingMemoryStore]:
    history_store = TaskHistoryStore(tmp_path / "history.db")
    history_store.initialize()
    vector_store = VectorStore(db_path=tmp_path / "vectors.db")
    working_memory_store = WorkingMemoryStore()
    engine = ExecutionEngine(
        router=StubRouter(mode=mode),  # type: ignore[arg-type]
        planner=StubPlanningAgent(steps),  # type: ignore[arg-type]
        executor=ExecutorAgent(),
        coding_agent=(coding_agent or StubCodingAgent()),  # type: ignore[arg-type]
        analysis_agent=StubAnalysisAgent(),  # type: ignore[arg-type]
        approval_store=ApprovalStore(),
        history_store=history_store,
        working_memory_store=working_memory_store,
        rollback_manager=RollbackManager(history_store),
        session_manager=SessionManager(),
        vector_store=vector_store,
    )
    return engine, history_store, working_memory_store


def test_execution_engine_returns_conversation_payload_without_execution(tmp_path: Path) -> None:
    engine, history_store, working_memory_store = build_engine(tmp_path, steps=[], mode="conversation")

    outcome = engine.run_task("Let's discuss my project idea", {"cwd": str(tmp_path)})

    assert outcome.result.success is True
    assert outcome.result.steps == []
    assert outcome.result.data["conversation"]["mode"] == "conversation"
    assert working_memory_store.get(outcome.task_id) is None
    assert history_store.get_task(outcome.task_id) is not None


def test_execution_engine_runs_executor_pipeline_and_records_history(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(description="Create folder demo", role="executor", tool_name="create_folder", args={"path": "demo"})
    engine, history_store, working_memory_store = build_engine(tmp_path, steps=[step])

    outcome = engine.run_task("create a folder demo", {"cwd": str(workspace)})

    assert outcome.result.success is True
    assert outcome.result.data["files_modified"] == ["demo"]
    assert outcome.result.data["steps_completed"] == [
        {
            "step_index": 0,
            "step": "Create folder demo",
            "role": "executor",
            "tool_name": "create_folder",
        }
    ]
    assert outcome.result.data["errors"] == []
    assert (workspace / "demo").is_dir()
    assert working_memory_store.get(outcome.task_id) is None
    stored_task = history_store.get_task(outcome.task_id)
    assert stored_task is not None
    assert stored_task["command"] == "create a folder demo"


def test_execution_engine_resolves_denied_approval_without_replanning(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(
        description="Install package nano",
        role="executor",
        tool_name="pacman_install",
        args={"package": "nano"},
        requires_approval=True,
        approval_category="package_install",
    )
    engine, _, working_memory_store = build_engine(tmp_path, steps=[step])

    pending = engine.run_task("install package nano", {"cwd": str(workspace)})

    assert pending.result.data["status"] == "pending_approval"
    approval_request = pending.result.data["approval_request"]
    assert approval_request is not None

    resolved = engine.resolve_approval(
        approval_request["approval_id"],
        approval_request["token"],
        "deny",
    )

    assert resolved.result.data["status"] == "cancelled"
    assert resolved.result.success is False
    assert working_memory_store.get(pending.task_id) is None


def test_execution_engine_uses_registry_metadata_for_approval(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(
        description="Install package nano",
        role="executor",
        tool_name="pacman_install",
        args={"package": "nano"},
    )
    engine, _, working_memory_store = build_engine(tmp_path, steps=[step])

    pending = engine.run_task("install package nano", {"cwd": str(workspace)})

    assert pending.result.data["status"] == "pending_approval"
    approval_request = pending.result.data["approval_request"]
    assert approval_request is not None
    assert approval_request["category"] == "system"
    assert pending.result.steps[0].requires_approval is True
    assert pending.result.steps[0].approval_category == "system"
    assert working_memory_store.get(pending.task_id) is not None


def test_execution_engine_treats_structured_coding_failure_as_failed_step(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("def hello():\n    return 'old'\n", encoding="utf-8")
    step = PlanStep(
        description="Update application code",
        role="coding",
        tool_name="coding_pipeline",
        args={"instruction": "update hello"},
    )
    engine, history_store, _ = build_engine(
        tmp_path,
        steps=[step],
        coding_agent=FailingCodingAgent(),
    )

    outcome = engine.run_task("update hello", {"cwd": str(workspace)})

    assert outcome.result.success is False
    assert outcome.result.message == "Step failed after retries: Update application code"
    assert outcome.result.data["step_results"][0]["result"]["error"] == "Validation failed after retries"
    assert outcome.result.data["files_modified"] == []
    assert outcome.result.data["steps_completed"] == []
    assert outcome.result.data["errors"][0]["message"] == "Validation failed after retries"
    stored_task = history_store.get_task(outcome.task_id)
    assert stored_task is not None
    assert stored_task["success"] is False


def test_execution_engine_links_continuation_to_previous_task(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(description="Create folder demo", role="executor", tool_name="create_folder", args={"path": "demo"})
    engine, history_store, _ = build_engine(tmp_path, steps=[step])

    first = engine.run_task("create a folder demo", {"cwd": str(workspace)})
    second = engine.run_task("continue and add to this setup", {"cwd": str(workspace)})

    first_task = history_store.get_task(first.task_id)
    second_task = history_store.get_task(second.task_id)
    assert first_task is not None
    assert second_task is not None
    assert first_task["parent_task_id"] is None
    assert second_task["parent_task_id"] == first.task_id
    assert second_task["success"] is False
    assert second_task["task_summary"] == "Failed: continue and add to this setup"


def test_execution_engine_indexes_completed_task_for_recall(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(description="Create folder demo", role="executor", tool_name="create_folder", args={"path": "demo"})
    history_store = TaskHistoryStore(tmp_path / "history.db")
    history_store.initialize()
    vector_store = VectorStore(db_path=tmp_path / "vectors.db")
    engine = ExecutionEngine(
        router=StubRouter(mode="execution"),  # type: ignore[arg-type]
        planner=StubPlanningAgent([step]),  # type: ignore[arg-type]
        executor=ExecutorAgent(),
        coding_agent=StubCodingAgent(),  # type: ignore[arg-type]
        analysis_agent=StubAnalysisAgent(),  # type: ignore[arg-type]
        approval_store=ApprovalStore(),
        history_store=history_store,
        working_memory_store=WorkingMemoryStore(),
        rollback_manager=RollbackManager(history_store),
        session_manager=SessionManager(),
        vector_store=vector_store,
    )

    first = engine.run_task("create a folder demo", {"cwd": str(workspace)})
    related = vector_store.get_related_tasks("create similar demo project", str(workspace), limit=3)

    assert first.result.success is True
    assert related
    assert related[0]["task_id"] == first.task_id


def test_execution_engine_blocks_when_orchestrator_is_not_installed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    router = StubRouter(mode="execution")
    download_manager = RecordingDownloadManager()
    history_store = TaskHistoryStore(tmp_path / "history.db")
    history_store.initialize()
    engine = ExecutionEngine(
        router=router,  # type: ignore[arg-type]
        planner=StubPlanningAgent([]),  # type: ignore[arg-type]
        executor=ExecutorAgent(),
        coding_agent=StubCodingAgent(),  # type: ignore[arg-type]
        analysis_agent=StubAnalysisAgent(),  # type: ignore[arg-type]
        approval_store=ApprovalStore(),
        history_store=history_store,
        working_memory_store=WorkingMemoryStore(),
        rollback_manager=RollbackManager(history_store),
        session_manager=SessionManager(),
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
        model_manager=LifecycleModelManager({"orchestrator": ModelState.NOT_INSTALLED}),
        download_manager=download_manager,  # type: ignore[arg-type]
    )

    outcome = engine.run_task("create a folder demo", {"cwd": str(workspace)})

    assert outcome.result.success is False
    assert outcome.result.message == (
        "Orchestrator model is not installed yet. Please wait while it is downloading. "
        "You can continue using normal terminal commands."
    )
    assert download_manager.queued_roles == ["orchestrator"]


def test_execution_engine_uses_orchestrator_fallback_for_simple_planning_tasks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(description="Create folder demo", role="executor", tool_name="create_folder", args={"path": "demo"})
    history_store = TaskHistoryStore(tmp_path / "history.db")
    history_store.initialize()
    engine = ExecutionEngine(
        router=StubRouter(mode="execution"),  # type: ignore[arg-type]
        planner=StubPlanningAgent([step]),  # type: ignore[arg-type]
        executor=ExecutorAgent(),
        coding_agent=StubCodingAgent(),  # type: ignore[arg-type]
        analysis_agent=StubAnalysisAgent(),  # type: ignore[arg-type]
        approval_store=ApprovalStore(),
        history_store=history_store,
        working_memory_store=WorkingMemoryStore(),
        rollback_manager=RollbackManager(history_store),
        session_manager=SessionManager(),
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
        model_manager=LifecycleModelManager(
            {
                "orchestrator": ModelState.INSTALLED,
                "planning": ModelState.DOWNLOADING,
                "coding": ModelState.INSTALLED,
                "analysis": ModelState.INSTALLED,
            }
        ),
        download_manager=RecordingDownloadManager(),  # type: ignore[arg-type]
    )

    outcome = engine.run_task("create a folder demo", {"cwd": str(workspace)})

    assert outcome.result.success is True
    assert outcome.result.message == "Using a smaller model because the preferred model is still downloading."
    assert "Model mistral:7b is downloading. You can run basic tasks." in outcome.result.data["model_notices"]


def test_execution_engine_blocks_coding_when_model_is_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    step = PlanStep(
        description="Apply coding workflow for auth",
        role="coding",
        tool_name="coding_pipeline",
        args={"instruction": "add auth"},
        needs_retrieval=True,
    )
    download_manager = RecordingDownloadManager()
    history_store = TaskHistoryStore(tmp_path / "history.db")
    history_store.initialize()
    engine = ExecutionEngine(
        router=StubRouter(mode="execution"),  # type: ignore[arg-type]
        planner=StubPlanningAgent([step]),  # type: ignore[arg-type]
        executor=ExecutorAgent(),
        coding_agent=StubCodingAgent(),  # type: ignore[arg-type]
        analysis_agent=StubAnalysisAgent(),  # type: ignore[arg-type]
        approval_store=ApprovalStore(),
        history_store=history_store,
        working_memory_store=WorkingMemoryStore(),
        rollback_manager=RollbackManager(history_store),
        session_manager=SessionManager(),
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
        model_manager=LifecycleModelManager(
            {
                "orchestrator": ModelState.INSTALLED,
                "planning": ModelState.INSTALLED,
                "coding": ModelState.NOT_INSTALLED,
                "analysis": ModelState.INSTALLED,
            }
        ),
        download_manager=download_manager,  # type: ignore[arg-type]
    )

    outcome = engine.run_task("add auth", {"cwd": str(workspace)})

    assert outcome.result.success is False
    assert outcome.result.message == "This task requires a more capable model. Please wait for the model to finish downloading."
    assert "Model qwen2.5-coder:1.5b is downloading. You can run basic tasks." in outcome.result.data["model_notices"]
    assert download_manager.queued_roles == ["coding"]
