import pytest

from ai_core.tools.registry import (
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolRegistry,
    ToolRegistryError,
)


def test_tool_registry_registers_and_lists_tools() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="create_file",
        handler=lambda args, context: args["path"],
        args_schema={"path": {"type": "string", "required": True}},
        requires_approval=False,
        rollback_supported=True,
        category="filesystem",
        source="local",
    )

    registry.register(tool)

    assert registry.get("create_file") is tool
    assert registry.require("create_file") is tool
    assert registry.list_tools() == [tool]


def test_tool_registry_rejects_duplicate_registration() -> None:
    registry = ToolRegistry()
    tool = ToolDefinition(
        name="git_init",
        handler=lambda args, context: "ok",
        args_schema={},
        requires_approval=False,
        rollback_supported=False,
        category="git",
        source="local",
    )
    registry.register(tool)

    with pytest.raises(ToolRegistryError, match="already registered"):
        registry.register(tool)


def test_tool_registry_validates_required_and_typed_args() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="docker.run",
            handler=lambda args, context: "ok",
            args_schema={
                "command": {"type": "string_list", "required": True},
                "detached": {"type": "bool", "required": False},
            },
            requires_approval=True,
            rollback_supported=False,
            category="system",
            source="local",
        )
    )

    with pytest.raises(ToolRegistryError, match="missing required arg 'command'"):
        registry.validate_args("docker.run", {})

    with pytest.raises(ToolRegistryError, match="expected string_list"):
        registry.validate_args("docker.run", {"command": "docker ps"})

    registry.validate_args("docker.run", {"command": ["ps"], "detached": True})


def test_tool_registry_rejects_unknown_tools_before_execution() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolRegistryError, match="unknown tool"):
        registry.execute("missing.tool", {}, ToolExecutionContext(cwd="/tmp"))


def test_tool_registry_wraps_raw_handler_results() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="read_file",
            handler=lambda args, context: f"{context.cwd}/{args['path']}",
            args_schema={"path": {"type": "string", "required": True}},
            requires_approval=False,
            rollback_supported=False,
            category="filesystem",
            source="local",
        )
    )

    result = registry.execute("read_file", {"path": "demo.txt"}, ToolExecutionContext(cwd="/workspace"))

    assert result == ToolExecutionResult(success=True, output="/workspace/demo.txt", error=None)


def test_tool_registry_normalizes_handler_exceptions() -> None:
    registry = ToolRegistry()

    def failing_handler(args, context):
        raise RuntimeError("boom")

    registry.register(
        ToolDefinition(
            name="dangerous.tool",
            handler=failing_handler,
            args_schema={},
            requires_approval=True,
            rollback_supported=True,
            category="system",
            source="local",
        )
    )

    result = registry.execute("dangerous.tool", {}, ToolExecutionContext(cwd="/tmp"))

    assert result.success is False
    assert result.output is None
    assert result.error == "boom"


def test_tool_registry_preserves_structured_result_objects() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="structured.tool",
            handler=lambda args, context: ToolExecutionResult(success=True, output={"ok": True}, error=None),
            args_schema={},
            requires_approval=False,
            rollback_supported=False,
            category="test",
            source="local",
        )
    )

    result = registry.execute("structured.tool", {}, ToolExecutionContext(cwd="/tmp"))

    assert result == ToolExecutionResult(success=True, output={"ok": True}, error=None)


def test_tool_registry_supports_mcp_sourced_tools_through_same_interface() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="github.create_repo",
            handler=lambda args, context: {"remote": "mcp", "name": args["name"]},
            args_schema={"name": {"type": "string", "required": True}},
            requires_approval=True,
            rollback_supported=False,
            category="github",
            source="mcp",
        )
    )

    tool = registry.require("github.create_repo")
    result = registry.execute("github.create_repo", {"name": "demo"}, ToolExecutionContext(cwd="/tmp"))

    assert tool.source == "mcp"
    assert tool.requires_approval is True
    assert tool.rollback_supported is False
    assert result == ToolExecutionResult(success=True, output={"remote": "mcp", "name": "demo"}, error=None)
