import sqlite3
from pathlib import Path

from ai_core.core.types import PlanStep, TaskResult
from ai_core.memory.store import TaskHistoryStore


def test_task_history_store_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    store = TaskHistoryStore(db_path)
    store.initialize()

    result = TaskResult(
        success=True,
        message="ok",
        steps=[PlanStep(description="Create folder demo", tool_name="create_folder", args={"path": "demo"})],
        data={"step_results": [{"step": "Create folder demo", "result": "/tmp/demo"}]},
    )

    store.record_task(
        "task-1",
        "create a folder demo",
        str(tmp_path),
        result,
        parent_task_id="task-0",
        task_summary="Completed: create a folder demo",
    )

    saved = store.get_task("task-1")
    assert saved is not None
    assert saved["parent_task_id"] == "task-0"
    assert saved["task_summary"] == "Completed: create a folder demo"
    assert saved["success"] is True
    assert saved["steps"][0]["tool_name"] == "create_folder"

    tasks = store.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["id"] == "task-1"
    assert tasks[0]["parent_task_id"] == "task-0"

    store.record_execution_log(
        "task-1",
        0,
        "executor",
        "create_folder",
        "completed",
        {"result": "/tmp/demo"},
    )
    logs = store.list_execution_logs("task-1")
    assert logs[0]["status"] == "completed"
    assert logs[0]["payload"]["result"] == "/tmp/demo"

    store.record_scratchpad(
        "task-1",
        0,
        "tool_output",
        {"result": "/tmp/demo"},
    )
    scratchpad = store.list_scratchpad_entries("task-1")
    assert scratchpad[0]["category"] == "tool_output"

    store.record_rollback_snapshot(
        "task-1",
        0,
        "file",
        {"path": "/tmp/demo", "content": ""},
    )
    snapshots = store.list_rollback_snapshots("task-1")
    assert snapshots[0]["snapshot_type"] == "file"


def test_task_history_store_validates_structured_payloads(tmp_path: Path) -> None:
    store = TaskHistoryStore(tmp_path / "history.db")
    store.initialize()

    try:
        store.record_scratchpad("task-1", 0, "invalid", {"x": 1})
    except ValueError as exc:
        assert "scratchpad category" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError for invalid scratchpad category")


def test_task_history_store_migrates_existing_schema_with_link_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE task_history (
            id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            cwd TEXT NOT NULL,
            success INTEGER NOT NULL,
            message TEXT NOT NULL,
            steps_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    connection.close()

    store = TaskHistoryStore(db_path)
    store.initialize()

    result = TaskResult(success=True, message="ok", data={"status": "completed"})
    store.record_task("task-1", "create a project", str(tmp_path), result, parent_task_id="task-0")

    saved = store.get_task("task-1")
    assert saved is not None
    assert saved["parent_task_id"] == "task-0"
    assert saved["task_summary"] == "Completed: create a project"
