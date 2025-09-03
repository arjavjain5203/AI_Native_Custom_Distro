"""Rollback snapshot creation and restore logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any

from ai_core.core.types import PlanStep
from ai_core.memory.store import TaskHistoryStore
from ai_core.tools.shell import ToolExecutionError, run_shell_command
from ai_core.tools.system_tools import pacman_install, pacman_remove


@dataclass(slots=True)
class RollbackResult:
    """Outcome of a rollback operation."""

    success: bool
    task_id: str
    step_index: int
    reverted_snapshots: int
    message: str


class RollbackManager:
    """Create and restore rollback snapshots for destructive actions."""

    FILE_TOOLS = {"create_file", "write_file", "update_file", "create_folder", "clone_repo"}
    GIT_TOOLS = {"git_commit", "create_branch", "push_changes"}
    SYSTEM_TOOLS = {"pacman_install", "pacman_remove", "docker_run_command", "create_repository"}

    def __init__(self, history_store: TaskHistoryStore) -> None:
        self.history_store = history_store

    def maybe_create_snapshot(self, task_id: str, step_index: int, step: PlanStep, cwd: str) -> dict[str, Any] | None:
        """Create a snapshot for destructive steps and persist it."""
        if not self.is_destructive(step):
            return None

        snapshot_type, state = self._capture_snapshot(step, cwd)
        snapshot = {
            "task_id": task_id,
            "step_id": step_index,
            "type": snapshot_type,
            "state": state,
        }
        self.history_store.record_rollback_snapshot(task_id, step_index, snapshot_type, state)
        return snapshot

    def list_candidates(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return grouped rollback candidates from persisted snapshots."""
        tasks = self.history_store.list_tasks(limit=limit)
        grouped: dict[tuple[str, int], dict[str, Any]] = {}

        for task in tasks:
            snapshots = self.history_store.list_rollback_snapshots(task["id"], limit=200)
            for snapshot in snapshots:
                key = (snapshot["task_id"], snapshot["step_index"])
                entry = grouped.setdefault(
                    key,
                    {
                        "task_id": snapshot["task_id"],
                        "step_index": snapshot["step_index"],
                        "snapshot_types": [],
                        "created_at": snapshot["created_at"],
                        "command": task["command"],
                        "cwd": task["cwd"],
                    },
                )
                entry["snapshot_types"].append(snapshot["snapshot_type"])

        return sorted(grouped.values(), key=lambda item: (item["task_id"], item["step_index"]), reverse=True)

    def rollback(self, task_id: str, step_index: int) -> RollbackResult:
        """Rollback a task to the state before the specified step."""
        snapshots = self.history_store.list_rollback_snapshots(task_id, limit=500)
        relevant = [snapshot for snapshot in snapshots if int(snapshot["step_index"]) >= step_index]
        if not relevant:
            raise ValueError(f"no rollback snapshots found for task '{task_id}' at or after step {step_index}")

        reverted = 0
        for snapshot in sorted(relevant, key=lambda item: int(item["step_index"]), reverse=True):
            self._restore_snapshot(snapshot["snapshot_type"], snapshot["state"])
            reverted += 1

        return RollbackResult(
            success=True,
            task_id=task_id,
            step_index=step_index,
            reverted_snapshots=reverted,
            message=f"Rolled back {reverted} snapshot(s) for task {task_id} from step {step_index}.",
        )

    def restore_snapshot_payload(self, snapshot_type: str, state: dict[str, Any]) -> None:
        """Restore a single snapshot payload immediately."""
        self._restore_snapshot(snapshot_type, state)

    @classmethod
    def is_destructive(cls, step: PlanStep) -> bool:
        """Return whether the step should be snapshotted."""
        return step.role == "coding" or (step.tool_name in cls.FILE_TOOLS | cls.GIT_TOOLS | cls.SYSTEM_TOOLS)

    def _capture_snapshot(self, step: PlanStep, cwd: str) -> tuple[str, dict[str, Any]]:
        if step.role == "coding":
            return self._capture_coding_snapshot(cwd)

        tool_name = step.tool_name
        if tool_name in self.FILE_TOOLS:
            return "file", self._capture_file_snapshot(step, cwd)
        if tool_name in self.GIT_TOOLS:
            return "git", self._capture_git_snapshot(step, cwd)
        if tool_name in self.SYSTEM_TOOLS:
            return "system", self._capture_system_snapshot(step, cwd)

        raise ValueError(f"step is not rollback-aware: {tool_name}")

    def _capture_file_snapshot(self, step: PlanStep, cwd: str) -> dict[str, Any]:
        tool_name = step.tool_name or ""
        if tool_name == "clone_repo":
            destination = str(step.args.get("destination", "")).strip()
            if not destination:
                raise ValueError("clone_repo requires a destination for rollback snapshotting")
            target = self._resolve_path(destination, cwd)
        else:
            path = str(step.args.get("path", "")).strip()
            if not path:
                raise ValueError(f"{tool_name} requires a path for rollback snapshotting")
            target = self._resolve_path(path, cwd)

        state: dict[str, Any] = {
            "cwd": cwd,
            "tool_name": tool_name,
            "path": str(target),
            "existed": target.exists(),
        }
        if target.exists():
            state["is_dir"] = target.is_dir()
            if target.is_file():
                state["content"] = target.read_text(encoding="utf-8", errors="replace")
        return state

    def _capture_coding_snapshot(self, cwd: str) -> tuple[str, dict[str, Any]]:
        repo_root = Path(cwd).expanduser().resolve()
        if self._is_git_repo(repo_root):
            return "git", self._capture_git_state(repo_root, created_branch=None, tool_name="coding_pipeline")
        return "file", self._capture_tree_snapshot(repo_root)

    def _capture_git_snapshot(self, step: PlanStep, cwd: str) -> dict[str, Any]:
        repo_root = Path(cwd).expanduser().resolve()
        created_branch = None
        if step.tool_name == "create_branch":
            created_branch = str(step.args.get("branch_name", "")).strip() or None
        return self._capture_git_state(repo_root, created_branch=created_branch, tool_name=step.tool_name or "git")

    def _capture_git_state(self, repo_root: Path, *, created_branch: str | None, tool_name: str) -> dict[str, Any]:
        if not self._is_git_repo(repo_root):
            raise ValueError(f"git snapshot requires a git repository: {repo_root}")

        head = run_shell_command(["git", "rev-parse", "HEAD"], cwd=str(repo_root))
        branch = run_shell_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_root))
        return {
            "cwd": str(repo_root),
            "tool_name": tool_name,
            "previous_head": head.strip(),
            "previous_branch": branch.strip(),
            "created_branch": created_branch,
        }

    def _capture_system_snapshot(self, step: PlanStep, cwd: str) -> dict[str, Any]:
        return {
            "cwd": cwd,
            "tool_name": step.tool_name,
            "args": dict(step.args),
        }

    def _capture_tree_snapshot(self, root: Path) -> dict[str, Any]:
        files: dict[str, str] = {}
        for file_path in sorted(root.rglob("*")):
            if file_path.is_file():
                files[file_path.relative_to(root).as_posix()] = file_path.read_text(encoding="utf-8", errors="replace")
        return {
            "cwd": str(root),
            "tool_name": "coding_pipeline",
            "tree": files,
        }

    def _restore_snapshot(self, snapshot_type: str, state: dict[str, Any]) -> None:
        if snapshot_type == "file":
            self._restore_file_snapshot(state)
            return
        if snapshot_type == "git":
            self._restore_git_snapshot(state)
            return
        if snapshot_type == "system":
            self._restore_system_snapshot(state)
            return
        raise ValueError(f"unsupported rollback snapshot type: {snapshot_type}")

    def _restore_file_snapshot(self, state: dict[str, Any]) -> None:
        if "tree" in state:
            self._restore_tree_snapshot(state)
            return

        target = Path(str(state["path"])).expanduser().resolve()
        existed = bool(state.get("existed", False))
        is_dir = bool(state.get("is_dir", False))

        if existed:
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(state.get("content", "")), encoding="utf-8")
            return

        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    def _restore_tree_snapshot(self, state: dict[str, Any]) -> None:
        root = Path(str(state["cwd"])).expanduser().resolve()
        tree = state.get("tree", {})
        if not isinstance(tree, dict):
            raise ValueError("tree snapshot state must be an object")

        current_files = [path for path in root.rglob("*") if path.is_file()]
        desired_files = {root / relative_path for relative_path in tree}

        for file_path in current_files:
            if file_path not in desired_files:
                file_path.unlink()

        for relative_path, content in tree.items():
            target = (root / str(relative_path)).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")

        self._remove_empty_directories(root)

    def _restore_git_snapshot(self, state: dict[str, Any]) -> None:
        repo_root = Path(str(state["cwd"])).expanduser().resolve()
        previous_branch = str(state.get("previous_branch", "")).strip()
        previous_head = str(state.get("previous_head", "")).strip()
        created_branch = state.get("created_branch")

        if previous_branch:
            run_shell_command(["git", "checkout", previous_branch], cwd=str(repo_root))
        if previous_head:
            run_shell_command(["git", "reset", "--hard", previous_head], cwd=str(repo_root))
        if isinstance(created_branch, str) and created_branch.strip() and created_branch.strip() != previous_branch:
            run_shell_command(["git", "branch", "-D", created_branch.strip()], cwd=str(repo_root))

    def _restore_system_snapshot(self, state: dict[str, Any]) -> None:
        tool_name = str(state.get("tool_name", ""))
        args = state.get("args", {})
        if not isinstance(args, dict):
            raise ValueError("system snapshot args must be an object")

        if tool_name == "pacman_install":
            package_name = str(args.get("package", "")).strip()
            if package_name:
                pacman_remove(package_name)
            return

        if tool_name == "pacman_remove":
            package_name = str(args.get("package", "")).strip()
            if package_name:
                pacman_install(package_name)
            return

    @staticmethod
    def _resolve_path(path: str, cwd: str) -> Path:
        raw_path = Path(path).expanduser()
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (Path(cwd).expanduser().resolve() / raw_path).resolve()

    @staticmethod
    def _is_git_repo(path: Path) -> bool:
        try:
            output = run_shell_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(path))
        except (ToolExecutionError, OSError):
            return False
        return output.strip() == "true"

    @staticmethod
    def _remove_empty_directories(root: Path) -> None:
        for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                continue
