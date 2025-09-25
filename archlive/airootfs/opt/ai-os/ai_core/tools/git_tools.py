"""Git tools."""

from pathlib import Path

from .shell import run_shell_command


def git_init(path: str | Path) -> str:
    """Initialize a git repository at the target path."""
    repo_path = Path(path).expanduser().resolve()
    repo_path.mkdir(parents=True, exist_ok=True)
    return run_shell_command(["git", "init"], cwd=str(repo_path))


def git_commit(path: str | Path, message: str) -> str:
    """Stage all changes and create a commit."""
    repo_path = Path(path).expanduser().resolve()
    run_shell_command(["git", "add", "."], cwd=str(repo_path))
    return run_shell_command(["git", "commit", "-m", message], cwd=str(repo_path))


def clone_repo(repo_url: str, destination: str | Path) -> str:
    """Clone a repository into the destination path."""
    destination_path = Path(destination).expanduser().resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    return run_shell_command(["git", "clone", repo_url, str(destination_path)])


def create_branch(path: str | Path, branch_name: str) -> str:
    """Create and switch to a branch in the target repository."""
    repo_path = Path(path).expanduser().resolve()
    return run_shell_command(["git", "checkout", "-b", branch_name], cwd=str(repo_path))


def push_changes(path: str | Path, remote: str = "origin", branch: str | None = None) -> str:
    """Push repository changes to the configured remote."""
    repo_path = Path(path).expanduser().resolve()
    command = ["git", "push", remote]
    if branch:
        command.append(branch)
    return run_shell_command(command, cwd=str(repo_path))
