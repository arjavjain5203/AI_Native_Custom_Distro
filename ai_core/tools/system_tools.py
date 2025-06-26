"""System-level package and Docker tools."""

from __future__ import annotations

from .shell import run_shell_command


def pacman_install(package_name: str) -> str:
    """Install a package through pacman."""
    return run_shell_command(["pacman", "-S", "--noconfirm", package_name])


def pacman_remove(package_name: str) -> str:
    """Remove a package through pacman."""
    return run_shell_command(["pacman", "-R", "--noconfirm", package_name])


def pacman_query(package_name: str) -> str:
    """Query whether a package is installed."""
    return run_shell_command(["pacman", "-Q", package_name])


def docker_check() -> str:
    """Return Docker version information."""
    return run_shell_command(["docker", "--version"])


def docker_run_command(command: list[str]) -> str:
    """Run a Docker command through the docker CLI."""
    return run_shell_command(["docker", *command])
