from __future__ import annotations

import pytest

from ai_core.tools.mcp_tools import make_mcp_tool_definition, register_mcp_tools
from ai_core.tools.registry import ToolExecutionContext, ToolRegistry, ToolRegistryError


class FakeMCPClient:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, tool_name: str, args: dict[str, object]) -> dict[str, object]:
        self.calls.append((tool_name, dict(args)))
        if self.success:
            return {
                "success": True,
                "tool_name": tool_name,
                "result": {"echo": args},
                "error": None,
            }
        return {
            "success": False,
            "tool_name": tool_name,
            "result": None,
            "error": {"message": "remote exploded"},
        }


def test_register_mcp_tools_adds_expected_registry_entries() -> None:
    registry = ToolRegistry()
    register_mcp_tools(registry, FakeMCPClient())

    create_repo = registry.require("github.create_repo")
    assert create_repo.source == "mcp"
    assert create_repo.requires_approval is True
    assert create_repo.rollback_supported is False

    create_branch = registry.require("github.create_branch")
    assert create_branch.category == "github"

    push_file = registry.require("github.push_file")
    assert push_file.source == "mcp"


def test_mcp_tool_definition_executes_through_mcp_client() -> None:
    client = FakeMCPClient()
    registry = ToolRegistry()
    registry.register(
        make_mcp_tool_definition(
            name="github.create_repo",
            remote_name="github.create_repo",
            mcp_client=client,  # type: ignore[arg-type]
            args_schema={"name": {"type": "string", "required": True}},
            requires_approval=True,
            rollback_supported=False,
            category="github",
        )
    )

    result = registry.execute(
        "github.create_repo",
        {"name": "demo"},
        ToolExecutionContext(cwd="/tmp"),
    )

    assert client.calls == [("github.create_repo", {"name": "demo"})]
    assert result.success is True
    assert result.output == {"echo": {"name": "demo"}}


def test_mcp_tool_definition_normalizes_remote_failures() -> None:
    client = FakeMCPClient(success=False)
    registry = ToolRegistry()
    registry.register(
        make_mcp_tool_definition(
            name="github.create_repo",
            remote_name="github.create_repo",
            mcp_client=client,  # type: ignore[arg-type]
            args_schema={"name": {"type": "string", "required": True}},
            requires_approval=True,
            rollback_supported=False,
            category="github",
        )
    )

    result = registry.execute(
        "github.create_repo",
        {"name": "demo"},
        ToolExecutionContext(cwd="/tmp"),
    )

    assert result.success is False
    assert result.output is None
    assert result.error == "github.create_repo: remote exploded"


def test_registered_mcp_tool_validates_args_before_client_call() -> None:
    client = FakeMCPClient()
    registry = ToolRegistry()
    register_mcp_tools(registry, client)  # type: ignore[arg-type]

    with pytest.raises(ToolRegistryError, match="missing required arg 'name'"):
        registry.validate_args("github.create_repo", {})

    assert client.calls == []
