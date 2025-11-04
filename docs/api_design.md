# API Design

## Purpose

The local API is the stable communication boundary between clients and the AI daemon. In v1 it is implemented with FastAPI and exposed only on localhost.

## API Principles

The API should be:

- local-only
- explicit about task state
- stable enough for future clients
- simple enough to debug with standard HTTP tooling

The terminal client is the primary consumer in v1, but the same API can later support a dashboard or editor integration.

## Core Endpoints

### `POST /tasks`

Creates a new task.

Example request:

```json
{
  "command": "create a fastapi project and push it to github",
  "cwd": "/home/user/projects",
  "context": {
    "project_name": "demo-service"
  }
}
```

Example response:

```json
{
  "task_id": "task_001",
  "status": "planning"
}
```

### `GET /tasks/{task_id}`

Returns current task status, generated plan, step logs, and final result summary.

### `POST /projects/index`

Indexes a repository for retrieval-based code understanding.

Example request:

```json
{
  "path": "/home/user/projects/demo-service"
}
```

### `GET /health`

Reports daemon health, database availability, Ollama availability, and high-level runtime readiness.

### `GET /models/recommendations`

Returns hardware-aware recommended models by role.

Example response:

```json
{
  "intent_model": "recommended-small-model",
  "planning_model": "recommended-reasoning-model",
  "coding_model": "recommended-coding-model"
}
```

### `POST /models/install`

Installs or assigns models after user approval.

### `GET /models/current`

Returns installed models, current role assignments, and whether each model is available.

### `POST /permissions/decision`

Accepts user responses to approval prompts, including one-time or persistent decisions.

## Internal Communication Model

The API layer should remain thin. Endpoint handlers should:

- validate input
- create or look up task state
- call the appropriate daemon subsystem
- return structured responses

Endpoint handlers should not contain planning or execution logic directly.

## Task Status Shape

Task responses should include:

- task ID
- current status
- generated plan
- current step
- per-step results
- final summary
- error details when relevant

This allows the terminal client to show progress without re-implementing task logic.

## Security and Locality

The API is local-only in v1. It should not be exposed to remote clients by default. Authentication can remain simple in v1 because the threat model assumes the local user owns the session, but the daemon must still validate requests and never treat client input as trusted shell commands.
