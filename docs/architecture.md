# Architecture

## Purpose

This document explains the full system architecture for AI-Native Developer Operating Environment, how the layers fit together, and how data moves through the platform during a request.

## Layered Architecture

The v1 architecture is organized into six layers:

```text
User
  |
  v
AI Developer Terminal
  |
  v
Local API Layer
  |
  v
AI Daemon
  |
  +--> Agent System
  |      |- Planner Agent
  |      |- Executor Agent
  |      |- Coding Agent
  |      `- Analysis Agent
  |
  +--> Tool Engine
  |      |- Filesystem tools
  |      |- Git tools
  |      |- GitHub tools
  |      `- Package manager tools
  |
  +--> Model Manager
  |      |- intent model
  |      |- planning model
  |      `- coding model
  |
  +--> Memory Layer
         |- SQLite
         `- FAISS
  |
  v
Linux OS + Ollama Runtime
```

## Layer Responsibilities

### Interface Layer

The primary interface in v1 is the AI terminal. It sends user commands to the local API, displays proposed plans, requests approvals, and streams task progress. Future versions may add voice and richer graphical controls, but the terminal is the stable first client.

### Local API Layer

The API is a localhost-only boundary around the daemon. It standardizes communication between clients and the orchestration layer and simplifies future integrations such as a dashboard or editor plugin.

### AI Daemon

The daemon is the system coordinator. It receives requests, creates task state, loads configuration, routes work to agents, checks permissions, logs progress, and returns results.

### Agent System

Agents are separated by responsibility:

- Planner Agent decomposes the task
- Executor Agent maps approved plan steps to tools
- Coding Agent handles code generation and bounded code edits
- Analysis Agent handles environment diagnostics and error explanation

### Tool Engine

The tool engine is the only way the system can mutate files, run commands, or access external systems. This prevents the model from directly generating unsafe shell operations.

### Model and Memory Layers

Ollama provides local model execution. SQLite and FAISS provide persistent state, task history, project metadata, and semantic retrieval for code understanding.

## End-to-End Data Flow

The standard request flow in v1 is:

1. The user enters a natural language request into the AI terminal.
2. The terminal calls `POST /tasks` on the local API.
3. The daemon stores initial task state and runs intent classification.
4. The model router selects the appropriate planning model.
5. The Planner Agent generates a structured plan.
6. The terminal displays the plan and collects approval.
7. The Executor Agent walks the plan one step at a time.
8. If a step requires code understanding, the Coding Agent retrieves relevant files from FAISS-backed indexes and proposes changes.
9. The tool engine validates the step, checks permissions, and executes the corresponding tool.
10. Results are written to task history and returned to the client.

## Example Workflow

For the command `create a fastapi project and push it to github`, the high-level path is:

- intent model identifies a project generation workflow
- planning model generates steps for project creation, dependency setup, git initialization, repository creation, and push
- terminal asks the user to approve the plan
- filesystem and git tools create the local project
- GitHub plugin creates the remote repository
- git tools push the repository
- task history is stored in SQLite

## Architectural Boundaries

The architecture deliberately excludes the following from v1:

- direct model-generated shell execution without a tool layer
- large distributed agent systems
- support for arbitrary large repositories
- voice-first interaction
- mandatory Docker workflows

Those boundaries keep the first release stable and implementable.
