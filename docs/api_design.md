# API Design

## Purpose

The local API is the stable communication boundary between clients and the AI daemon. It is implemented with FastAPI and exposed only on localhost (port 8000 by default).

## API Principles

The API should be:

- local-only
- explicit about task state
- stable enough for future clients
- simple enough to debug with standard HTTP tooling

The terminal client is the primary consumer, but the same API supports future dashboards or editor integrations.

## Core Endpoints

### `GET /health`

Reports daemon health, service name, and version.

Response:

```json
{
  "status": "ok",
  "service": "ai-daemon",
  "version": "0.1.0"
}
```

### `POST /task`

Creates and executes a new task from a natural-language command.

Request:

```json
{
  "command": "create a fastapi project and push it to github",
  "cwd": "/home/user/projects"
}
```

Response:

```json
{
  "task_id": "task_001",
  "status": "completed",
  "success": true,
  "message": "Task completed successfully",
  "command": "create a fastapi project and push it to github",
  "cwd": "/home/user/projects",
  "steps": [
    {
      "description": "Create project directory",
      "role": "executor",
      "tool_name": "create_folder",
      "args": {"path": "demo-service"},
      "needs_retrieval": false,
      "requires_approval": false,
      "approval_category": null
    }
  ],
  "result": {},
  "approval_request": null
}
```

### `GET /tasks`

Lists completed tasks with optional pagination.

Query parameters:

- `limit` (int, 1–100, default 20)

### `GET /tasks/{task_id}`

Returns a single task by ID with full history, steps, and result.

### `GET /runtime`

Returns the current model runtime configuration, hardware detection, and per-role model selection.

Response:

```json
{
  "configured_runtime": "auto",
  "detected_ram_gb": 16.0,
  "cpu_cores": 8,
  "low_memory_threshold_gb": 12.0,
  "selected_runtime_by_role": {
    "intent": "ollama",
    "planning": "ollama",
    "coding": "ollama"
  },
  "issues": {}
}
```

### `POST /runtime`

Switches the model runtime (e.g., `ollama`, `airllm`, `auto`).

Request:

```json
{
  "runtime": "ollama"
}
```

### `GET /models`

Returns all configured models and their role assignments.

### `POST /models/roles`

Assigns a specific model to a role.

Request:

```json
{
  "role": "coding",
  "runtime": "ollama",
  "model_name": "qwen2.5-coder:1.5b"
}
```

### `GET /approvals/{approval_id}`

Returns a pending approval request by ID.

### `POST /approvals/{approval_id}`

Resolves an approval with a decision.

Request:

```json
{
  "token": "approval_token_abc",
  "decision": "approve"
}
```

### `GET /rollback`

Lists tasks that have rollback candidates (file snapshots).

Query parameters:

- `limit` (int, 1–100, default 20)

### `POST /rollback`

Rolls back a specific task step, reverting file changes.

Request:

```json
{
  "task_id": "task_001",
  "step_index": 2
}
```

## Internal Communication Model

The API layer remains thin. Endpoint handlers:

- validate input via Pydantic models
- delegate to the `ExecutionEngine` for task orchestration
- return structured responses

Endpoint handlers do not contain planning or execution logic directly.

## Task Status Shape

Task responses include:

- task ID
- current status (`completed`, `failed`, `pending_approval`, `cancelled`)
- success flag
- generated plan steps
- per-step results
- final summary
- approval request details when relevant

This allows the terminal client to show progress without re-implementing task logic.

## Security and Locality

The API is local-only. It is not exposed to remote clients by default. The daemon validates all requests and never treats client input as trusted shell commands. The tool engine mediates all system mutations.
