"""Tests for the plugin system."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGitHubPlugin:
    """Validate GitHubPlugin behavior."""

    def test_plugin_detects_missing_token(self) -> None:
        """A plugin without a token should report unauthenticated."""
        from plugins.github_plugin import GitHubPlugin

        plugin = GitHubPlugin(token="")
        assert plugin.authenticated is False

    def test_plugin_detects_configured_token(self) -> None:
        """A plugin with a token should report authenticated."""
        from plugins.github_plugin import GitHubPlugin

        plugin = GitHubPlugin(token="ghp_test123")
        assert plugin.authenticated is True


class TestDockerPlugin:
    """Validate DockerPlugin behavior."""

    def test_plugin_initializes(self) -> None:
        """The Docker plugin should initialize with defaults."""
        from plugins.docker_plugin import DockerPlugin

        plugin = DockerPlugin()
        assert plugin.binary == "docker"

    @patch("subprocess.run")
    def test_ps_returns_empty_on_failure(self, mock_run: MagicMock) -> None:
        """Container listing should return empty list on CLI failure."""
        from plugins.docker_plugin import DockerPlugin

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        plugin = DockerPlugin()
        result = plugin.ps()
        assert result == []

    @patch("subprocess.run")
    def test_stop_returns_success(self, mock_run: MagicMock) -> None:
        """Stopping a container should report success when CLI succeeds."""
        from plugins.docker_plugin import DockerPlugin

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        plugin = DockerPlugin()
        result = plugin.stop("test-container")
        assert result["success"] is True
        assert result["container"] == "test-container"

    @patch("subprocess.run")
    def test_build_returns_result(self, mock_run: MagicMock) -> None:
        """Building an image should return success status."""
        from plugins.docker_plugin import DockerPlugin

        mock_run.return_value = MagicMock(returncode=0, stdout="Built", stderr="")
        plugin = DockerPlugin()
        result = plugin.build(tag="test:latest")
        assert result["success"] is True
        assert result["tag"] == "test:latest"
