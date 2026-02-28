# System Design

## Purpose

This document describes the internal service design of the system, with a focus on the AI daemon, its components, and runtime interactions.

## Core Runtime

The central runtime component is a Python daemon. The daemon coordinates everything that happens after the user submits a request. It is not just a model wrapper — it is the platform controller.

The daemon is designed as a set of focused subsystems organized under the `ai_core/` package.

## Daemon Components

### API Server

The daemon exposes a local FastAPI service on localhost (`ai_core/daemon/app.py`). It accepts task creation requests, reports task status, exposes model management, handles approval decisions, and supports rollback. The `create_app()` factory function wires all subsystems together.

### Execution Engine

The execution engine (`ai_core/core/execution_engine.py`) is the central orchestrator. It manages the full task lifecycle:

- receives a command and working directory
- runs intent classification through the Orchestrator
- dispatches to the appropriate agent via the Model Router
- coordinates approval flow for risky steps
- delegates step execution to the StepRunner
- records outcomes in task history
- supports approval resolution for pending tasks

### Step Runner

The step runner (`ai_core/core/step_runner.py`) executes individual plan steps:

- dispatches tool calls through the ToolRegistry
- invokes the Coding Agent when steps require code retrieval
- invokes the Analysis Agent for diagnostic steps
- manages rollback snapshots for file modifications
- captures per-step outcomes and error context

### Agent Coordinator

The Orchestrator (`ai_core/models/orchestrator.py`) decides which agent should handle a task. It classifies input into:

- `planning` — general project and workflow tasks
- `coding` — code generation and modification
- `analysis` — diagnostics and environment checks
- `system` — system-level operations

The classification also determines the execution mode (`conversation` vs `execution`) and confidence level.

### Tool Registry

The registry (`ai_core/tools/registry.py`) maps structured tool calls to concrete implementations. It validates tool names, argument schemas, and permission categories before execution. Tools are registered at startup through `register_tools.py`.

Currently registered tool families:

- Filesystem tools (create, read, write, update, list)
- Git tools (init, add, commit, push, branch, clone, status)
- GitHub tools (create repository, push file contents)
- Shell tools (safe subprocess execution)
- System tools (system information, package management)
- MCP tools (Model Context Protocol integrations)

### Approval Store

The approval store (`ai_core/core/approvals.py`) manages pending approval requests. When a plan step requires user confirmation, the execution engine creates an approval token and pauses execution until the user resolves it.

### Rollback Manager

The rollback manager (`ai_core/core/rollback.py`) provides undo capability:

- snapshots file contents before modification
- tracks which task and step modified each file
- supports reverting changes from any completed task
- exposes rollback candidates through the API

### Model Manager

The model manager (`ai_core/models/manager.py`) owns:

- installed model inventory
- role assignments (`intent`, `planning`, `coding`, `analysis`, `orchestrator`)
- hardware detection (RAM, CPU cores)
- runtime switching between Ollama and AirLLM
- model recommendations based on system resources
- low-memory threshold configuration

### Session Manager

The session manager (`ai_core/core/session.py`) tracks active sessions and maintains context across related task interactions.

### Persistence Layer

Persistence combines SQLite and vector embeddings:

- `TaskHistoryStore` (`ai_core/memory/store.py`) — structured task history, user preferences
- `VectorStore` (`ai_core/memory/vector_store.py`) — semantic embeddings for code retrieval
- `WorkingMemoryStore` (`ai_core/memory/working_memory.py`) — ephemeral context for active sessions

## Service Interaction Model

The daemon interacts with other runtime components through explicit interfaces:

- FastAPI endpoint handlers delegate to the ExecutionEngine
- the ExecutionEngine asks the Orchestrator to classify the task
- the ModelRouter resolves classification to a concrete model selection
- agents request model inference through the ModelManager
- Executor and Coding agents call tools through the ToolRegistry
- tools return structured results that are written to SQLite and surfaced to the client
- the RollbackManager snapshots files before modifications

This structure keeps the system testable and avoids direct coupling between API handlers, models, and shell operations.

## Logging and Observability

The daemon writes structured logs that capture:

- task IDs
- agent transitions
- tool execution start and stop events
- permission prompts
- model selection decisions
- failure details

Task-local logs are useful for the terminal client. System-level logs are also emitted to standard output for inspection through standard Linux tooling.

## Failure Handling

The system design assumes failures are normal:

- commands can fail
- models can be missing or unreachable
- permissions can be denied
- repositories can be unsupported
- network-dependent actions can partially complete
- Ollama may not be running

The daemon fails safely and explicitly. A failed step stops dependent execution, records context, and returns a useful error. The Planner Agent includes rule-based fallback planning so basic commands work even without a running model.

## Current Implementation Status

The repository contains the complete daemon, API, agent system, tool engine, model layer, and memory layer under `ai_core/`. Top-level directories (`daemon/`, `agents/`, `models/`, `memory/`, `plugins/`, `interfaces/`) provide clean public re-exports. The `archlive/` directory contains the Arch ISO build profile for distribution packaging.
