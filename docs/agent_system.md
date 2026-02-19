# Agent System

## Purpose

This document describes the multi-agent structure, the responsibilities of each agent, and how coordination works without turning the system into an unpredictable autonomous loop.

## Agent Design Principles

The platform uses multiple specialized agents because a single model trying to both reason and execute tends to be fragile. The design principles are:

- one agent, one main responsibility
- no agent executes tools directly except through the tool engine
- execution remains bounded by task state and step count
- plans are reviewed before sensitive work begins
- rule-based fallbacks ensure the system works without a running model

## Planner Agent (`ai_core/agents/planner.py`)

The Planner Agent converts a natural-language goal into a structured sequence of `PlanStep` objects. It is responsible for:

- understanding user intent
- deciding whether the task is supported
- selecting a high-level workflow
- producing an ordered execution plan

### Planning Pipeline

1. The planner builds a structured prompt from the user command
2. It calls the planning model via the Model Manager
3. The response is parsed as a JSON array of plan steps
4. Each step is validated against the allowed tool set

### Fallback Planning

If the model is unavailable or returns invalid output, the planner falls back to rule-based pattern matching for common commands:

- `create folder <path>` → `create_folder` tool
- `create file <path>` → `create_file` tool
- `read file <path>` → `read_file` tool
- `git init` → `git_init` tool
- `git commit <message>` → `git_commit` tool
- `clone repo <url>` → `clone_repo` tool
- `push changes` → `push_changes` tool (requires approval)
- `install package <name>` → `pacman_install` tool (requires approval)
- Coding-related requests → `coding_pipeline` tool
- Analysis-related requests → `analysis_pipeline` tool

### Plan Step Structure

Each step includes:

- `description` — human-readable step summary
- `role` — executor, coding, or analysis
- `tool_name` — the tool to invoke
- `args` — tool arguments
- `needs_retrieval` — whether code context is required
- `requires_approval` — whether user confirmation is needed
- `approval_category` — risk category (git_push, package_install, etc.)

## Executor Agent (`ai_core/agents/executor.py`)

The Executor Agent walks the approved plan. Its responsibilities are:

- select the correct tool for each step
- validate preconditions
- execute one step at a time through the tool registry
- record results and failure details
- stop when a risky step requires additional approval

The executor does not perform deep reasoning. It translates an approved plan into concrete tool operations.

## Coding Agent (`ai_core/agents/coding.py`)

The Coding Agent is responsible for file generation and bounded code modifications. It is activated when the task involves code understanding or source changes.

Responsibilities:

- retrieve relevant code chunks through the VectorStore
- reason about repository structure and dependencies
- generate new files when required
- modify existing files with targeted changes
- validate proposed changes against the codebase
- explain unsupported repository shapes when limits are exceeded

The Coding Agent uses the coding model (`qwen2.5-coder:1.5b` by default) and requires retrieval context before making modifications.

## Analysis Agent (`ai_core/agents/analysis.py`)

The Analysis Agent handles system and environment diagnostics:

- explain why a tool setup failed
- inspect package installation state
- analyze command output and error messages
- provide system-level developer diagnostics
- run environment health checks

Examples:

- confirming whether Python or Docker is installed
- interpreting a failing command in a setup workflow
- reporting missing dependencies
- explaining error tracebacks

## Coordination Model

The coordination is managed by the Execution Engine (`ai_core/core/execution_engine.py`) and Step Runner (`ai_core/core/step_runner.py`):

1. Execution Engine receives the task
2. Orchestrator classifies the intent and selects an agent
3. Planner Agent generates a structured plan
4. Execution Engine checks for steps requiring approval
5. Step Runner executes the plan step by step
6. Coding Agent is invoked when a step has `needs_retrieval=True`
7. Analysis Agent is invoked when a step uses `analysis_pipeline`
8. Tool Registry dispatches tool calls
9. Rollback Manager snapshots files before modification
10. Outcomes are recorded in TaskHistoryStore

This keeps planning, execution, coding, and diagnostics separated while still allowing collaboration between agents.

## Example Task

For `add authentication to this fastapi project`:

1. Orchestrator classifies as `coding` task type
2. Planner Agent produces a bounded code-modification plan
3. Coding Agent retrieves relevant files from the vector store
4. Coding Agent proposes changes grounded in actual codebase context
5. Step Runner applies changes through filesystem tools
6. Rollback Manager snapshots modified files
7. Execution Engine records the outcome and returns a task summary

## Constraints

The agent system does not aim for broad autonomy. The following are explicitly out of scope:

- large swarms of specialized agents
- self-directed long-running research tasks
- cross-machine coordination
- unrestricted edits across very large repositories

The goal is predictable developer automation, not maximal agent complexity.
