from pathlib import Path

from ai_core.core.rollback import RollbackManager
from ai_core.core.types import PlanStep, TaskResult
from ai_core.memory.store import TaskHistoryStore


def test_rollback_manager_restores_file_state(tmp_path: Path) -> None:
    store = TaskHistoryStore(tmp_path / "history.db")
    store.initialize()
    manager = RollbackManager(store)
    file_path = tmp_path / "demo.txt"
    file_path.write_text("before", encoding="utf-8")
    step = PlanStep(
        description="Update file demo.txt",
        role="executor",
        tool_name="update_file",
        args={"path": "demo.txt", "content": "after"},
    )

    snapshot = manager.maybe_create_snapshot("task-1", 0, step, str(tmp_path))
    assert snapshot is not None

    file_path.write_text("after", encoding="utf-8")

    result = manager.rollback("task-1", 0)

    assert result.success is True
    assert file_path.read_text(encoding="utf-8") == "before"


def test_rollback_manager_lists_candidates(tmp_path: Path) -> None:
    store = TaskHistoryStore(tmp_path / "history.db")
    store.initialize()
    manager = RollbackManager(store)
    file_path = tmp_path / "demo.txt"
    step = PlanStep(
        description="Create file demo.txt",
        role="executor",
        tool_name="create_file",
        args={"path": "demo.txt", "content": ""},
    )

    store.record_task(
        "task-1",
        "create a file demo.txt",
        str(tmp_path),
        TaskResult(
            success=True,
            message="ok",
            steps=[step],
            data={"status": "completed"},
        ),
    )
    manager.maybe_create_snapshot("task-1", 0, step, str(tmp_path))
    file_path.write_text("", encoding="utf-8")

    candidates = manager.list_candidates()

    assert candidates
    assert candidates[0]["task_id"] == "task-1"
    assert candidates[0]["step_index"] == 0
