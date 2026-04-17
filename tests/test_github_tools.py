from __future__ import annotations

from urllib import request

import pytest

from ai_core.tools.git_tools import GitToolError
from ai_core.tools.github_tools import GitHubToolError, create_repo, push_changes


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_create_repo_requires_ai_os_github_token(monkeypatch) -> None:
    monkeypatch.delenv("AI_OS_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(GitHubToolError, match="GitHub token not configured. Please set AI_OS_GITHUB_TOKEN"):
        create_repo("demo")


def test_create_repo_posts_to_authenticated_user(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req: request.Request, timeout: int = 30) -> _FakeResponse:
        captured["url"] = req.full_url
        captured["authorization"] = req.get_header("Authorization")
        captured["payload"] = req.data.decode("utf-8") if req.data else None
        return _FakeResponse('{"name":"demo","private":false}')

    monkeypatch.setenv("AI_OS_GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("ai_core.tools.github_tools.request.urlopen", fake_urlopen)

    result = create_repo("demo")

    assert result["name"] == "demo"
    assert captured["url"] == "https://api.github.com/user/repos"
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["payload"] == '{"name": "demo", "private": false}'


def test_push_changes_uses_authenticated_user_and_never_returns_token(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req: request.Request, timeout: int = 30) -> _FakeResponse:
        return _FakeResponse('{"login":"octocat"}')

    def fake_set_remote(path: str, remote: str, remote_url: str, *, secrets: tuple[str, ...] = ()) -> str:
        captured["set_remote_path"] = path
        captured["set_remote_remote"] = remote
        captured["set_remote_url"] = remote_url
        captured["set_remote_secrets"] = secrets
        return "ok"

    def fake_git_push_changes(
        path: str,
        remote: str = "origin",
        branch: str | None = None,
        *,
        set_upstream: bool = False,
        secrets: tuple[str, ...] = (),
    ) -> str:
        captured["push_path"] = path
        captured["push_remote"] = remote
        captured["push_branch"] = branch
        captured["push_set_upstream"] = set_upstream
        captured["push_secrets"] = secrets
        return "ok"

    monkeypatch.setenv("AI_OS_GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("ai_core.tools.github_tools.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ai_core.tools.github_tools.is_git_repo", lambda path: True)
    monkeypatch.setattr("ai_core.tools.github_tools.set_remote", fake_set_remote)
    monkeypatch.setattr("ai_core.tools.github_tools.git_push_changes", fake_git_push_changes)

    result = push_changes(tmp_path, repo_name="demo", branch="main")

    assert result == {
        "owner": "octocat",
        "repo": "demo",
        "branch": "main",
        "remote": "origin",
        "pushed": True,
    }
    assert captured["set_remote_path"] == tmp_path.resolve()
    assert captured["set_remote_remote"] == "origin"
    assert captured["set_remote_url"] == "https://secret-token@github.com/octocat/demo.git"
    assert captured["set_remote_secrets"] == ("secret-token",)
    assert captured["push_path"] == tmp_path.resolve()
    assert captured["push_remote"] == "origin"
    assert captured["push_branch"] == "main"
    assert captured["push_set_upstream"] is True
    assert captured["push_secrets"] == ("secret-token",)


def test_push_changes_sanitizes_token_in_git_failures(monkeypatch, tmp_path) -> None:
    def fake_urlopen(req: request.Request, timeout: int = 30) -> _FakeResponse:
        return _FakeResponse('{"login":"octocat"}')

    def fake_set_remote(path: str, remote: str, remote_url: str, *, secrets: tuple[str, ...] = ()) -> str:
        raise GitToolError("git push failed for https://secret-token@github.com/octocat/demo.git")

    monkeypatch.setenv("AI_OS_GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("ai_core.tools.github_tools.request.urlopen", fake_urlopen)
    monkeypatch.setattr("ai_core.tools.github_tools.is_git_repo", lambda path: True)
    monkeypatch.setattr("ai_core.tools.github_tools.set_remote", fake_set_remote)

    with pytest.raises(GitHubToolError) as exc_info:
        push_changes(tmp_path, repo_name="demo")

    assert "secret-token" not in str(exc_info.value)
    assert "***" in str(exc_info.value)
