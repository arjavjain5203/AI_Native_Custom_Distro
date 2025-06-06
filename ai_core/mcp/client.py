"""Stdio-based MCP client."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import queue
import re
import subprocess
from threading import Lock, Thread
import time
from typing import Any


logger = logging.getLogger(__name__)

_STREAM_CLOSED = object()
_VALID_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+$")


class MCPError(RuntimeError):
    """Base MCP client error."""


class MCPConnectionError(MCPError):
    """Raised when the MCP server cannot be started or the stream closes."""


class MCPTimeoutError(MCPError):
    """Raised when an MCP request times out."""


class MCPProtocolError(MCPError):
    """Raised when the MCP server responds with invalid protocol data."""


class MCPClient:
    """Simple stdio-based JSON-RPC client for MCP tool calls."""

    def __init__(
        self,
        server_command: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        default_timeout_seconds: float = 5.0,
    ) -> None:
        if not server_command or not all(isinstance(part, str) and part.strip() for part in server_command):
            raise ValueError("server_command must be a non-empty list of strings")

        self.server_command = server_command
        self.env = dict(env or {})
        self.cwd = str(Path(cwd).expanduser()) if cwd is not None else None
        self.default_timeout_seconds = default_timeout_seconds
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[object] = queue.Queue()
        self._stderr_queue: queue.Queue[str] = queue.Queue()
        self._request_lock = Lock()
        self._request_id = 0

    def __enter__(self) -> MCPClient:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> None:
        """Start the MCP server subprocess if it is not already running."""
        if self._process is not None and self._process.poll() is None:
            return

        merged_env = os.environ.copy()
        merged_env.update(self.env)

        try:
            process = subprocess.Popen(
                self.server_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.cwd,
                env=merged_env,
            )
        except OSError as exc:
            raise MCPConnectionError(f"failed to start MCP server: {exc}") from exc

        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.kill()
            raise MCPConnectionError("failed to open MCP server stdio pipes")

        self._process = process
        self._stdout_queue = queue.Queue()
        self._stderr_queue = queue.Queue()
        Thread(target=self._read_stdout, args=(process.stdout,), daemon=True).start()
        Thread(target=self._read_stderr, args=(process.stderr,), daemon=True).start()
        logger.info("Started MCP server: %s", self.server_command)

    def close(self) -> None:
        """Terminate the MCP server subprocess."""
        process = self._process
        self._process = None
        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        logger.info("Stopped MCP server: %s", self.server_command)

    def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Call an MCP tool and return a normalized result payload."""
        self._validate_tool_name(tool_name)
        self._validate_args(args)
        self.start()

        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        request_id = self._next_request_id()
        request_payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": args,
            },
        }

        with self._request_lock:
            self._write_request(request_payload)
            response = self._read_response(request_id, timeout)

        error_payload = response.get("error")
        if error_payload is not None:
            return {
                "success": False,
                "tool_name": tool_name,
                "result": None,
                "error": self._normalize_error(error_payload),
            }

        result_payload = response.get("result")
        if not isinstance(result_payload, dict):
            raise MCPProtocolError("MCP response result must be an object")

        return {
            "success": True,
            "tool_name": tool_name,
            "result": result_payload,
            "error": None,
        }

    def _write_request(self, payload: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise MCPConnectionError("MCP server is not running")

        if process.poll() is not None:
            raise MCPConnectionError("MCP server exited before request could be sent")

        serialized = json.dumps(payload) + "\n"
        try:
            process.stdin.write(serialized)
            process.stdin.flush()
        except OSError as exc:
            raise MCPConnectionError(f"failed to write MCP request: {exc}") from exc

    def _read_response(self, request_id: int, timeout_seconds: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPTimeoutError(f"MCP request timed out after {timeout_seconds} seconds")

            try:
                raw_message = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise MCPTimeoutError(f"MCP request timed out after {timeout_seconds} seconds") from exc

            if raw_message is _STREAM_CLOSED:
                stderr_output = self._drain_stderr()
                raise MCPConnectionError(
                    "MCP server closed stdout unexpectedly"
                    + (f": {stderr_output}" if stderr_output else "")
                )

            if not isinstance(raw_message, str):
                raise MCPProtocolError("MCP stdout queue returned a non-string message")

            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                raise MCPProtocolError(f"MCP server returned invalid JSON: {raw_message}") from exc

            if not isinstance(payload, dict):
                raise MCPProtocolError("MCP response must be a JSON object")

            if payload.get("id") != request_id:
                continue

            logger.info("MCP response received for request id=%s", request_id)
            return payload

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _validate_tool_name(tool_name: str) -> None:
        if not isinstance(tool_name, str) or not _VALID_TOOL_NAME.match(tool_name.strip()):
            raise ValueError("tool_name must be a non-empty 'service.action' string")

    @staticmethod
    def _validate_args(args: dict[str, Any]) -> None:
        if not isinstance(args, dict):
            raise ValueError("args must be a JSON object")

    @staticmethod
    def _normalize_error(error_payload: Any) -> dict[str, Any]:
        if isinstance(error_payload, dict):
            code = error_payload.get("code")
            message = error_payload.get("message")
            data = error_payload.get("data")
            return {
                "code": code,
                "message": str(message) if message is not None else "MCP tool call failed",
                "data": data,
            }

        return {
            "code": None,
            "message": str(error_payload),
            "data": None,
        }

    def _drain_stderr(self) -> str:
        lines: list[str] = []
        while True:
            try:
                line = self._stderr_queue.get_nowait()
            except queue.Empty:
                break
            lines.append(line)
        return " | ".join(lines[-5:])

    def _read_stdout(self, stream: Any) -> None:
        for line in iter(stream.readline, ""):
            stripped = line.strip()
            if stripped:
                self._stdout_queue.put(stripped)
        self._stdout_queue.put(_STREAM_CLOSED)

    def _read_stderr(self, stream: Any) -> None:
        for line in iter(stream.readline, ""):
            stripped = line.strip()
            if stripped:
                self._stderr_queue.put(stripped)
