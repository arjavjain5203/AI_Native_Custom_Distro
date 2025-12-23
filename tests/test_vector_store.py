from pathlib import Path

from ai_core.memory.vector_store import VectorStore


def test_vector_store_indexes_and_searches_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def create_user():\n    return 'ok'\n", encoding="utf-8")
    (repo / "notes.txt").write_text("docker setup instructions", encoding="utf-8")

    store = VectorStore(db_path=tmp_path / "vectors.db")
    indexed_count = store.index_repository(repo)
    results = store.search(repo, "create user function", limit=2)

    assert indexed_count == 2
    assert results
    assert results[0]["file_path"] == "main.py"


def test_vector_store_indexes_and_recalls_task_summaries_workspace_first(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other"
    workspace.mkdir()
    other_workspace.mkdir()

    store = VectorStore(db_path=tmp_path / "vectors.db")
    store.index_task_summary("task-1", str(workspace), "Completed: create a Flask app with auth")
    store.index_task_summary("task-2", str(other_workspace), "Completed: create a Django blog")
    store.index_task_summary("task-3", str(workspace), "Completed: add JWT authentication to Flask app")

    results = store.get_related_tasks("create similar Flask auth project", str(workspace), limit=3)

    assert [item["task_id"] for item in results[:2]] == ["task-1", "task-3"]
    assert all(set(item) == {"task_id", "summary"} for item in results)
