"""GitHub integration plugin.

Wraps the core GitHub tool implementations to provide a plugin-level
interface for repository creation, authentication, and remote operations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ai_core.tools.github_tools import (
    create_repository,
    push_file_contents,
)


@dataclass
class GitHubPlugin:
    """Plugin connector for GitHub operations.

    Uses a personal access token from the environment or explicit config
    to authenticate with the GitHub API.
    """

    token: str = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN", ""))

    @property
    def authenticated(self) -> bool:
        """Return whether a token is configured."""
        return bool(self.token)

    def create_repo(self, name: str, *, private: bool = False) -> dict[str, Any]:
        """Create a new GitHub repository."""
        return create_repository(name, private=private, token=self.token or None)

    def push_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        *,
        branch: str = "main",
    ) -> dict[str, Any]:
        """Push a file to a GitHub repository."""
        return push_file_contents(
            owner, repo, path, content, message,
            branch=branch, token=self.token or None,
        )
