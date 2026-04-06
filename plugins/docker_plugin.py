"""Docker integration plugin.

Provides a safe, structured interface for container lifecycle management.
All operations run through subprocess, never through direct Docker socket
access, to maintain the tool-engine security boundary.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class DockerPlugin:
    """Plugin connector for Docker container operations."""

    binary: str = "docker"

    def _run(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        """Execute a Docker CLI command."""
        return subprocess.run(
            [self.binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def build(self, path: str = ".", *, tag: str = "ai-os-build:latest") -> dict[str, Any]:
        """Build a Docker image from the given path."""
        result = self._run("build", "-t", tag, path, timeout=300)
        return {
            "success": result.returncode == 0,
            "tag": tag,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }

    def run(
        self,
        image: str,
        *,
        name: str | None = None,
        detach: bool = True,
        ports: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Run a Docker container."""
        cmd: list[str] = ["run"]
        if detach:
            cmd.append("-d")
        if name:
            cmd.extend(["--name", name])
        if ports:
            for host_port, container_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])
        cmd.append(image)
        result = self._run(*cmd)
        return {
            "success": result.returncode == 0,
            "container_id": result.stdout.strip()[:12] if result.returncode == 0 else None,
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }

    def stop(self, container: str) -> dict[str, Any]:
        """Stop a running container."""
        result = self._run("stop", container)
        return {"success": result.returncode == 0, "container": container}

    def ps(self, *, all_containers: bool = False) -> list[dict[str, Any]]:
        """List containers."""
        cmd = ["ps", "--format", "{{json .}}"]
        if all_containers:
            cmd.append("-a")
        result = self._run(*cmd)
        if result.returncode != 0:
            return []
        containers = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return containers
