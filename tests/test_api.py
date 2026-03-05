import asyncio
import json
from pathlib import Path

import httpx

from ai_core.agents.planner import PlannerAgent
from ai_core.agents.analysis import AnalysisAgent
from ai_core.agents.executor import ExecutorAgent
from ai_core.core.session import SessionManager
from ai_core.core.types import ExecutionOutcome, ExecutionStepResult, ModelSelection, PlanStep, PlanningResult, TaskResult
from ai_core.daemon.app import create_app
from ai_core.memory.store import TaskHistoryStore
from ai_core.memory.working_memory import WorkingMemoryStore
from ai_core.models.manager import ModelManager
from ai_core.models.ollama import OllamaError
from ai_core.memory.vector_store import VectorStore
from ai_core.tools import ToolDefinition, ToolExecutionContext, ToolRegistry, build_tool_registry


class FailingOllamaClient:
    def generate(self, prompt: str, model: str | None = None) -> str:
        raise OllamaError("ollama unavailable")

    def list_installed_models(self) -> set[str]:
        return set()


class InstalledModelsOllamaClient:
    def __init__(self, installed_models: set[str] | None = None) -> None:
        self.installed_models = installed_models or {"phi3:mini", "gemma:2b", "mistral:7b", "qwen2.5-coder:1.5b"}

    def generate(self, prompt: str, model: str | None = None, timeout_seconds: float | None = None) -> str:
        return "[]"

    def list_installed_models(self) -> set[str]:
        return set(self.installed_models)


class RecordingRouter:
    def __init__(self, session_manager: SessionManager | None = None) -> None:
        self.contexts: list[dict[str, object]] = []
        self.session_manager = session_manager

    def classify(
        self,
        task: str,
        context: dict[str, object],
        *,
        session_id: str | None = None,
    ) -> dict[str, object]:
        self.contexts.append(dict(context))
        decision = {
            "mode": "execution",
            "task_type": "system",
            "agent": "planning",
            "confidence": 0.9,
        }
        if session_id is not None and self.session_manager is not None:
            self.session_manager.update(
                session_id,
                task,
                mode=str(decision["mode"]),
                task_type=str(decision["task_type"]),
                agent=str(decision["agent"]),
            )
        return decision

    def selection_for_decision(self, decision: dict[str, object]) -> ModelSelection:
        return ModelSelection(
            task_type=str(decision["task_type"]),  # type: ignore[arg-type]
            role=str(decision["agent"]),  # type: ignore[arg-type]
            provider="ollama",
            model_name="gemma:2b",
        )

    def route(self, task: str, context: dict[str, object]) -> ModelSelection:
        return self.selection_for_decision(self.classify(task, context))


class ConversationRouter(RecordingRouter):
    def classify(
        self,
        task: str,
        context: dict[str, object],
        *,
        session_id: str | None = None,
    ) -> dict[str, object]:
        self.contexts.append(dict(context))
        return {
            "mode": "conversation",
            "task_type": "planning",
            "agent": "planning",
            "confidence": 0.93,
        }


class StubPlanningAgent:
    def __init__(self, steps: list[PlanStep]) -> None:
        self.steps = steps

    def plan_task(self, command: str) -> PlanningResult:
        return PlanningResult(
            steps=self.steps,
            source="fallback",
            validation={"step_count": len(self.steps)},
        )

    def plan(self, command: str) -> list[PlanStep]:
        return self.steps


class FlakyExecutor(ExecutorAgent):
    def __init__(self, fail_until_attempt: int = 2) -> None:
        super().__init__()
        self.fail_until_attempt = fail_until_attempt
        self.calls = 0

    def execute_step(self, step: PlanStep, cwd: str | None = None) -> ExecutionStepResult:
        self.calls += 1
        if self.calls <= self.fail_until_attempt:
            raise ValueError("transient failure")
        return ExecutionStepResult(
            success=True,
            tool_name=step.tool_name or "",
            output={"attempt": self.calls},
            validation={"args_validated": True},
        )


class AlwaysFailExecutor(ExecutorAgent):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def execute_step(self, step: PlanStep, cwd: str | None = None) -> ExecutionStepResult:
        self.calls += 1
        raise ValueError("persistent failure")


class StubAnalysisAgent(AnalysisAgent):
    def __init__(self) -> None:
        self.calls = 0

    def execute_step(self, instruction: str, step_args: dict[str, object]):  # type: ignore[override]
        self.calls += 1
        from ai_core.core.types import AnalysisStepResult

        return AnalysisStepResult(
            success=True,
            analysis="Failure diagnosed.",
            context=dict(step_args),
            validation={"analysis_length": 18},
        )


def build_flaky_registry(*, fail_until_attempt: int | None = None, always_fail: bool = False) -> tuple[ToolRegistry, dict[str, int]]:
    registry = build_tool_registry()
    calls = {"count": 0}

    def flaky_create_folder(args: dict[str, object], context: ToolExecutionContext) -> dict[str, object]:
        calls["count"] += 1
        if always_fail or (fail_until_attempt is not None and calls["count"] <= fail_until_attempt):
            raise ValueError("persistent failure" if always_fail else "transient failure")
        return {"attempt": calls["count"], "path": args["path"]}

    registry.register(
        ToolDefinition(
            name="test.create_folder_flaky",
            handler=flaky_create_folder,
            args_schema={"path": {"type": "string", "required": True}},
            requires_approval=False,
            rollback_supported=False,
            category="filesystem",
            source="local",
        )
    )
    return registry, calls


class StubExecutionEngine:
    def __init__(self) -> None:
        self.run_calls: list[tuple[str, dict[str, object]]] = []
        self.approval_calls: list[tuple[str, str, str]] = []

    def run_task(self, user_input: str, context: dict[str, object]) -> ExecutionOutcome:
        self.run_calls.append((user_input, dict(context)))
        return ExecutionOutcome(
            task_id="task-stubbed",
            command=user_input,
            cwd=str(context["cwd"]),
            result=TaskResult(
                success=True,
                message="stubbed",
                steps=[],
                data={"status": "completed"},
            ),
        )

    def resolve_approval(self, approval_id: str, token: str, decision: str) -> ExecutionOutcome:
        self.approval_calls.append((approval_id, token, decision))
        return ExecutionOutcome(
            task_id="task-stubbed",
            command="noop",
            cwd="/tmp",
            result=TaskResult(
                success=False,
                message="stubbed approval",
                steps=[],
                data={"status": "cancelled"},
            ),
        )


class StubDownloadManager:
    def __init__(self) -> None:
        self.retry_role_calls: list[str] = []
        self.retry_all_calls = 0

    def start(self) -> None:
        return None

    def retry_role(self, role: str) -> dict[str, object]:
        self.retry_role_calls.append(role)
        return {
            "queued": True,
            "role": role,
            "model_name": "mistral:7b",
            "message": "Model mistral:7b is downloading. You can run basic tasks.",
        }

    def retry_all(self) -> dict[str, object]:
        self.retry_all_calls += 1
        return {"queued_roles": ["intent", "planning"], "message": "Model downloads resumed."}


def build_model_manager(tmp_path: Path, installed_models: set[str] | None = None) -> ModelManager:
    return ModelManager(
        ollama_client=InstalledModelsOllamaClient(installed_models=installed_models),
        system_config_path=tmp_path / "system-models.json",
        user_config_path=tmp_path / "user-models.json",
        ram_gb_provider=lambda: 8.0,
    )


def test_api_health_and_task_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    planner = PlannerAgent(ollama_client=FailingOllamaClient())
    history_store = TaskHistoryStore(db_path)
    working_memory_store = WorkingMemoryStore()
    model_manager = build_model_manager(tmp_path)
    app = create_app(
        planner=planner,
        history_store=history_store,
        model_manager=model_manager,
        working_memory_store=working_memory_store,
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            runtime = await client.get("/runtime")
            assert runtime.status_code == 200
            assert runtime.json()["configured_runtime"] == "auto"

            updated_runtime = await client.post("/runtime", json={"runtime": "ollama"})
            assert updated_runtime.status_code == 200
            assert updated_runtime.json()["configured_runtime"] == "ollama"
            user_config = json.loads((tmp_path / "user-models.json").read_text(encoding="utf-8"))
            assert user_config["runtime"] == "ollama"

            models = await client.get("/models")
            assert models.status_code == 200
            assert "intent" in models.json()
            assert "planning" in models.json()

            updated_model = await client.post(
                "/models/roles",
                json={"role": "planning", "runtime": "ollama", "model_name": "mistral:7b"},
            )
            assert updated_model.status_code == 200
            assert updated_model.json()["planning"]["configured"]["ollama"] == "mistral:7b"

            workdir = tmp_path / "workspace"
            workdir.mkdir()

            response = await client.post(
                "/task",
                json={"command": "create a folder test", "cwd": str(workdir)},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert (workdir / "test").is_dir()

            task_id = payload["task_id"]
            assert working_memory_store.get(task_id) is None
            logs = history_store.list_execution_logs(task_id)
            assert logs[-1]["status"] == "completed"
            scratchpad = history_store.list_scratchpad_entries(task_id)
            assert scratchpad[-1]["category"] == "tool_output"

            stored = await client.get(f"/tasks/{task_id}")
            assert stored.status_code == 200
            assert stored.json()["command"] == "create a folder test"

            rollback_candidates = await client.get("/rollback")
            assert rollback_candidates.status_code == 200
            assert rollback_candidates.json()

            rollback_response = await client.post(
                "/rollback",
                json={"task_id": task_id, "step_index": 0},
            )
            assert rollback_response.status_code == 200
            assert rollback_response.json()["success"] is True
            assert not (workdir / "test").exists()

            history = await client.get("/tasks", params={"limit": 10})
            assert history.status_code == 200
            assert len(history.json()) == 1

            approval_response = await client.post(
                "/task",
                json={"command": "install package nano", "cwd": str(workdir)},
            )
            assert approval_response.status_code == 200
            approval_payload = approval_response.json()
            assert approval_payload["status"] == "pending_approval"
            approval = approval_payload["approval_request"]
            pending_task_id = approval_payload["task_id"]
            working_memory = working_memory_store.get(pending_task_id)
            assert working_memory is not None
            assert working_memory["status"] == "pending_approval"
            pending_logs = history_store.list_execution_logs(pending_task_id)
            assert pending_logs[-1]["status"] == "pending_approval"

            denied = await client.post(
                f"/approvals/{approval['approval_id']}",
                json={"token": approval["token"], "decision": "deny"},
            )
            assert denied.status_code == 200
            assert denied.json()["status"] == "cancelled"
            assert working_memory_store.get(pending_task_id) is None

    asyncio.run(run_scenario())


def test_api_exposes_model_download_retry_endpoint(tmp_path: Path) -> None:
    download_manager = StubDownloadManager()
    app = create_app(
        planner=PlannerAgent(ollama_client=FailingOllamaClient()),
        history_store=TaskHistoryStore(tmp_path / "history.db"),
        model_manager=build_model_manager(tmp_path),
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
        download_manager=download_manager,  # type: ignore[arg-type]
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            role_retry = await client.post("/models/downloads", json={"role": "planning"})
            assert role_retry.status_code == 200
            assert role_retry.json()["message"] == "Model mistral:7b is downloading. You can run basic tasks."
            assert download_manager.retry_role_calls == ["planning"]

            retry_all = await client.post("/models/downloads", json={})
            assert retry_all.status_code == 200
            assert retry_all.json()["message"] == "Model downloads resumed."
            assert download_manager.retry_all_calls == 1

    asyncio.run(run_scenario())


def test_api_passes_session_context_to_router(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    planner = PlannerAgent(ollama_client=FailingOllamaClient())
    model_manager = build_model_manager(tmp_path)
    session_manager = SessionManager()
    router = RecordingRouter(session_manager=session_manager)
    app = create_app(
        planner=planner,
        history_store=TaskHistoryStore(db_path),
        model_manager=model_manager,
        router=router,  # type: ignore[arg-type]
        session_manager=session_manager,
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            workdir = tmp_path / "workspace"
            workdir.mkdir()

            first = await client.post("/task", json={"command": "create a folder first", "cwd": str(workdir)})
            assert first.status_code == 200

            second = await client.post("/task", json={"command": "create a folder second", "cwd": str(workdir)})
            assert second.status_code == 200

        assert len(router.contexts) == 2
        assert router.contexts[0]["last_mode"] is None
        assert router.contexts[0]["last_agent"] is None
        assert router.contexts[0]["recent_messages"] == []
        assert router.contexts[0]["current_task_state"] is None
        assert router.contexts[0]["related_tasks"] == []
        assert router.contexts[1]["last_mode"] == "execution"
        assert router.contexts[1]["last_task_type"] == "system"
        assert router.contexts[1]["last_agent"] == "planning"
        assert router.contexts[1]["recent_messages"] == ["create a folder first"]
        assert router.contexts[1]["related_tasks"] == [
            {
                "task_id": first.json()["task_id"],
                "summary": "Completed: create a folder first",
            }
        ]
        current_task_state = router.contexts[1]["current_task_state"]
        assert current_task_state == {
            "status": "completed",
            "task_type": "system",
            "agent": "planning",
            "active_command": "create a folder first",
            "task_id": current_task_state["task_id"],
        }

    asyncio.run(run_scenario())


def test_api_returns_conversation_mode_without_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    app = create_app(
        planner=PlannerAgent(ollama_client=FailingOllamaClient()),
        history_store=TaskHistoryStore(db_path),
        model_manager=build_model_manager(tmp_path),
        router=ConversationRouter(),  # type: ignore[arg-type]
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            workdir = tmp_path / "workspace"
            workdir.mkdir()

            response = await client.post("/task", json={"command": "Let's discuss my project idea", "cwd": str(workdir)})
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert payload["steps"] == []
            assert payload["result"]["conversation"]["mode"] == "conversation"

    asyncio.run(run_scenario())


def test_api_retries_failed_step_and_then_succeeds(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    step = PlanStep(
        description="Create folder demo",
        role="executor",
        tool_name="test.create_folder_flaky",
        args={"path": "demo"},
    )
    tool_registry, calls = build_flaky_registry(fail_until_attempt=2)
    app = create_app(
        planner=StubPlanningAgent([step]),  # type: ignore[arg-type]
        history_store=TaskHistoryStore(db_path),
        model_manager=build_model_manager(tmp_path),
        router=RecordingRouter(),  # type: ignore[arg-type]
        tool_registry=tool_registry,
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            workdir = tmp_path / "workspace"
            workdir.mkdir()

            response = await client.post("/task", json={"command": "create a folder demo", "cwd": str(workdir)})
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is True
            assert calls["count"] == 3

    asyncio.run(run_scenario())


def test_api_aborts_safely_after_retry_exhaustion(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    step = PlanStep(
        description="Create folder demo",
        role="executor",
        tool_name="test.create_folder_flaky",
        args={"path": "demo"},
    )
    tool_registry, calls = build_flaky_registry(always_fail=True)
    analysis = StubAnalysisAgent()
    app = create_app(
        planner=StubPlanningAgent([step]),  # type: ignore[arg-type]
        analysis_agent=analysis,  # type: ignore[arg-type]
        history_store=TaskHistoryStore(db_path),
        model_manager=build_model_manager(tmp_path),
        router=RecordingRouter(),  # type: ignore[arg-type]
        tool_registry=tool_registry,
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            workdir = tmp_path / "workspace"
            workdir.mkdir()

            response = await client.post("/task", json={"command": "create a folder demo", "cwd": str(workdir)})
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "failed"
            assert payload["success"] is False
            assert payload["result"]["failed_step_index"] == 0
            assert payload["result"]["failure_analysis"]["analysis"] == "Failure diagnosed."
            assert calls["count"] == 3
            assert analysis.calls == 1

    asyncio.run(run_scenario())


def test_api_delegates_task_and_approval_execution_to_engine(tmp_path: Path) -> None:
    engine = StubExecutionEngine()
    app = create_app(execution_engine=engine, vector_store=VectorStore(db_path=tmp_path / "vectors.db"))  # type: ignore[arg-type]

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            workdir = tmp_path / "workspace"
            workdir.mkdir()

            task_response = await client.post("/task", json={"command": "create a folder demo", "cwd": str(workdir)})
            assert task_response.status_code == 200
            assert task_response.json()["task_id"] == "task-stubbed"

            approval_response = await client.post(
                "/approvals/approval-1234",
                json={"token": "token-1", "decision": "deny"},
            )
            assert approval_response.status_code == 200
            assert approval_response.json()["status"] == "cancelled"

        assert engine.run_calls == [("create a folder demo", {"cwd": str(workdir)})]
        assert engine.approval_calls == [("approval-1234", "token-1", "deny")]

    asyncio.run(run_scenario())
