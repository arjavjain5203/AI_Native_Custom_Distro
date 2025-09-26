"""GitHub tools."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request


class GitHubToolError(RuntimeError):
    """Raised when a GitHub API operation fails."""


def _get_github_token(explicit_token: str | None = None) -> str:
    token = explicit_token or os.environ.get("AI_OS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise GitHubToolError("missing GitHub token in AI_OS_GITHUB_TOKEN or GITHUB_TOKEN")
    return token


def _github_request(method: str, path: str, payload: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"https://api.github.com{path}",
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_get_github_token(token)}",
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


def create_repository(name: str, private: bool = False, token: str | None = None) -> dict[str, Any]:
    """Create a GitHub repository for the authenticated user."""
    return _github_request("POST", "/user/repos", {"name": name, "private": private}, token=token)


def create_branch_reference(
    owner: str,
    repo: str,
    branch_name: str,
    from_sha: str,
    token: str | None = None,
) -> dict[str, Any]:
    """Create a branch reference in GitHub."""
    return _github_request(
        "POST",
        f"/repos/{owner}/{repo}/git/refs",
        {"ref": f"refs/heads/{branch_name}", "sha": from_sha},
        token=token,
    )


def push_file_contents(
    owner: str,
    repo: str,
    path: str | Path,
    content: str,
    message: str,
    branch: str = "main",
    token: str | None = None,
) -> dict[str, Any]:
    """Create or update a file through the GitHub contents API."""
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    return _github_request(
        "PUT",
        f"/repos/{owner}/{repo}/contents/{Path(path).as_posix()}",
        {"message": message, "content": encoded_content, "branch": branch},
        token=token,
    )
