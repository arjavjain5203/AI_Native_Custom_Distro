import json
from pathlib import Path

import pytest

from ai_core.agents.coding import CodingAgent
from ai_core.memory.vector_store import VectorStore


class BaseFakeModelManager:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_model_for_task(self, task_type: str) -> str:
        assert task_type == "coding"
        return "deepseek-coder"


class SingleResponseModelManager(BaseFakeModelManager):
    def __init__(self, response: str) -> None:
        super().__init__()
        self.response = response

    def run_model(self, model_name: str, prompt: str, *, runtime: str | None = None, task_type: str | None = None) -> str:
        assert model_name == "deepseek-coder"
        assert task_type == "coding"
        self.calls.append(prompt)
        return self.response


class RetryingSyntaxModelManager(BaseFakeModelManager):
    def __init__(self, repo: Path) -> None:
        super().__init__()
        self.repo = repo

    def run_model(self, model_name: str, prompt: str, *, runtime: str | None = None, task_type: str | None = None) -> str:
        self.calls.append(prompt)
        if len(self.calls) == 1:
            return json.dumps(
                {
                    "actions": [
                        {
                            "action": "edit_file",
                            "file": "app.py",
                            "content": "def hello(\n    return 'broken'\n",
                        }
                    ]
                }
            )
        assert (self.repo / "app.py").read_text(encoding="utf-8") == "def hello():\n    return 'old'\n"
        return json.dumps(
            {
                "actions": [
                    {
                        "action": "edit_file",
                        "file": "app.py",
                        "content": "def hello():\n    return 'fixed'\n",
                    }
                ]
            }
        )


def build_agent(tmp_path: Path, model_manager: object) -> CodingAgent:
    return CodingAgent(
        model_manager=model_manager,  # type: ignore[arg-type]
        vector_store=VectorStore(db_path=tmp_path / "vectors.db"),
    )


def test_coding_agent_updates_file_and_returns_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 'old'\n", encoding="utf-8")
    model_manager = SingleResponseModelManager(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "edit_file",
                        "file": "app.py",
                        "content": "def hello():\n    return 'updated'\n",
                    }
                ]
            }
        )
    )

    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is True
    assert result.error is None
    assert result.actions == [
        {
            "action": "edit_file",
            "file": "app.py",
            "content": "def hello():\n    return 'updated'\n",
        }
    ]
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["tool_name"] == "update_file"
    assert result.model_response
    assert "app.py" in result.changed_files
    assert "app.py" in result.diffs
    assert result.validation["retrieval_used"] is True
    assert result.validation["syntax_ok"] is True
    assert result.validation["imports_ok"] is True
    assert result.validation["retries_used"] == 0
    assert result.tests == {"executed": False, "passed": False, "failures": []}
    assert (repo / "app.py").read_text(encoding="utf-8") == "def hello():\n    return 'updated'\n"
    assert len(model_manager.calls) == 1


def test_coding_agent_validates_instruction(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("print('hello')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="instruction"):
        build_agent(
            tmp_path,
            SingleResponseModelManager('{"actions": []}'),
        ).execute_step("", str(repo), {"instruction": ""})


def test_coding_agent_retries_when_generated_python_has_syntax_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 'old'\n", encoding="utf-8")

    model_manager = RetryingSyntaxModelManager(repo)
    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is True
    assert result.validation["syntax_ok"] is True
    assert result.validation["imports_ok"] is True
    assert result.validation["retries_used"] == 1
    assert len(model_manager.calls) == 2
    assert (repo / "app.py").read_text(encoding="utf-8") == "def hello():\n    return 'fixed'\n"


def test_coding_agent_returns_import_issues_as_warnings_without_retrying(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 'old'\n", encoding="utf-8")

    model_manager = SingleResponseModelManager(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "edit_file",
                        "file": "app.py",
                        "content": "def hello():\n    return os.getcwd()\n",
                    }
                ]
            }
        )
    )
    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is True
    assert result.validation["syntax_ok"] is True
    assert result.validation["imports_ok"] is False
    assert result.validation["warnings"] == ["app.py: possible missing import or undefined name(s): os"]
    assert result.validation["retries_used"] == 0
    assert len(model_manager.calls) == 1
    assert (repo / "app.py").read_text(encoding="utf-8") == "def hello():\n    return os.getcwd()\n"


def test_coding_agent_returns_structured_failure_after_max_retries_for_invalid_python(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    original = "def hello():\n    return 'old'\n"
    (repo / "app.py").write_text(original, encoding="utf-8")

    model_manager = SingleResponseModelManager(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "edit_file",
                        "file": "app.py",
                        "content": "def hello(\n    return 'broken'\n",
                    }
                ]
            }
        )
    )
    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is False
    assert result.error == "Validation failed after retries"
    assert result.changed_files == []
    assert result.diffs == {}
    assert result.validation["syntax_ok"] is False
    assert result.validation["imports_ok"] is True
    assert result.validation["retries_used"] == 2
    assert len(model_manager.calls) == 3
    assert (repo / "app.py").read_text(encoding="utf-8") == original


def test_coding_agent_rejects_free_text_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    original = "def hello():\n    return 'old'\n"
    (repo / "app.py").write_text(original, encoding="utf-8")

    model_manager = SingleResponseModelManager("Here is the code update you requested.")
    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is False
    assert result.error == "Validation failed after retries"
    assert result.actions == []
    assert result.tool_calls == []
    assert result.validation["errors"]
    assert len(model_manager.calls) == 3
    assert (repo / "app.py").read_text(encoding="utf-8") == original


def test_coding_agent_fails_when_action_produces_no_verified_file_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    original = "def hello():\n    return 'old'\n"
    (repo / "app.py").write_text(original, encoding="utf-8")

    model_manager = SingleResponseModelManager(
        json.dumps(
            {
                "actions": [
                    {
                        "action": "edit_file",
                        "file": "app.py",
                        "content": original,
                    }
                ]
            }
        )
    )
    result = build_agent(tmp_path, model_manager).execute_step(
        "update hello function",
        str(repo),
        {"instruction": "update hello function"},
    )

    assert result.success is False
    assert result.error == "coding action 'update_file' produced no verified file changes"
    assert result.changed_files == []
    assert result.actions[0]["file"] == "app.py"
    assert result.tool_calls == []
    assert "produced no verified file changes" in result.validation["errors"][-1]
    assert (repo / "app.py").read_text(encoding="utf-8") == original
