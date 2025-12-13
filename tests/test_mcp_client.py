from __future__ import annotations

from pathlib import Path
import sys

import pytest

from ai_core.mcp import MCPClient, MCPConnectionError, MCPProtocolError, MCPTimeoutError


def write_server_script(path: Path) -> None:
    path.write_text(
        """
import json
import sys
import time

mode = sys.argv[1]

for line in sys.stdin:
    request = json.loads(line)
    request_id = request.get("id")
    params = request.get("params", {})

    if mode == "success":
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "received_name": params.get("name"),
                "received_args": params.get("arguments", {}),
            },
        }
        sys.stdout.write(json.dumps(response) + "\\n")
        sys.stdout.flush()
    elif mode == "error":
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": "remote exploded",
                "data": {"tool": params.get("name")},
            },
        }
        sys.stdout.write(json.dumps(response) + "\\n")
        sys.stdout.flush()
    elif mode == "invalid-json":
        sys.stdout.write("this-is-not-json\\n")
        sys.stdout.flush()
    elif mode == "timeout":
        time.sleep(1.0)
        response = {"jsonrpc": "2.0", "id": request_id, "result": {"late": True}}
        sys.stdout.write(json.dumps(response) + "\\n")
        sys.stdout.flush()
""".strip()
        + "\n",
        encoding="utf-8",
    )


def build_client(tmp_path: Path, mode: str) -> MCPClient:
    server_script = tmp_path / "fake_mcp_server.py"
    write_server_script(server_script)
    return MCPClient([sys.executable, str(server_script), mode], default_timeout_seconds=0.2)


def test_mcp_client_calls_tool_successfully(tmp_path: Path) -> None:
    client = build_client(tmp_path, "success")

    try:
        result = client.call_tool("github.create_repo", {"name": "demo"})
        second = client.call_tool("github.create_repo", {"name": "demo-2"})
        process = client._process
        assert process is not None
        assert process.poll() is None
    finally:
        client.close()

    assert result == {
        "success": True,
        "tool_name": "github.create_repo",
        "result": {
            "received_name": "github.create_repo",
            "received_args": {"name": "demo"},
        },
        "error": None,
    }
    assert second["success"] is True


def test_mcp_client_returns_structured_remote_error(tmp_path: Path) -> None:
    client = build_client(tmp_path, "error")

    try:
        result = client.call_tool("aws.deploy", {"service": "api"})
    finally:
        client.close()

    assert result == {
        "success": False,
        "tool_name": "aws.deploy",
        "result": None,
        "error": {
            "code": -32000,
            "message": "remote exploded",
            "data": {"tool": "aws.deploy"},
        },
    }


def test_mcp_client_raises_on_invalid_json_response(tmp_path: Path) -> None:
    client = build_client(tmp_path, "invalid-json")

    with pytest.raises(MCPProtocolError, match="invalid JSON"):
        try:
            client.call_tool("database.query", {"sql": "SELECT 1"})
        finally:
            client.close()


def test_mcp_client_raises_on_timeout(tmp_path: Path) -> None:
    client = build_client(tmp_path, "timeout")

    with pytest.raises(MCPTimeoutError, match="timed out"):
        try:
            client.call_tool("docker.run_container", {"image": "busybox"})
        finally:
            client.close()


def test_mcp_client_raises_on_startup_failure() -> None:
    client = MCPClient(["/definitely/missing-mcp-server"])

    with pytest.raises(MCPConnectionError, match="failed to start MCP server"):
        client.start()


def test_mcp_client_validates_tool_name_and_args(tmp_path: Path) -> None:
    client = build_client(tmp_path, "success")

    with pytest.raises(ValueError, match="service.action"):
        client.call_tool("not-valid", {"name": "demo"})

    with pytest.raises(ValueError, match="JSON object"):
        client.call_tool("github.create_repo", ["demo"])  # type: ignore[arg-type]

    client.close()
