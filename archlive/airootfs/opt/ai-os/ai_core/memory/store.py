"""Structured SQLite-backed memory storage."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from ai_core.core.config import DEFAULT_MEMORY_DB
from ai_core.core.types import PlanStep, TaskResult


SCRATCHPAD_CATEGORIES = {"model_response", "tool_output", "retrieval_context", "validation"}
ROLLBACK_SNAPSHOT_TYPES = {"file", "git", "system"}


class TaskHistoryStore:
    """Persist task history, execution logs, scratchpad entries, and snapshots."""

    def __init__(self, db_path: str | Path = DEFAULT_MEMORY_DB) -> None:
        self.db_path = Path(db_path).expanduser().resolve()

    def initialize(self) -> None:
        """Create the memory schema if it does not exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_history (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    parent_task_id TEXT,
                    task_summary TEXT NOT NULL DEFAULT '',
                    success INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(
                connection,
                "task_history",
                "parent_task_id",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "task_history",
                "task_summary",
                "TEXT NOT NULL DEFAULT ''",
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    tool_name TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scratchpad_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rollback_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def record_task(
        self,
        task_id: str,
        command: str,
        cwd: str,
        result: TaskResult,
        *,
        parent_task_id: str | None = None,
        task_summary: str | None = None,
    ) -> None:
        """Persist a task and its final result."""
        self._validate_task_id(task_id)
        self._validate_nonempty_string(command, "command")
        self._validate_nonempty_string(cwd, "cwd")
        if parent_task_id is not None:
            self._validate_task_id(parent_task_id)
        summary = (task_summary or self._derive_task_summary(command, result)).strip()
        if not summary:
            summary = self._derive_task_summary(command, result)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO task_history
                    (id, command, cwd, parent_task_id, task_summary, success, message, steps_json, result_json)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    command,
                    cwd,
                    parent_task_id,
                    summary,
                    int(result.success),
                    result.message,
                    json.dumps(self._serialize_plan_steps(result.steps)),
                    json.dumps(result.data),
                ),
            )
            connection.commit()

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent task history entries."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, command, cwd, parent_task_id, task_summary, success, message, steps_json, result_json, created_at
                FROM task_history
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        """Return a single task history entry by task ID."""
        self._validate_task_id(task_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, command, cwd, parent_task_id, task_summary, success, message, steps_json, result_json, created_at
                FROM task_history
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._task_row_to_dict(row)

    def record_execution_log(
        self,
        task_id: str,
        step_index: int,
        role: str,
        tool_name: str | None,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist a per-step execution log entry."""
        self._validate_task_id(task_id)
        self._validate_step_index(step_index)
        self._validate_nonempty_string(role, "role")
        self._validate_nonempty_string(status, "status")
        self._validate_payload_object(payload, "payload")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_logs
                    (task_id, step_index, role, tool_name, status, payload_json)
                VALUES
                    (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_index,
                    role,
                    tool_name,
                    status,
                    json.dumps(payload),
                ),
            )
            connection.commit()

    def list_execution_logs(self, task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return execution logs for a task."""
        self._validate_task_id(task_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, step_index, role, tool_name, status, payload_json, created_at
                FROM execution_logs
                WHERE task_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [self._execution_log_row_to_dict(row) for row in rows]

    def record_scratchpad(
        self,
        task_id: str,
        step_index: int,
        category: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist a scratchpad entry for a task step."""
        self._validate_task_id(task_id)
        self._validate_step_index(step_index)
        self._validate_category(category)
        self._validate_payload_object(payload, "payload")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scratchpad_entries
                    (task_id, step_index, category, payload_json)
                VALUES
                    (?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_index,
                    category,
                    json.dumps(payload),
                ),
            )
            connection.commit()

    def list_scratchpad_entries(
        self,
        task_id: str,
        *,
        step_index: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return scratchpad entries for a task, optionally filtered by step."""
        self._validate_task_id(task_id)
        if step_index is not None:
            self._validate_step_index(step_index)

        query = """
            SELECT task_id, step_index, category, payload_json, created_at
            FROM scratchpad_entries
            WHERE task_id = ?
        """
        params: list[Any] = [task_id]
        if step_index is not None:
            query += " AND step_index = ?"
            params.append(step_index)
        query += " ORDER BY id ASC LIMIT ?"
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._scratchpad_row_to_dict(row) for row in rows]

    def record_rollback_snapshot(
        self,
        task_id: str,
        step_index: int,
        snapshot_type: str,
        state: dict[str, Any],
    ) -> None:
        """Persist a rollback snapshot row for a task step."""
        self._validate_task_id(task_id)
        self._validate_step_index(step_index)
        self._validate_snapshot_type(snapshot_type)
        self._validate_payload_object(state, "state")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO rollback_snapshots
                    (task_id, step_index, snapshot_type, state_json)
                VALUES
                    (?, ?, ?, ?)
                """,
                (
                    task_id,
                    step_index,
                    snapshot_type,
                    json.dumps(state),
                ),
            )
            connection.commit()

    def list_rollback_snapshots(self, task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return rollback snapshot rows for a task."""
        self._validate_task_id(task_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT task_id, step_index, snapshot_type, state_json, created_at
                FROM rollback_snapshots
                WHERE task_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [self._rollback_row_to_dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

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
    def _task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "command": row["command"],
            "cwd": row["cwd"],
            "parent_task_id": row["parent_task_id"],
            "task_summary": row["task_summary"],
            "success": bool(row["success"]),
            "message": row["message"],
            "steps": json.loads(row["steps_json"]),
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _derive_task_summary(command: str, result: TaskResult) -> str:
        status = str(result.data.get("status", "completed" if result.success else "failed"))
        normalized_command = " ".join(command.strip().split())
        if status == "completed":
            return f"Completed: {normalized_command}"[:160]
        if status == "pending_approval":
            return f"Awaiting approval: {normalized_command}"[:160]
        if status == "cancelled":
            return f"Cancelled: {normalized_command}"[:160]
        if status == "conversation":
            return f"Discussed: {normalized_command}"[:160]
        return f"Failed: {normalized_command}"[:160]

    @staticmethod
    def _execution_log_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "step_index": row["step_index"],
            "role": row["role"],
            "tool_name": row["tool_name"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _scratchpad_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "step_index": row["step_index"],
            "category": row["category"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _rollback_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "step_index": row["step_index"],
            "snapshot_type": row["snapshot_type"],
            "state": json.loads(row["state_json"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _validate_task_id(task_id: str) -> None:
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")

    @staticmethod
    def _validate_step_index(step_index: int) -> None:
        if not isinstance(step_index, int) or step_index < 0:
            raise ValueError("step_index must be a non-negative integer")

    @staticmethod
    def _validate_nonempty_string(value: str, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")

    @staticmethod
    def _validate_payload_object(payload: dict[str, Any], field_name: str) -> None:
        if not isinstance(payload, dict):
            raise ValueError(f"{field_name} must be a JSON object")

    @staticmethod
    def _validate_category(category: str) -> None:
        if category not in SCRATCHPAD_CATEGORIES:
            raise ValueError(f"unsupported scratchpad category: {category}")

    @staticmethod
    def _validate_snapshot_type(snapshot_type: str) -> None:
        if snapshot_type not in ROLLBACK_SNAPSHOT_TYPES:
            raise ValueError(f"unsupported rollback snapshot type: {snapshot_type}")
