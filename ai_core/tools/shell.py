"""Shell execution tool."""

from collections.abc import Sequence
import subprocess


class ToolExecutionError(RuntimeError):
    """Raised when a shell-backed tool fails."""

    def __init__(self, command: Sequence[str], returncode: int, stdout: str, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        command = " ".join(self.command)
        stderr = self.stderr.strip()
        if stderr:
            return f"command failed ({self.returncode}): {command}: {stderr}"
        return f"command failed ({self.returncode}): {command}"


def run_shell_command(command: Sequence[str], cwd: str | None = None) -> str:
    """Run a command safely and return combined stdout/stderr text."""
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        raise ToolExecutionError(command, completed.returncode, completed.stdout, completed.stderr)

    output = completed.stdout.strip()
    if output:
        return output

    return completed.stderr.strip()
