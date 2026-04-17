"""GitHub tools."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from .git_tools import GitToolError, is_git_repo, push_changes as git_push_changes, set_remote


class GitHubToolError(RuntimeError):
    """Raised when a GitHub API operation fails."""


def _sanitize_secret(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def _get_github_token() -> str:
    token = os.environ.get("AI_OS_GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubToolError("GitHub token not configured. Please set AI_OS_GITHUB_TOKEN")
    return token


def _github_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"https://api.github.com{path}",
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_get_github_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise GitHubToolError(f"github returned HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise GitHubToolError(f"could not reach GitHub: {exc.reason}") from exc
    return json.loads(raw) if raw else {}


def _authenticated_user() -> dict[str, Any]:
    return _github_request("GET", "/user")


def _authenticated_username() -> str:
    login = str(_authenticated_user().get("login", "")).strip()
    if not login:
        raise GitHubToolError("could not determine authenticated GitHub user")
    return login


def infer_repo_name(repo_path: str | Path) -> str:
    """Infer the repository name from a local project path."""
    name = Path(repo_path).expanduser().resolve().name.strip()
    if not name:
        raise GitHubToolError("could not determine repository name from path")
    return name


def create_repo(repo_name: str, private: bool = False) -> dict[str, Any]:
    """Create a GitHub repository for the authenticated user."""
    normalized_name = repo_name.strip()
    if not normalized_name:
        raise GitHubToolError("repository name cannot be empty")
    return _github_request("POST", "/user/repos", {"name": normalized_name, "private": private})


def create_repository(name: str, private: bool = False) -> dict[str, Any]:
    """Compatibility wrapper for GitHub repository creation."""
    return create_repo(name, private=private)


def create_branch_reference(
    owner: str,
    repo: str,
    branch_name: str,
    from_sha: str,
) -> dict[str, Any]:
    """Create a branch reference in GitHub."""
    return _github_request(
        "POST",
        f"/repos/{owner}/{repo}/git/refs",
        {"ref": f"refs/heads/{branch_name}", "sha": from_sha},
    )


def push_file_contents(
    owner: str,
    repo: str,
    path: str | Path,
    content: str,
    message: str,
    branch: str = "main",
) -> dict[str, Any]:
    """Create or update a file through the GitHub contents API."""
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    return _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{Path(path).as_posix()}",
        {"message": message, "content": encoded_content, "branch": branch},
    )


def push_changes(repo_path: str | Path, repo_name: str | None = None, branch: str = "main") -> dict[str, Any]:
    """Push local repository changes to GitHub using the configured token."""
    local_repo = Path(repo_path).expanduser().resolve()
    if not is_git_repo(local_repo):
        raise GitHubToolError(f"local git repository is not initialized: {local_repo}")

    owner = _authenticated_username()
    resolved_repo_name = (repo_name or infer_repo_name(local_repo)).strip()
    token = _get_github_token()
    remote_url = f"https://{token}@github.com/{owner}/{resolved_repo_name}.git"

    try:
        set_remote(local_repo, "origin", remote_url, secrets=(token,))
        git_push_changes(local_repo, remote="origin", branch=branch, set_upstream=True, secrets=(token,))
    except GitToolError as exc:
        raise GitHubToolError(_sanitize_secret(str(exc), token)) from exc

    return {
        "owner": owner,
        "repo": resolved_repo_name,
        "branch": branch,
        "remote": "origin",
        "pushed": True,
    }
