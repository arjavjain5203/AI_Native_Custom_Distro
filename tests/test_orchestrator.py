from ai_core.core.session import SessionManager
from ai_core.models.orchestrator import Orchestrator
from ai_core.models.ollama import OllamaError


class FakeModelManager:
    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get_model_for_role(self, role: str) -> str:
        assert role in {"orchestrator", "intent"}
        return "gemma:2b"

    def run_model(
        self,
        model_name: str,
        prompt: str,
        *,
        runtime: str | None = None,
        task_type: str | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        self.calls.append(
            {
                "model_name": model_name,
                "prompt": prompt,
                "runtime": runtime,
                "task_type": task_type,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_orchestrator_accepts_valid_model_json() -> None:
    manager = FakeModelManager(
        response='{"mode":"execution","task_type":"coding","agent":"coding","confidence":0.97}'
    )
    orchestrator = Orchestrator(model_manager=manager, timeout_seconds=4)

    decision = orchestrator.classify_input("Add JWT authentication to this project", {})

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "coding"
    assert manager.calls[0]["runtime"] == "ollama"
    assert manager.calls[0]["timeout_seconds"] == 4
    assert "current_task_state=" in str(manager.calls[0]["prompt"])
    assert "related_tasks=" in str(manager.calls[0]["prompt"])


def test_orchestrator_falls_back_on_invalid_json() -> None:
    manager = FakeModelManager(response='{"mode":"execution","task_type":"nope","agent":"coding","confidence":0.9}')
    orchestrator = Orchestrator(model_manager=manager)

    decision = orchestrator.classify_input("create folder test", {})

    assert decision["task_type"] == "system"
    assert decision["agent"] == "planning"


def test_orchestrator_falls_back_on_timeout() -> None:
    manager = FakeModelManager(error=TimeoutError("timed out"))
    orchestrator = Orchestrator(model_manager=manager)

    decision = orchestrator.classify_input("Let's discuss my project idea", {})

    assert decision["mode"] == "conversation"
    assert decision["task_type"] == "planning"


def test_orchestrator_falls_back_on_model_failure() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    orchestrator = Orchestrator(model_manager=manager)

    decision = orchestrator.classify_input("debug this error from the logs", {})

    assert decision["task_type"] == "analysis"
    assert decision["agent"] == "analysis"


def test_orchestrator_falls_back_to_coding_for_fastapi_app_request() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    orchestrator = Orchestrator(model_manager=manager)

    decision = orchestrator.classify_input("create a fastapi app", {})

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "coding"
    assert decision["agent"] == "coding"


def test_orchestrator_falls_back_to_system_for_list_files_request() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    orchestrator = Orchestrator(model_manager=manager)

    decision = orchestrator.classify_input("list files in current directory", {})

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "system"
    assert decision["agent"] == "planning"


def test_orchestrator_updates_session_context_when_session_id_is_provided() -> None:
    manager = FakeModelManager(
        response='{"mode":"conversation","task_type":"planning","agent":"planning","confidence":0.92}'
    )
    sessions = SessionManager()
    orchestrator = Orchestrator(model_manager=manager, session_manager=sessions)

    decision = orchestrator.classify_input("Let's discuss my project idea", {"cwd": "/tmp/project"}, session_id="project")

    assert decision["mode"] == "conversation"
    context = sessions.get_context("project")
    assert context["last_mode"] == "conversation"
    assert context["last_task_type"] == "planning"
    assert context["last_agent"] == "planning"
    assert context["recent_messages"] == ["Let's discuss my project idea"]
    assert context["current_task_state"] == {
        "status": "conversation",
        "task_type": "planning",
        "agent": "planning",
        "active_command": "Let's discuss my project idea",
    }


def test_orchestrator_continues_task_across_follow_up_commands() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    sessions = SessionManager()
    sessions.update(
        "project",
        "create a project",
        mode="execution",
        task_type="system",
        agent="planning",
        current_task_state={
            "status": "completed",
            "task_type": "system",
            "agent": "planning",
            "active_command": "create a project",
        },
    )
    orchestrator = Orchestrator(model_manager=manager, session_manager=sessions)

    decision = orchestrator.classify_input("add authentication", {"cwd": "/tmp/project"}, session_id="project")

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "coding"
    assert decision["agent"] == "coding"


def test_orchestrator_switches_from_conversation_to_execution_on_follow_up() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    sessions = SessionManager()
    sessions.update(
        "project",
        "Let's discuss my project idea",
        mode="conversation",
        task_type="planning",
        agent="planning",
        current_task_state={
            "status": "conversation",
            "task_type": "planning",
            "agent": "planning",
            "active_command": "Let's discuss my project idea",
        },
    )
    orchestrator = Orchestrator(model_manager=manager, session_manager=sessions)

    decision = orchestrator.classify_input("now create the structure", {"cwd": "/tmp/project"}, session_id="project")

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "system"
    assert decision["agent"] == "planning"


def test_orchestrator_routes_implement_it_to_coding_after_planning() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    sessions = SessionManager()
    sessions.update(
        "project",
        "create a project",
        mode="execution",
        task_type="planning",
        agent="planning",
        current_task_state={
            "status": "completed",
            "task_type": "planning",
            "agent": "planning",
            "active_command": "create a project",
        },
    )
    orchestrator = Orchestrator(model_manager=manager, session_manager=sessions)

    decision = orchestrator.classify_input("implement it", {"cwd": "/tmp/project"}, session_id="project")

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "coding"
    assert decision["agent"] == "coding"


def test_orchestrator_keeps_safe_fallback_when_context_is_unclear() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    orchestrator = Orchestrator(model_manager=manager, session_manager=SessionManager())

    decision = orchestrator.classify_input("continue", {"cwd": "/tmp"}, session_id="workspace")

    assert decision["mode"] == "conversation"
    assert decision["task_type"] == "planning"
    assert decision["agent"] == "planning"


def test_orchestrator_uses_related_tasks_for_similar_project_fallback() -> None:
    manager = FakeModelManager(error=OllamaError("ollama unavailable"))
    orchestrator = Orchestrator(model_manager=manager, session_manager=SessionManager())

    decision = orchestrator.classify_input(
        "create similar project",
        {
            "cwd": "/tmp/project",
            "related_tasks": [
                {
                    "task_id": "task-1",
                    "summary": "Completed: create a Flask app with JWT authentication",
                }
            ],
        },
        session_id="project",
    )

    assert decision["mode"] == "execution"
    assert decision["task_type"] == "system"
    assert decision["agent"] == "planning"
