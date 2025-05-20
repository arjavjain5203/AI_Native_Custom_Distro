"""Strict executor agent for tool-backed execution only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_core.core.types import ExecutionStepResult, PlanStep, TaskResult
from ai_core.tools import (
    ToolExecutionError,
    clone_repo,
    create_branch,
    create_file,
    create_folder,
    create_repository,
    docker_check,
    docker_run_command,
    git_commit,
    git_init,
    list_files,
    pacman_install,
    pacman_query,
    pacman_remove,
    push_changes,
    read_file,
    update_file,
    write_file,
)


ToolHandler = Callable[[PlanStep, str | None], Any]


class ExecutorAgent:
    """Execute validated tool steps without making routing or planning decisions."""

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {
            "create_folder": self._handle_create_folder,
            "create_file": self._handle_create_file,
            "read_file": self._handle_read_file,
            "write_file": self._handle_write_file,
            "update_file": self._handle_update_file,
            "list_files": self._handle_list_files,
            "git_init": self._handle_git_init,
            "git_commit": self._handle_git_commit,
            "clone_repo": self._handle_clone_repo,
            "create_branch": self._handle_create_branch,
            "push_changes": self._handle_push_changes,
            "create_repository": self._handle_create_repository,
            "pacman_install": self._handle_pacman_install,
            "pacman_remove": self._handle_pacman_remove,
            "pacman_query": self._handle_pacman_query,
            "docker_check": self._handle_docker_check,
            "docker_run_command": self._handle_docker_run_command,
        }

    def execute(self, steps: list[PlanStep], cwd: str | None = None) -> TaskResult:
        """Execute a list of executor-only steps and collect structured results."""
        results: list[dict[str, Any]] = []

        try:
            for step in steps:
                result = self.execute_step(step, cwd=cwd)
                results.append(
                    {
                        "step": step.description,
                        "role": result.role,
                        "tool_name": result.tool_name,
                        "result": result.output,
                        "validation": result.validation,
                    }
                )
        except (ToolExecutionError, OSError, ValueError) as exc:
            return TaskResult(
                success=False,
                message=str(exc),
                steps=steps,
                data={"step_results": results},
            )

        return TaskResult(
            success=True,
            message="Task completed successfully.",
            steps=steps,
            data={"step_results": results},
        )

    def execute_step(self, step: PlanStep, cwd: str | None = None) -> ExecutionStepResult:
        """Validate and execute one executor step."""
        self._validate_step(step)
        assert step.tool_name is not None  # validated above
        handler = self._handlers[step.tool_name]
        output = handler(step, cwd)
        validation = {
            "cwd": self._resolve_repo_path(cwd),
            "args_validated": True,
            "tool_supported": True,
        }
        return ExecutionStepResult(
            success=True,
            tool_name=step.tool_name,
            output=output,
            validation=validation,
        )

    def _validate_step(self, step: PlanStep) -> None:
        if step.role != "executor":
            raise ValueError(f"executor agent only accepts executor steps, got: {step.role}")
        if not step.tool_name:
            raise ValueError(f"missing tool for step: {step.description}")
        if step.tool_name not in self._handlers:
            raise ValueError(f"unsupported tool: {step.tool_name}")
        if not isinstance(step.args, dict):
            raise ValueError("executor step args must be an object")

    def _handle_create_folder(self, step: PlanStep, cwd: str | None) -> str:
        return create_folder(self._required_path(step, cwd, "create_folder"))

    def _handle_create_file(self, step: PlanStep, cwd: str | None) -> str:
        return create_file(
            self._required_path(step, cwd, "create_file"),
            content=str(step.args.get("content", "")),
        )

    def _handle_read_file(self, step: PlanStep, cwd: str | None) -> str:
        return read_file(self._required_path(step, cwd, "read_file"))

    def _handle_write_file(self, step: PlanStep, cwd: str | None) -> str:
        return write_file(
            self._required_path(step, cwd, "write_file"),
            content=str(step.args.get("content", "")),
        )

    def _handle_update_file(self, step: PlanStep, cwd: str | None) -> str:
        return update_file(
            self._required_path(step, cwd, "update_file"),
            content=str(step.args.get("content", "")),
        )

    def _handle_list_files(self, step: PlanStep, cwd: str | None) -> list[str]:
        return list_files(self._resolve_repo_path(cwd))

    def _handle_git_init(self, step: PlanStep, cwd: str | None) -> str:
        return git_init(self._resolve_repo_path(cwd))

    def _handle_git_commit(self, step: PlanStep, cwd: str | None) -> str:
        message = str(step.args.get("message", "")).strip()
        if not message:
            raise ValueError("git_commit requires a message")
        return git_commit(self._resolve_repo_path(cwd), message)

    def _handle_clone_repo(self, step: PlanStep, cwd: str | None) -> str:
        repo_url = str(step.args.get("repo_url", "")).strip()
        if not repo_url:
            raise ValueError("clone_repo requires a repo_url")
        destination = str(step.args.get("destination", self._resolve_repo_path(cwd))).strip()
        if not destination:
            raise ValueError("clone_repo requires a destination")
        return clone_repo(repo_url, destination)

    def _handle_create_branch(self, step: PlanStep, cwd: str | None) -> str:
        branch_name = str(step.args.get("branch_name", "")).strip()
        if not branch_name:
            raise ValueError("create_branch requires a branch_name")
        return create_branch(self._resolve_repo_path(cwd), branch_name)

    def _handle_push_changes(self, step: PlanStep, cwd: str | None) -> str:
        remote = str(step.args.get("remote", "origin")).strip() or "origin"
        branch = str(step.args.get("branch", "")).strip() or None
        return push_changes(self._resolve_repo_path(cwd), remote=remote, branch=branch)

    def _handle_create_repository(self, step: PlanStep, cwd: str | None) -> dict[str, Any]:
        name = str(step.args.get("name", "")).strip()
        if not name:
            raise ValueError("create_repository requires a name")
        return create_repository(name=name, private=bool(step.args.get("private", False)))

    def _handle_pacman_install(self, step: PlanStep, cwd: str | None) -> str:
        package_name = str(step.args.get("package", "")).strip()
        if not package_name:
            raise ValueError("pacman_install requires a package")
        return pacman_install(package_name)

    def _handle_pacman_remove(self, step: PlanStep, cwd: str | None) -> str:
        package_name = str(step.args.get("package", "")).strip()
        if not package_name:
            raise ValueError("pacman_remove requires a package")
        return pacman_remove(package_name)

    def _handle_pacman_query(self, step: PlanStep, cwd: str | None) -> str:
        package_name = str(step.args.get("package", "")).strip()
        if not package_name:
            raise ValueError("pacman_query requires a package")
        return pacman_query(package_name)

    def _handle_docker_check(self, step: PlanStep, cwd: str | None) -> str:
        return docker_check()

    def _handle_docker_run_command(self, step: PlanStep, cwd: str | None) -> str:
        command = step.args.get("command", [])
        if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
            raise ValueError("docker_run_command requires a command list")
        return docker_run_command(command)

    def _required_path(self, step: PlanStep, cwd: str | None, tool_name: str) -> str:
        path = step.args.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{tool_name} requires a path")
        return self._resolve_path(path, cwd)

    @staticmethod
    def _resolve_path(path: str, cwd: str | None = None) -> str:
        raw_path = Path(path).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        base = Path(cwd).expanduser() if cwd else Path.cwd()
        return str((base / raw_path).resolve())

    @staticmethod
    def _resolve_repo_path(cwd: str | None = None) -> str:
        return str((Path(cwd).expanduser() if cwd else Path.cwd()).resolve())
