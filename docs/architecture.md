# Architecture

## Purpose

This document explains the full system architecture for AI-Native Developer Operating Environment, how the layers fit together, and how data moves through the platform during a request.

## Layered Architecture

The architecture is organized into six layers:

```text
User
  │
  ▼
AI Developer Terminal (CLI)
  │
  ▼
Local FastAPI Daemon (port 8000)
  │
  ├──▸ Execution Engine
  │     ├─ Task lifecycle management
  │     ├─ Approval flow coordination
  │     └─ Step-by-step plan execution
  │
  ├──▸ Agent System
  │     ├─ Planner Agent    → decomposes user requests into structured plans
  │     ├─ Executor Agent   → maps plan steps to tool invocations
  │     ├─ Coding Agent     → code generation and modification with retrieval
  │     └─ Analysis Agent   → diagnostics and error explanation
  │
  ├──▸ Tool Engine
  │     ├─ Tool Registry    → validates and dispatches tool calls
  │     ├─ Filesystem tools → create, read, write, update, list
  │     ├─ Git tools        → init, add, commit, push, branch, clone
  │     ├─ GitHub tools     → repository creation, file push
  │     ├─ Shell tools      → safe subprocess execution
  │     ├─ System tools     → system info and package management
  │     └─ MCP tools        → Model Context Protocol integrations
  │
  ├──▸ Model Layer
  │     ├─ Orchestrator     → classifies tasks and selects agents
  │     ├─ Model Router     → resolves task type to model/provider
  │     ├─ Model Manager    → hardware detection, runtime switching
  │     ├─ Ollama Client    → HTTP client for local Ollama API
  │     └─ AirLLM Client    → alternative runtime for constrained hardware
  │
  └──▸ Memory Layer
        ├─ TaskHistoryStore   → SQLite-backed task and command history
        ├─ VectorStore        → semantic code retrieval with embeddings
        └─ WorkingMemoryStore → short-lived context for active sessions
  │
  ▼
Linux OS + Ollama Runtime
```

## Layer Responsibilities

### Interface Layer

The primary interface is the AI Developer Terminal (`ai_core/cli/`). It sends user commands to the local API, displays proposed plans, requests approvals, and streams task progress. A secondary launcher script (`ai-os`) provides quick access. Future versions may add voice and graphical interfaces through the `interfaces/` package.

### Local API Layer

The API is a localhost-only FastAPI service (`ai_core/daemon/app.py`). It exposes endpoints for task creation, task history, model management, runtime configuration, approval flow, and rollback. The API standardizes communication between clients and the execution engine.

### Execution Engine

The execution engine (`ai_core/core/execution_engine.py`) is the central coordinator. It receives task requests, creates task state, runs intent classification through the orchestrator, dispatches work to agents, manages approval flow, records results, and supports rollback of file changes.

### Agent System

Agents are separated by responsibility and live in `ai_core/agents/`:

- **Planner Agent** (`planner.py`) — decomposes natural-language requests into structured `PlanStep` objects. Uses LLM-based planning with a rule-based fallback for common commands.
- **Executor Agent** (`executor.py`) — maps approved plan steps to concrete tool invocations.
- **Coding Agent** (`coding.py`) — handles code generation and bounded code modifications. Uses retrieval-grounded context from the vector store to edit the correct files.
- **Analysis Agent** (`analysis.py`) — runs environment diagnostics and explains errors.

### Tool Engine

The tool engine (`ai_core/tools/`) is the only way the system can mutate files, run commands, or access external services. All tools are registered with the `ToolRegistry` (`registry.py`) and dispatched through `register_tools.py`. Available tool families:

- `filesystem.py` — create, read, write, update files and directories
- `git_tools.py` — git init, add, commit, push, branch, clone
- `github_tools.py` — repository creation, file push via GitHub API
- `shell.py` — safe subprocess execution with argument validation
- `system_tools.py` — system information and package management
- `mcp_tools.py` — Model Context Protocol tool integration

### Model Layer

The model layer (`ai_core/models/`) manages all LLM interactions:

- **Orchestrator** (`orchestrator.py`) — classifies user input into task types (planning, coding, analysis, system) and selects the appropriate agent. Uses the orchestrator model with a keyword-based fallback.
- **Model Router** (`router.py`) — resolves a classification decision into a concrete `ModelSelection` specifying the provider, model name, and agent role.
- **Model Manager** (`manager.py`) — manages model inventory, role assignments (intent, planning, coding, analysis), hardware detection, and runtime switching between Ollama and AirLLM.
- **Ollama Client** (`ollama.py`) — HTTP client for the local Ollama REST API with streaming support.
- **AirLLM Client** (`airllm_client.py`) — alternative runtime for memory-constrained hardware.

Model roles:

| Role | Default Model | Purpose |
|------|--------------|---------|
| `intent` | `phi3:mini` | Task classification |
| `planning` | `gemma:2b` | Plan generation |
| `coding` | `qwen2.5-coder:1.5b` | Code generation/modification |
| `analysis` | `gemma:2b` | Diagnostics and explanation |
| `orchestrator` | `phi3:mini` | Input classification and agent selection |

### Memory Layer

The memory layer (`ai_core/memory/`) provides persistent and ephemeral state:

- **TaskHistoryStore** (`store.py`) — SQLite-backed storage for task history, user preferences, permission decisions, and model assignments.
- **VectorStore** (`vector_store.py`) — semantic code retrieval using embeddings for retrieval-augmented code editing.
- **WorkingMemoryStore** (`working_memory.py`) — short-lived context for active task sessions, cleared after task completion.

### Core Infrastructure

The `ai_core/core/` package provides shared infrastructure:

- **ExecutionEngine** (`execution_engine.py`) — orchestrates the full task lifecycle
- **StepRunner** (`step_runner.py`) — executes individual plan steps with tool dispatch
- **ApprovalStore** (`approvals.py`) — manages pending approval tokens and decisions
- **RollbackManager** (`rollback.py`) — snapshots files before modification and supports undo
- **SessionManager** (`session.py`) — tracks active sessions and context
- **FileVerifier** (`file_verifier.py`) — validates file operations before execution
- **ModelProfiles** (`model_profiles.py`) — hardware-aware model recommendations
- **Config** (`config.py`) — environment-based configuration for all subsystems

## End-to-End Data Flow

The standard request flow is:

1. The user enters a natural-language request into the AI terminal.
2. The terminal calls `POST /task` on the local API.
3. The execution engine stores initial task state.
4. The orchestrator classifies the input and selects the appropriate agent.
5. The model router resolves the classification to a concrete model.
6. The Planner Agent generates a structured plan (LLM-based or rule-based fallback).
7. The execution engine checks for steps requiring approval.
8. If approval is needed, the terminal displays the plan and collects the user's decision.
9. The step runner walks the plan one step at a time.
10. If a step requires code understanding, the Coding Agent retrieves relevant files from the vector store and proposes changes.
11. The tool registry validates the step, checks permissions, and executes the corresponding tool.
12. The rollback manager snapshots files before modification.
13. Results are written to task history and returned to the client.

## Example Workflow

For the command `create a fastapi project and push it to github`, the flow is:

- Orchestrator classifies this as a `planning` task type with `planning` agent
- Planner Agent generates steps for project creation, dependency setup, git initialization, repository creation, and push
- Terminal asks the user to approve the plan
- Filesystem tools create the local project structure
- Git tools initialize the repository and make the first commit
- GitHub tools create the remote repository via the GitHub API
- Git tools push the repository
- Task history is stored in SQLite
- Rollback snapshots are available for file changes

## Plugin System

External integrations are implemented as plugins (`plugins/`):

- **GitHub Plugin** (`github_plugin.py`) — wraps GitHub API tools for repository management
- **Docker Plugin** (`docker_plugin.py`) — container lifecycle management (build, run, stop, list)

Plugins register their tools with the tool registry so agents can invoke them during plan execution.

## Architectural Boundaries

The architecture deliberately excludes the following:

- direct model-generated shell execution without a tool layer
- large distributed agent systems
- support for arbitrary large repositories
- voice-first interaction (planned for future versions)
- mandatory Docker workflows

Those boundaries keep the system stable and implementable.
