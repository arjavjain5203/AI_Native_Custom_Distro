# Roadmap

## Purpose

This roadmap describes the project's development phases, their current status, and what remains for a complete Version 1 release.

## Phase Overview

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Arch Environment Baseline | ✅ Complete | ISO build, package layout, i3 desktop |
| 2. AI Daemon and Local API | ✅ Complete | FastAPI daemon, task lifecycle, health API |
| 3. Terminal Client | ✅ Complete | CLI command flow, plan approval, history |
| 4. Tool Registry and Permissions | ✅ Complete | Permission-gated tool execution, registry |
| 5. GitHub Workflow | ✅ Complete | Repo creation, PAT auth, push |
| 6. Persistence and Memory | ✅ Complete | SQLite history, preferences, working memory |
| 7. Code Indexing and Retrieval | ✅ Complete | Vector store, chunking, semantic retrieval |
| 8. Coding Workflow | ✅ Complete | Retrieval-grounded code editing |
| 9. Environment Setup and Diagnostics | 🟡 In Progress | Package management, Analysis Agent |
| 10. ISO Integration and First-Boot | 🟡 In Progress | Daemon service, model recommendation |
| 11. Stretch Work | 📋 Planned | Docker plugin, dashboard |

---

## Phase 1: Arch Environment Baseline ✅

### Goal

Establish the Linux distribution baseline and package layout.

### Outputs

- `archlive/` build base confirmed and cleaned
- required packages and service files defined
- `i3` finalized as the default desktop

### Status

Complete. The ISO builds reproducibly and ships with the correct runtime dependencies.

---

## Phase 2: AI Daemon and Local API ✅

### Goal

Create the daemon skeleton and local FastAPI surface.

### Outputs

- daemon process structure (`ai_core/daemon/`)
- local API endpoints (`POST /task`, `GET /tasks`, `GET /health`, etc.)
- task lifecycle model with full state machine
- execution engine with step-by-step plan execution

### Status

Complete. The daemon runs, creates tasks, routes to agents, and returns structured results. Includes runtime management, model configuration, approval flow, and rollback endpoints.

---

## Phase 3: Terminal Client ✅

### Goal

Build the primary user interface.

### Outputs

- terminal command entry flow (`ai_core/cli/`)
- task status display
- plan presentation and approval collection
- history viewing (`--history`)
- health check (`--health`)

### Status

Complete. Users can submit natural-language commands, view plans, approve execution, and review task history.

---

## Phase 4: Tool Registry and Permissions ✅

### Goal

Introduce the safe execution layer.

### Outputs

- tool registry (`ai_core/tools/registry.py`)
- filesystem tools (`filesystem.py`)
- git tools (`git_tools.py`)
- shell tools (`shell.py`)
- system tools (`system_tools.py`)
- MCP tools (`mcp_tools.py`)
- permission manager with category-based policies
- `permissions.json` configuration

### Status

Complete. All tool families are registered. Risky steps trigger confirmation. Rollback manager snapshots files before modification.

---

## Phase 5: GitHub Workflow ✅

### Goal

Implement the first complete developer automation path.

### Outputs

- GitHub tools (`github_tools.py`)
- GitHub plugin (`plugins/github_plugin.py`)
- PAT-based authentication flow
- repository creation and file push support

### Status

Complete. The system can create a project, initialize git, create a GitHub repository, and push code.

---

## Phase 6: Persistence and Memory ✅

### Goal

Add structured state and task history.

### Outputs

- SQLite persistence (`ai_core/memory/store.py`)
- task history with full step detail
- user preferences
- permission state
- model assignments
- working memory for active sessions (`working_memory.py`)

### Status

Complete. Task state survives process restarts. Approvals, preferences, and model settings persist.

---

## Phase 7: Code Indexing and Retrieval ✅

### Goal

Add semantic code retrieval for existing repositories.

### Outputs

- vector store (`ai_core/memory/vector_store.py`)
- embeddings pipeline (`embeddings.py`)
- semantic search for code chunks
- SQLite metadata mapping

### Status

Complete. Repositories can be indexed and queried for relevant context during code modification tasks.

---

## Phase 8: Coding Workflow ✅

### Goal

Enable bounded code modifications on indexed repositories.

### Outputs

- Coding Agent integration (`ai_core/agents/coding.py`)
- retrieval-grounded edits
- validation flow for modified files
- rollback support for file changes

### Status

Complete. The system can modify existing projects in response to bounded feature requests.

---

## Phase 9: Environment Setup and Diagnostics 🟡

### Goal

Support developer environment setup tasks and basic analysis.

### Outputs

- `pacman` tool integration
- installation verification
- Analysis Agent basics (`ai_core/agents/analysis.py`)
- system information tools

### Remaining Work

- deeper diagnostic workflows
- broader package manager support
- environment troubleshooting flows

---

## Phase 10: ISO Integration and First-Boot Setup 🟡

### Goal

Turn the runtime into an integrated developer operating environment.

### Outputs

- daemon service included in the Arch image
- terminal configured by default
- first-boot hardware detection
- model recommendation and install flow

### Remaining Work

- systemd unit file finalization
- first-boot wizard
- model recommendation UI in terminal
- ISO testing with full runtime

---

## Phase 11: Stretch Work 📋

### Goal

Add optional features if the core system is stable.

### Outputs

- Docker plugin (implemented: `plugins/docker_plugin.py`)
- Voice interface placeholder (implemented: `interfaces/voice.py`)
- Minimal settings or status dashboard

### Status

Docker plugin is implemented. Voice interface has a placeholder structure. Dashboard is planned.

---

## Major Risks

The main delivery risks are:

- over-broad scope
- unstable code modification behavior
- unsafe command execution
- large-model resource constraints
- coupling too much logic into prompts instead of deterministic runtime code

The roadmap is ordered to reduce those risks by building the execution and safety layers before broad feature expansion.
