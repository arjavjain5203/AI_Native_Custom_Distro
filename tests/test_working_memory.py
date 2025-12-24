from ai_core.memory.working_memory import WorkingMemoryStore


def test_working_memory_store_lifecycle() -> None:
    store = WorkingMemoryStore()

    created = store.create(
        "task-1",
        [{"description": "Create folder demo", "tool_name": "create_folder", "args": {"path": "demo"}}],
        context={"cwd": "/tmp/demo"},
    )

    assert created["current_task_id"] == "task-1"
    assert created["step_index"] == 0
    assert created["context"]["cwd"] == "/tmp/demo"

    updated = store.update_step_index("task-1", 1, status="pending_approval")
    assert updated["step_index"] == 1
    assert updated["status"] == "pending_approval"

    merged = store.update_context("task-1", {"retry_count": 1})
    assert merged["context"]["cwd"] == "/tmp/demo"
    assert merged["context"]["retry_count"] == 1

    store.clear("task-1")
    assert store.get("task-1") is None


def test_working_memory_store_validates_inputs() -> None:
    store = WorkingMemoryStore()

    try:
        store.create("", [])
    except ValueError as exc:
        assert "task_id" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected ValueError for invalid task_id")
