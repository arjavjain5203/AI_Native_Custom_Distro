from __future__ import annotations

import json
import socket

from ai_core.cli import main as cli_main


def test_cli_runtime_show(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "get_runtime_status",
        lambda base_url: {
            "configured_runtime": "auto",
            "selected_runtime_by_role": {"planning": "airllm"},
            "issues": {},
            "detected_ram_gb": 8.0,
            "low_memory_threshold_gb": 12.0,
        },
    )

    exit_code = cli_main.main(["runtime"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert payload["configured_runtime"] == "auto"
    assert "Conversation mode active" not in stdout


def test_cli_runtime_update(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "set_runtime_mode",
        lambda runtime, base_url: {
            "configured_runtime": runtime,
            "selected_runtime_by_role": {"planning": "ollama"},
            "issues": {},
            "detected_ram_gb": 16.0,
            "low_memory_threshold_gb": 12.0,
        },
    )

    exit_code = cli_main.main(["runtime", "ollama"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert payload["configured_runtime"] == "ollama"


def test_cli_models_set_role(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "set_model_role",
        lambda role, runtime, model_name, base_url: {
            role: {
                "configured": {runtime: model_name},
                "runtime": runtime,
                "model_name": model_name,
                "installed": True,
            },
            "runtime": "auto",
        },
    )

    exit_code = cli_main.main(["models", "set-role", "planning", "ollama", "mistral:7b"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["planning"]["configured"]["ollama"] == "mistral:7b"


def test_cli_models_retry(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "retry_model_downloads",
        lambda role, base_url: {
            "role": role or "all",
            "message": "Model mistral:7b is downloading. You can run basic tasks.",
        },
    )

    exit_code = cli_main.main(["models", "retry", "planning"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["role"] == "planning"


def test_cli_rollback_list(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "list_rollback_candidates",
        lambda base_url: [{"task_id": "task-1", "step_index": 0, "snapshot_types": ["file"]}],
    )

    exit_code = cli_main.main(["rollback"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["task_id"] == "task-1"


def test_cli_rollback_execute(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "rollback_task",
        lambda task_id, step_index, base_url: {
            "success": True,
            "task_id": task_id,
            "step_index": step_index,
            "reverted_snapshots": 1,
        },
    )

    exit_code = cli_main.main(["rollback", "task-1", "0"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reverted_snapshots"] == 1


def test_cli_task_greeting_prints_json_then_hello(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "submit_task",
        lambda command, base_url: {
            "task_id": "task-1",
            "status": "completed",
            "success": True,
            "message": "Conversation mode active.",
            "command": command,
            "cwd": "/root",
            "steps": [],
            "result": {
                "status": "completed",
                "routing": {"task_type": "planning", "role": "planning"},
                "files_modified": [],
                "steps_completed": [],
                "errors": [],
                "model_notices": [],
                "conversation": {
                    "mode": "conversation",
                    "agent": "planning",
                    "message": "Conversation mode active. Clarify requirements or say what to execute next.",
                    "command": command,
                    "cwd": "/root",
                },
            },
            "approval_request": None,
        },
    )

    exit_code = cli_main.main(["hi"])

    assert exit_code == 0
    stdout_lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads("\n".join(stdout_lines[:-1]))["command"] == "hi"
    assert stdout_lines[-1] == "Hello."


def test_cli_task_folder_creation_prints_json_then_success_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "submit_task",
        lambda command, base_url: {
            "task_id": "task-2",
            "status": "completed",
            "success": True,
            "message": "Task completed successfully.",
            "command": command,
            "cwd": "/root",
            "steps": [],
            "result": {
                "status": "completed",
                "routing": {"task_type": "system", "role": "planning"},
                "files_modified": ["test_project"],
                "steps_completed": [
                    {
                        "step_index": 0,
                        "step": "Create folder test_project",
                        "role": "executor",
                        "tool_name": "create_folder",
                    }
                ],
                "errors": [],
                "model_notices": [],
            },
            "approval_request": None,
        },
    )

    exit_code = cli_main.main(["create", "a", "folder", "test_project"])

    assert exit_code == 0
    stdout_lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads("\n".join(stdout_lines[:-1]))["result"]["files_modified"] == ["test_project"]
    assert stdout_lines[-1] == 'I have successfully created the folder "test_project".'


def test_cli_task_failure_prints_json_then_failure_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_main,
        "submit_task",
        lambda command, base_url: {
            "task_id": "task-3",
            "status": "failed",
            "success": False,
            "message": "This task requires a more capable model. Please wait for the model to finish downloading.",
            "command": command,
            "cwd": "/root",
            "steps": [],
            "result": {
                "status": "failed",
                "routing": {"task_type": "coding", "role": "coding"},
                "files_modified": [],
                "steps_completed": [],
                "errors": [
                    {
                        "message": "This task requires a more capable model. Please wait for the model to finish downloading.",
                        "type": "model_unavailable",
                    }
                ],
                "model_notices": [],
            },
            "approval_request": None,
        },
    )

    exit_code = cli_main.main(["create", "a", "fastapi", "app"])

    assert exit_code == 0
    stdout_lines = capsys.readouterr().out.strip().splitlines()
    assert json.loads("\n".join(stdout_lines[:-1]))["status"] == "failed"
    assert stdout_lines[-1] == (
        "Task failed: This task requires a more capable model. Please wait for the model to finish downloading."
    )


def test_submit_task_uses_extended_task_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, payload: dict[str, object], *, timeout_seconds: float) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return {"status": "completed"}

    monkeypatch.setattr(cli_main, "_http_post_json", fake_post)

    cli_main.submit_task("create folder demo", "http://127.0.0.1:8000")

    assert captured["url"] == "http://127.0.0.1:8000/task"
    assert captured["timeout_seconds"] == cli_main.DEFAULT_TASK_TIMEOUT_SECONDS


def test_http_post_json_wraps_socket_timeout(monkeypatch) -> None:
    def fake_urlopen(*args, **kwargs):
        raise socket.timeout("timed out")

    monkeypatch.setattr(cli_main.request, "urlopen", fake_urlopen)

    try:
        cli_main._http_post_json("http://127.0.0.1:8000/task", {"command": "hi"})
    except cli_main.CliError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("expected CliError")
