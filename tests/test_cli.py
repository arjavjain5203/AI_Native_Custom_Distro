from __future__ import annotations

import json

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
    payload = json.loads(capsys.readouterr().out)
    assert payload["configured_runtime"] == "auto"


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
    payload = json.loads(capsys.readouterr().out)
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
