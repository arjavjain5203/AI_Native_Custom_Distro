from __future__ import annotations

from ai_core.tools.register_tools import build_tool_registry
from ai_core.tools.registry import ToolExecutionContext


def test_build_tool_registry_registers_all_builtin_local_tools() -> None:
    registry = build_tool_registry()

    tool_names = {tool.name for tool in registry.list_tools()}
    assert {
        "create_folder",
        "create_file",
        "read_file",
        "write_file",
        "update_file",
        "list_files",
        "git_init",
        "git_commit",
        "clone_repo",
        "create_branch",
        "push_changes",
        "create_repository",
        "create_branch_reference",
        "push_file_contents",
        "pacman_install",
        "pacman_remove",
        "pacman_query",
        "docker_check",
        "docker_run_command",
        "run_shell_command",
    }.issubset(tool_names)


def test_build_tool_registry_assigns_expected_metadata() -> None:
    registry = build_tool_registry()

    push_tool = registry.require("push_changes")
    assert push_tool.category == "git"
    assert push_tool.requires_approval is True
    assert push_tool.rollback_supported is True
    assert push_tool.source == "local"

    read_tool = registry.require("read_file")
    assert read_tool.requires_approval is False
    assert read_tool.rollback_supported is False


def test_registered_filesystem_tool_uses_context_cwd(tmp_path, monkeypatch) -> None:
    called: dict[str, str] = {}

    def fake_create_folder(path: str) -> str:
        called["path"] = path
        return path

    monkeypatch.setattr("ai_core.tools.register_tools.create_folder", fake_create_folder)

    registry = build_tool_registry()
    result = registry.execute(
        "create_folder",
        {"path": "demo"},
        ToolExecutionContext(cwd=str(tmp_path)),
    )

    assert result.success is True
    assert called["path"] == str((tmp_path / "demo").resolve())


def test_registered_shell_tool_accepts_optional_cwd(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_shell_command(command: list[str], cwd: str | None = None) -> str:
        captured["command"] = command
        captured["cwd"] = cwd
        return "ok"

    monkeypatch.setattr("ai_core.tools.register_tools.run_shell_command", fake_run_shell_command)

    registry = build_tool_registry()
    result = registry.execute(
        "run_shell_command",
        {"command": ["pwd"], "cwd": "nested"},
        ToolExecutionContext(cwd=str(tmp_path)),
    )

    assert result.success is True
    assert captured["command"] == ["pwd"]
    assert captured["cwd"] == str((tmp_path / "nested").resolve())


def test_registered_git_tool_uses_default_repo_path_from_context(tmp_path, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_git_init(path: str) -> str:
        captured["path"] = path
        return "initialized"

    monkeypatch.setattr("ai_core.tools.register_tools.git_init", fake_git_init)

    registry = build_tool_registry()
    result = registry.execute("git_init", {}, ToolExecutionContext(cwd=str(tmp_path)))

    assert result.success is True
    assert captured["path"] == str(tmp_path.resolve())


def test_build_tool_registry_optionally_registers_mcp_tools() -> None:
    class FakeMCPClient:
        def call_tool(self, tool_name: str, args: dict[str, object]) -> dict[str, object]:
            return {
                "success": True,
                "tool_name": tool_name,
                "result": {"tool_name": tool_name, "args": args},
                "error": None,
            }

    registry = build_tool_registry(mcp_client=FakeMCPClient())  # type: ignore[arg-type]

    tool = registry.require("github.create_repo")
    assert tool.source == "mcp"

    result = registry.execute(
        "github.create_repo",
        {"name": "demo"},
        ToolExecutionContext(cwd="/tmp"),
    )
    assert result.success is True
    assert result.output == {"tool_name": "github.create_repo", "args": {"name": "demo"}}
