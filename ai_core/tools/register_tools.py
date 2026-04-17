"""Centralized registration for built-in local tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_core.mcp import MCPClient

from .filesystem import create_file, create_folder, list_files, read_file, update_file, write_file
from .git_tools import clone_repo, create_branch, git_commit, git_init, push_changes as git_push_changes
from .github_tools import (
    create_branch_reference,
    create_repo,
    infer_repo_name,
    push_changes as github_push_changes,
    push_file_contents,
)
from .mcp_tools import register_mcp_tools
from .registry import ToolDefinition, ToolExecutionContext, ToolRegistry
from .shell import run_shell_command
from .system_tools import docker_check, docker_run_command, pacman_install, pacman_query, pacman_remove


def build_tool_registry(*, mcp_client: MCPClient | None = None) -> ToolRegistry:
    """Create and populate a registry with all built-in local tools."""
    registry = ToolRegistry()
    return register_all_tools(registry, mcp_client=mcp_client)


def register_all_tools(registry: ToolRegistry, *, mcp_client: MCPClient | None = None) -> ToolRegistry:
    """Register all built-in local tools into the provided registry."""
    registry.register(
        ToolDefinition(
            name="create_folder",
            handler=_handle_create_folder,
            args_schema={"path": {"type": "string", "required": True}},
            requires_approval=False,
            rollback_supported=True,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_file",
            handler=_handle_create_file,
            args_schema={
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": False},
            },
            requires_approval=False,
            rollback_supported=True,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="read_file",
            handler=_handle_read_file,
            args_schema={"path": {"type": "string", "required": True}},
            requires_approval=False,
            rollback_supported=False,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="write_file",
            handler=_handle_write_file,
            args_schema={
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
            requires_approval=True,
            rollback_supported=True,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="update_file",
            handler=_handle_update_file,
            args_schema={
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
            requires_approval=True,
            rollback_supported=True,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="list_files",
            handler=_handle_list_files,
            args_schema={"path": {"type": "string", "required": False}},
            requires_approval=False,
            rollback_supported=False,
            category="filesystem",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="git_init",
            handler=_handle_git_init,
            args_schema={"path": {"type": "string", "required": False}},
            requires_approval=False,
            rollback_supported=False,
            category="git",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="git_commit",
            handler=_handle_git_commit,
            args_schema={
                "path": {"type": "string", "required": False},
                "message": {"type": "string", "required": True},
            },
            requires_approval=False,
            rollback_supported=True,
            category="git",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="clone_repo",
            handler=_handle_clone_repo,
            args_schema={
                "repo_url": {"type": "string", "required": True},
                "destination": {"type": "string", "required": False},
            },
            requires_approval=False,
            rollback_supported=True,
            category="git",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_branch",
            handler=_handle_create_branch,
            args_schema={
                "path": {"type": "string", "required": False},
                "branch_name": {"type": "string", "required": True},
            },
            requires_approval=False,
            rollback_supported=True,
            category="git",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="push_changes",
            handler=_handle_push_changes,
            args_schema={
                "path": {"type": "string", "required": False},
                "repo_name": {"type": "string", "required": False},
                "remote": {"type": "string", "required": False},
                "branch": {"type": "string", "required": False},
            },
            requires_approval=True,
            rollback_supported=True,
            category="git",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_repository",
            handler=_handle_create_repository,
            args_schema={
                "path": {"type": "string", "required": False},
                "name": {"type": "string", "required": False},
                "private": {"type": "bool", "required": False},
            },
            requires_approval=True,
            rollback_supported=True,
            category="github",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="create_branch_reference",
            handler=_handle_create_branch_reference,
            args_schema={
                "owner": {"type": "string", "required": True},
                "repo": {"type": "string", "required": True},
                "branch_name": {"type": "string", "required": True},
                "from_sha": {"type": "string", "required": True},
            },
            requires_approval=True,
            rollback_supported=False,
            category="github",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="push_file_contents",
            handler=_handle_push_file_contents,
            args_schema={
                "owner": {"type": "string", "required": True},
                "repo": {"type": "string", "required": True},
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "message": {"type": "string", "required": True},
                "branch": {"type": "string", "required": False},
            },
            requires_approval=True,
            rollback_supported=False,
            category="github",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="pacman_install",
            handler=_handle_pacman_install,
            args_schema={"package": {"type": "string", "required": True}},
            requires_approval=True,
            rollback_supported=True,
            category="system",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="pacman_remove",
            handler=_handle_pacman_remove,
            args_schema={"package": {"type": "string", "required": True}},
            requires_approval=True,
            rollback_supported=True,
            category="system",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="pacman_query",
            handler=_handle_pacman_query,
            args_schema={"package": {"type": "string", "required": True}},
            requires_approval=False,
            rollback_supported=False,
            category="system",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="docker_check",
            handler=_handle_docker_check,
            args_schema={},
            requires_approval=False,
            rollback_supported=False,
            category="system",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="docker_run_command",
            handler=_handle_docker_run_command,
            args_schema={"command": {"type": "string_list", "required": True}},
            requires_approval=True,
            rollback_supported=True,
            category="system",
            source="local",
        )
    )
    registry.register(
        ToolDefinition(
            name="run_shell_command",
            handler=_handle_run_shell_command,
            args_schema={
                "command": {"type": "string_list", "required": True},
                "cwd": {"type": "string", "required": False},
            },
            requires_approval=True,
            rollback_supported=False,
            category="shell",
            source="local",
        )
    )
    if mcp_client is not None:
        register_mcp_tools(registry, mcp_client)
    return registry


def _handle_create_folder(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return create_folder(_resolve_path(args["path"], context))


def _handle_create_file(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return create_file(_resolve_path(args["path"], context), content=str(args.get("content", "")))


def _handle_read_file(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return read_file(_resolve_path(args["path"], context))


def _handle_write_file(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return write_file(_resolve_path(args["path"], context), content=str(args["content"]))


def _handle_update_file(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return update_file(_resolve_path(args["path"], context), content=str(args["content"]))


def _handle_list_files(args: dict[str, Any], context: ToolExecutionContext) -> list[str]:
    target = _resolve_optional_path(args.get("path"), context)
    return list_files(target)


def _handle_git_init(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return git_init(_resolve_optional_repo_path(args.get("path"), context))


def _handle_git_commit(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return git_commit(_resolve_optional_repo_path(args.get("path"), context), message=str(args["message"]))


def _handle_clone_repo(args: dict[str, Any], context: ToolExecutionContext) -> str:
    destination = _resolve_optional_path(args.get("destination"), context)
    return clone_repo(str(args["repo_url"]), destination)


def _handle_create_branch(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return create_branch(
        _resolve_optional_repo_path(args.get("path"), context),
        branch_name=str(args["branch_name"]),
    )


def _handle_push_changes(args: dict[str, Any], context: ToolExecutionContext) -> str:
    branch = str(args.get("branch", "")).strip() or None
    repo_path = _resolve_optional_repo_path(args.get("path"), context)
    remote = _optional_string(args.get("remote"))
    if remote:
        return git_push_changes(
            repo_path,
            remote=remote,
            branch=branch,
        )
    repo_name = _optional_string(args.get("repo_name")) or infer_repo_name(repo_path)
    result = github_push_changes(
        repo_path,
        repo_name=repo_name,
        branch=branch or "main",
    )
    return f"Pushed changes to GitHub repository {result['owner']}/{result['repo']} on branch {result['branch']}."


def _handle_create_repository(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    repo_path = _resolve_optional_repo_path(args.get("path"), context)
    repo_name = _optional_string(args.get("name")) or infer_repo_name(repo_path)
    return create_repo(
        repo_name,
        private=bool(args.get("private", False)),
    )


def _handle_create_branch_reference(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return create_branch_reference(
        owner=str(args["owner"]),
        repo=str(args["repo"]),
        branch_name=str(args["branch_name"]),
        from_sha=str(args["from_sha"]),
    )


def _handle_push_file_contents(args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    branch = _optional_string(args.get("branch")) or "main"
    return push_file_contents(
        owner=str(args["owner"]),
        repo=str(args["repo"]),
        path=str(args["path"]),
        content=str(args["content"]),
        message=str(args["message"]),
        branch=branch,
    )


def _handle_pacman_install(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return pacman_install(str(args["package"]))


def _handle_pacman_remove(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return pacman_remove(str(args["package"]))


def _handle_pacman_query(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return pacman_query(str(args["package"]))


def _handle_docker_check(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return docker_check()


def _handle_docker_run_command(args: dict[str, Any], context: ToolExecutionContext) -> str:
    return docker_run_command(list(args["command"]))


def _handle_run_shell_command(args: dict[str, Any], context: ToolExecutionContext) -> str:
    cwd = _resolve_optional_path(args.get("cwd"), context)
    return run_shell_command(list(args["command"]), cwd=cwd)


def _resolve_path(path: str, context: ToolExecutionContext) -> str:
    raw_path = Path(path).expanduser()
    if raw_path.is_absolute():
        return str(raw_path.resolve())
    return str((Path(context.cwd).expanduser().resolve() / raw_path).resolve())


def _resolve_optional_path(path: Any, context: ToolExecutionContext) -> str:
    if isinstance(path, str) and path.strip():
        return _resolve_path(path, context)
    return str(Path(context.cwd).expanduser().resolve())


def _resolve_optional_repo_path(path: Any, context: ToolExecutionContext) -> str:
    return _resolve_optional_path(path, context)


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
