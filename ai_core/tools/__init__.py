"""Tool package."""

from .filesystem import create_file, create_folder, list_files, read_file, update_file, write_file
from .git_tools import clone_repo, create_branch, git_commit, git_init, push_changes
from .github_tools import GitHubToolError, create_branch_reference, create_repository, push_file_contents
from .mcp_tools import make_mcp_tool_definition, register_mcp_tools
from .register_tools import build_tool_registry, register_all_tools
from .registry import ToolDefinition, ToolExecutionContext, ToolExecutionResult, ToolRegistry, ToolRegistryError
from .shell import ToolExecutionError, run_shell_command
from .system_tools import docker_check, docker_run_command, pacman_install, pacman_query, pacman_remove

__all__ = [
    "GitHubToolError",
    "ToolDefinition",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ToolExecutionError",
    "ToolRegistry",
    "ToolRegistryError",
    "build_tool_registry",
    "clone_repo",
    "create_branch",
    "create_branch_reference",
    "create_file",
    "create_folder",
    "create_repository",
    "docker_check",
    "docker_run_command",
    "git_commit",
    "git_init",
    "list_files",
    "make_mcp_tool_definition",
    "pacman_install",
    "pacman_query",
    "pacman_remove",
    "push_changes",
    "push_file_contents",
    "read_file",
    "register_mcp_tools",
    "register_all_tools",
    "run_shell_command",
    "update_file",
    "write_file",
]
