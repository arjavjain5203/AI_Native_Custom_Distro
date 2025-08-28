"""CLI entrypoint for the ai-os terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib import error, request

from ai_core.core.config import API_BASE_URL


class CliError(RuntimeError):
    """Raised when the CLI cannot complete a daemon request."""


def _build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _http_get_json(url: str) -> dict[str, Any]:
    try:
        with request.urlopen(url, timeout=10) as response:
            payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"daemon returned HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise CliError(f"could not reach daemon at {url}: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CliError(f"daemon returned invalid JSON: {payload}") from exc


def _http_post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise CliError(f"daemon returned HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise CliError(f"could not reach daemon at {url}: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"daemon returned invalid JSON: {raw}") from exc


def get_health(base_url: str) -> dict[str, Any]:
    return _http_get_json(_build_url(base_url, "/health"))


def get_task(task_id: str, base_url: str) -> dict[str, Any]:
    return _http_get_json(_build_url(base_url, f"/tasks/{task_id}"))


def list_tasks(base_url: str, limit: int) -> list[dict[str, Any]]:
    url = _build_url(base_url, f"/tasks?limit={limit}")
    response = _http_get_json(url)
    if not isinstance(response, list):
        raise CliError(f"daemon returned invalid task list payload: {response}")
    return response


def submit_task(command: str, base_url: str) -> dict[str, Any]:
    return _http_post_json(
        _build_url(base_url, "/task"),
        {"command": command, "cwd": os.getcwd()},
    )


def get_runtime_status(base_url: str) -> dict[str, Any]:
    return _http_get_json(_build_url(base_url, "/runtime"))


def set_runtime_mode(runtime: str, base_url: str) -> dict[str, Any]:
    return _http_post_json(_build_url(base_url, "/runtime"), {"runtime": runtime})


def get_models(base_url: str) -> dict[str, Any]:
    return _http_get_json(_build_url(base_url, "/models"))


def set_model_role(role: str, runtime: str, model_name: str, base_url: str) -> dict[str, Any]:
    return _http_post_json(
        _build_url(base_url, "/models/roles"),
        {"role": role, "runtime": runtime, "model_name": model_name},
    )


def submit_approval(approval_id: str, token: str, decision: str, base_url: str) -> dict[str, Any]:
    return _http_post_json(
        _build_url(base_url, f"/approvals/{approval_id}"),
        {"token": token, "decision": decision},
    )


def list_rollback_candidates(base_url: str, limit: int = 20) -> list[dict[str, Any]]:
    url = _build_url(base_url, f"/rollback?limit={limit}")
    response = _http_get_json(url)
    if not isinstance(response, list):
        raise CliError(f"daemon returned invalid rollback list payload: {response}")
    return response


def rollback_task(task_id: str, step_index: int, base_url: str) -> dict[str, Any]:
    return _http_post_json(
        _build_url(base_url, "/rollback"),
        {"task_id": task_id, "step_index": step_index},
    )


def _print_json(response: Any) -> None:
    print(json.dumps(response, indent=2))


def _resolve_approval_if_needed(response: dict[str, Any], base_url: str) -> dict[str, Any]:
    current = response
    while current.get("status") == "pending_approval":
        approval = current.get("approval_request") or {}
        approval_id = approval.get("approval_id")
        token = approval.get("token")
        prompt = str(approval.get("prompt", "Approve this action?"))
        if not approval_id or not token:
            raise CliError("daemon returned a pending approval response without approval metadata")

        try:
            answer = input(f"{prompt} [y/N]: ").strip().lower()
        except EOFError:
            answer = "n"
        except KeyboardInterrupt:
            print()
            answer = "n"

        decision = "approve" if answer in {"y", "yes"} else "deny"
        current = submit_approval(approval_id, token, decision, base_url)
    return current


def _interactive_loop(base_url: str) -> int:
    print(f"ai-os terminal connected to {base_url}")
    print("Type a task, 'health', 'runtime', 'models', or 'exit'.")

    while True:
        try:
            command = input("ai-os> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        if not command:
            continue
        if command.lower() in {"exit", "quit"}:
            return 0

        try:
            _print_json(_dispatch_command(command.split(), base_url))
        except CliError as exc:
            print(f"Error: {exc}", file=sys.stderr)


def _dispatch_command(tokens: list[str], base_url: str) -> Any:
    if not tokens:
        return {}

    if tokens[0] == "runtime":
        if len(tokens) == 1:
            return get_runtime_status(base_url)
        if len(tokens) == 2:
            return set_runtime_mode(tokens[1], base_url)
        raise CliError("usage is 'ai-os runtime [auto|ollama|airllm]'")

    if tokens[0] == "models":
        if len(tokens) == 1 or tokens[1] == "list":
            return get_models(base_url)
        if len(tokens) == 5 and tokens[1] == "set-role":
            return set_model_role(tokens[2], tokens[3], tokens[4], base_url)
        raise CliError("usage is 'ai-os models [list|set-role <role> <runtime> <model>]'.")

    if tokens[0] == "health":
        return get_health(base_url)

    if tokens[0] == "rollback":
        if len(tokens) == 1 or (len(tokens) == 2 and tokens[1] == "list"):
            return list_rollback_candidates(base_url)
        if len(tokens) == 3:
            try:
                step_index = int(tokens[2])
            except ValueError as exc:
                raise CliError("rollback step_index must be an integer") from exc
            return rollback_task(tokens[1], step_index, base_url)
        raise CliError("usage is 'ai-os rollback [list|<task_id> <step_index>]'")

    task_response = submit_task(" ".join(tokens), base_url)
    return _resolve_approval_if_needed(task_response, base_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-os", description="AI developer terminal")
    parser.add_argument("command", nargs="*", help="Optional command to run.")
    parser.add_argument("--base-url", default=API_BASE_URL, help=f"Daemon base URL. Default: {API_BASE_URL}")
    parser.add_argument("--health", action="store_true", help="Check daemon health and exit.")
    parser.add_argument("--task-id", help="Fetch a previously stored task by ID and exit.")
    parser.add_argument("--history", type=int, metavar="LIMIT", help="Show recent task history and exit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.health:
        try:
            _print_json(get_health(args.base_url))
            return 0
        except CliError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.task_id:
        try:
            _print_json(get_task(args.task_id, args.base_url))
            return 0
        except CliError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.history is not None:
        try:
            _print_json(list_tasks(args.base_url, args.history))
            return 0
        except CliError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.command:
        try:
            _print_json(_dispatch_command(args.command, args.base_url))
            return 0
        except CliError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return _interactive_loop(args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
