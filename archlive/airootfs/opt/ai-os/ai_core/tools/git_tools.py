"""Git tools."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Iterable

from .shell import ToolExecutionError, run_shell_command


class GitToolError(RuntimeError):
    """Raised when a git operation fails."""


def _sanitize_text(text: str, secrets: Iterable[str] = ()) -> str:
    sanitized = text
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    return sanitized


def _run_git_command(command: list[str], *, cwd: str | None = None, secrets: Iterable[str] = ()) -> str:
    try:
        return run_shell_command(command, cwd=cwd)
    except FileNotFoundError as exc:
        raise GitToolError("git is not installed or not available in PATH") from exc
    except ToolExecutionError as exc:
        raise GitToolError(_sanitize_text(str(exc), secrets)) from exc


def _run_git_status(command: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitToolError("git is not installed or not available in PATH") from exc


def is_git_repo(path: str | Path) -> bool:
    """Return True if the target path is already a git repository."""
    repo_path = Path(path).expanduser().resolve()
    completed = _run_git_status(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(repo_path))
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def git_init(path: str | Path) -> str:
    """Initialize a git repository at the target path using main as the default branch."""
    repo_path = Path(path).expanduser().resolve()
    repo_path.mkdir(parents=True, exist_ok=True)
    if is_git_repo(repo_path):
        _run_git_command(["git", "branch", "-M", "main"], cwd=str(repo_path))
        return "Reinitialized existing Git repository and set branch to main."
    _run_git_command(["git", "init"], cwd=str(repo_path))
    _run_git_command(["git", "branch", "-M", "main"], cwd=str(repo_path))
    return "Initialized empty Git repository with main as the default branch."


def git_commit(path: str | Path, message: str) -> str:
    """Stage all changes and create a commit."""
    repo_path = Path(path).expanduser().resolve()
    _run_git_command(["git", "add", "."], cwd=str(repo_path))

    diff_status = _run_git_status(["git", "diff", "--cached", "--quiet", "--exit-code"], cwd=str(repo_path))
    if diff_status.returncode == 0:
        return "No changes to commit."
    if diff_status.returncode not in {0, 1}:
        stderr = diff_status.stderr.strip()
        raise GitToolError(stderr or "could not inspect staged changes")

    return _run_git_command(["git", "commit", "-m", message], cwd=str(repo_path))


def clone_repo(repo_url: str, destination: str | Path) -> str:
    """Clone a repository into the destination path."""
    destination_path = Path(destination).expanduser().resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    return _run_git_command(["git", "clone", repo_url, str(destination_path)])


def create_branch(path: str | Path, branch_name: str) -> str:
    """Create and switch to a branch in the target repository."""
    repo_path = Path(path).expanduser().resolve()
    return _run_git_command(["git", "checkout", "-b", branch_name], cwd=str(repo_path))


def set_remote(path: str | Path, remote: str, remote_url: str, *, secrets: Iterable[str] = ()) -> str:
    """Create or update a named remote."""
    repo_path = Path(path).expanduser().resolve()
    existing = _run_git_status(["git", "remote", "get-url", remote], cwd=str(repo_path))
    command = ["git", "remote", "set-url" if existing.returncode == 0 else "add", remote, remote_url]
    return _run_git_command(command, cwd=str(repo_path), secrets=secrets)


def push_changes(
    path: str | Path,
    remote: str = "origin",
    branch: str | None = None,
    *,
    set_upstream: bool = False,
    secrets: Iterable[str] = (),
) -> str:
    """Push repository changes to the configured remote."""
    repo_path = Path(path).expanduser().resolve()
    command = ["git", "push"]
    if set_upstream:
        command.append("-u")
    command.append(remote)
    if branch:
        command.append(branch)
    return _run_git_command(command, cwd=str(repo_path), secrets=secrets)
