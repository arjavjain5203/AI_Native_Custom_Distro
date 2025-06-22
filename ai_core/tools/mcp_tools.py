"""MCP-backed tool wrappers for registry integration."""

from __future__ import annotations

from typing import Any

from ai_core.mcp import MCPClient

from .registry import ToolDefinition, ToolExecutionContext, ToolRegistry


def register_mcp_tools(registry: ToolRegistry, mcp_client: MCPClient) -> ToolRegistry:
    """Register MCP-backed tools into the provided registry."""
    registry.register(
        make_mcp_tool_definition(
            name="github.create_repo",
            remote_name="github.create_repo",
            mcp_client=mcp_client,
            args_schema={
                "name": {"type": "string", "required": True},
                "private": {"type": "bool", "required": False},
            },
            requires_approval=True,
            rollback_supported=False,
            category="github",
        )
    )
    registry.register(
        make_mcp_tool_definition(
            name="github.create_branch",
            remote_name="github.create_branch",
            mcp_client=mcp_client,
            args_schema={
                "owner": {"type": "string", "required": True},
                "repo": {"type": "string", "required": True},
                "branch_name": {"type": "string", "required": True},
                "from_sha": {"type": "string", "required": True},
            },
            requires_approval=True,
            rollback_supported=False,
            category="github",
        )
    )
    registry.register(
        make_mcp_tool_definition(
            name="github.push_file",
            remote_name="github.push_file",
            mcp_client=mcp_client,
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
        )
    )
    return registry


def make_mcp_tool_definition(
    *,
    name: str,
    remote_name: str,
    mcp_client: MCPClient,
    args_schema: dict[str, dict[str, Any]],
    requires_approval: bool,
    rollback_supported: bool,
    category: str,
) -> ToolDefinition:
    """Create one MCP-backed registry entry."""
    return ToolDefinition(
        name=name,
        handler=_make_mcp_handler(mcp_client, remote_name),
        args_schema=args_schema,
        requires_approval=requires_approval,
        rollback_supported=rollback_supported,
        category=category,
        source="mcp",
    )


def _make_mcp_handler(mcp_client: MCPClient, remote_name: str):
    def handler(args: dict[str, Any], context: ToolExecutionContext) -> Any:
        del context
        response = mcp_client.call_tool(remote_name, args)
        if not response.get("success", False):
            error_payload = response.get("error")
            raise RuntimeError(_format_mcp_error(remote_name, error_payload))
        return response.get("result")

    return handler


def _format_mcp_error(tool_name: str, error_payload: Any) -> str:
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        if message is not None:
            return f"{tool_name}: {message}"
    return f"{tool_name}: MCP tool call failed"
