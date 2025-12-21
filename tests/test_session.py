from ai_core.core.session import SessionManager


def test_session_manager_returns_empty_context_for_unknown_session() -> None:
    manager = SessionManager()

    context = manager.get_context("workspace")

    assert context["last_mode"] is None
    assert context["last_task_type"] is None
    assert context["last_agent"] is None
    assert context["recent_messages"] == []
    assert context["current_task_state"] is None


def test_session_manager_tracks_recent_messages_and_metadata() -> None:
    manager = SessionManager(max_messages=2)

    manager.update(
        "workspace",
        "Let's discuss my project idea",
        mode="conversation",
        task_type="planning",
        agent="planning",
        current_task_state={"status": "conversation", "task_type": "planning", "agent": "planning"},
    )
    manager.update("workspace", "I want to build an AI system", mode="conversation", task_type="planning", agent="planning")
    context = manager.update(
        "workspace",
        "Now create the project structure",
        mode="execution",
        task_type="system",
        agent="planning",
        current_task_state={"status": "running", "task_type": "system", "agent": "planning"},
    )

    assert context["last_mode"] == "execution"
    assert context["last_task_type"] == "system"
    assert context["last_agent"] == "planning"
    assert context["recent_messages"] == [
        "I want to build an AI system",
        "Now create the project structure",
    ]
    assert context["current_task_state"] == {
        "status": "running",
        "task_type": "system",
        "agent": "planning",
    }
