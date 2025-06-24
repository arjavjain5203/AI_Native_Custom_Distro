"""Centralized tool registry with lightweight schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


SUPPORTED_ARG_TYPES = {"string", "bool", "string_list", "object"}
SUPPORTED_TOOL_SOURCES = {"local", "mcp"}


class ToolRegistryError(RuntimeError):
    """Raised when tool registration, lookup, or validation fails."""


@dataclass(slots=True)
class ToolExecutionContext:
    """Execution context passed to tool handlers."""

    cwd: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolExecutionResult:
    """Normalized tool execution result."""

    success: bool
    output: Any = None
    error: str | None = None


ToolHandler = Callable[[dict[str, Any], ToolExecutionContext], Any]


@dataclass(slots=True)
class ToolDefinition:
    """Registry entry for one executable tool."""

    name: str
    handler: ToolHandler
    args_schema: dict[str, dict[str, Any]]
    requires_approval: bool
    rollback_supported: bool
    category: str
    source: Literal["local", "mcp"]


class ToolRegistry:
    """Register, validate, and execute tools through one interface."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register one tool definition."""
        self._validate_tool_definition(tool)
        if tool.name in self._tools:
            raise ToolRegistryError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Return a tool definition if it exists."""
        self._validate_tool_name(name)
        return self._tools.get(name)

    def require(self, name: str) -> ToolDefinition:
        """Return a tool definition or raise."""
        tool = self.get(name)
        if tool is None:
            raise ToolRegistryError(f"unknown tool: {name}")
        return tool

    def list_tools(self) -> list[ToolDefinition]:
        """Return registered tools sorted by name."""
        return [self._tools[name] for name in sorted(self._tools)]

    def validate_args(self, name: str, args: dict[str, Any]) -> None:
        """Validate args for a registered tool."""
        tool = self.require(name)
        if not isinstance(args, dict):
            raise ToolRegistryError("tool args must be an object")

        for arg_name, schema in tool.args_schema.items():
            required = bool(schema.get("required", False))
            if required and arg_name not in args:
                raise ToolRegistryError(f"missing required arg '{arg_name}' for tool '{name}'")
            if arg_name not in args:
                continue
            self._validate_arg_type(name, arg_name, schema["type"], args[arg_name])

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """Validate and execute a registered tool."""
        tool = self.require(name)
        self.validate_args(name, args)
        try:
            result = tool.handler(args, context)
        except Exception as exc:
            return ToolExecutionResult(success=False, output=None, error=str(exc))

        if isinstance(result, ToolExecutionResult):
            return result
        return ToolExecutionResult(success=True, output=result, error=None)

    def _validate_tool_definition(self, tool: ToolDefinition) -> None:
        self._validate_tool_name(tool.name)
        if not callable(tool.handler):
            raise ToolRegistryError(f"tool handler must be callable for '{tool.name}'")
        if not isinstance(tool.category, str) or not tool.category.strip():
            raise ToolRegistryError(f"tool category must be a non-empty string for '{tool.name}'")
        if tool.source not in SUPPORTED_TOOL_SOURCES:
            raise ToolRegistryError(f"unsupported tool source for '{tool.name}': {tool.source}")
        self._validate_schema(tool.name, tool.args_schema)

    @staticmethod
    def _validate_tool_name(name: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ToolRegistryError("tool name must be a non-empty string")

    def _validate_schema(self, tool_name: str, schema: dict[str, dict[str, Any]]) -> None:
        if not isinstance(schema, dict):
            raise ToolRegistryError(f"args_schema must be an object for tool '{tool_name}'")
        for arg_name, config in schema.items():
            if not isinstance(arg_name, str) or not arg_name.strip():
                raise ToolRegistryError(f"tool schema arg names must be non-empty strings for '{tool_name}'")
            if not isinstance(config, dict):
                raise ToolRegistryError(f"schema for arg '{arg_name}' in tool '{tool_name}' must be an object")
            arg_type = config.get("type")
            if arg_type not in SUPPORTED_ARG_TYPES:
                raise ToolRegistryError(
                    f"unsupported schema type '{arg_type}' for arg '{arg_name}' in tool '{tool_name}'"
                )
            required = config.get("required", False)
            if not isinstance(required, bool):
                raise ToolRegistryError(
                    f"'required' must be a bool for arg '{arg_name}' in tool '{tool_name}'"
                )

    @staticmethod
    def _validate_arg_type(tool_name: str, arg_name: str, expected_type: str, value: Any) -> None:
        if expected_type == "string":
            valid = isinstance(value, str)
        elif expected_type == "bool":
            valid = isinstance(value, bool)
        elif expected_type == "string_list":
            valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
        elif expected_type == "object":
            valid = isinstance(value, dict)
        else:  # pragma: no cover - schema validation guards this path
            raise ToolRegistryError(f"unsupported schema type: {expected_type}")

        if not valid:
            raise ToolRegistryError(
                f"invalid arg '{arg_name}' for tool '{tool_name}': expected {expected_type}"
            )
