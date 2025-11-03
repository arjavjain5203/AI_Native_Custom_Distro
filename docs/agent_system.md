# Agent System

## Purpose

This document describes the multi-agent structure used in v1, the responsibilities of each agent, and how coordination works without turning the system into an unpredictable autonomous loop.

## Agent Design Principles

The platform uses multiple specialized agents because a single model trying to both reason and execute tends to be fragile. However, v1 intentionally limits the system to four agents with clear boundaries.

The design principles are:

- one agent, one main responsibility
- no agent executes tools directly except through the tool engine
- execution remains bounded by task state and step count
- plans are reviewed before sensitive work begins

## Planner Agent

The Planner Agent converts a natural language goal into a structured sequence of steps. It is responsible for:

- understanding user intent
- deciding whether the task is supported in v1
- selecting a high-level workflow
- producing an ordered execution plan

Planner output should be structured rather than freeform narrative. Each step should include:

- step description
- expected tool category
- risk level
- whether code retrieval is required

The planner does not execute commands.

## Executor Agent

The Executor Agent walks the approved plan. Its responsibilities are:

- select the correct tool for each step
- validate preconditions
- execute one step at a time
- record results and failure details
- stop when a risky step requires additional approval

The executor does not perform deep reasoning. It translates an approved plan into concrete tool operations.

## Coding Agent

The Coding Agent is responsible for file generation and bounded code modifications. It is only activated when the task involves code understanding or source changes.

Responsibilities:

- retrieve relevant code chunks through the retrieval layer
- reason about small and medium Python/FastAPI repositories
- generate new files when required
- modify existing files with targeted changes
- explain unsupported repository shapes when v1 limits are exceeded

The coding agent must not edit a repository blindly. Retrieval is required before modification.

## Analysis Agent

The Analysis Agent handles system and environment diagnostics. In v1 it is basic but useful. It can:

- explain why a tool setup failed
- inspect package installation state
- analyze command output
- provide simple system-level developer diagnostics

Examples include:

- confirming whether Python or Docker is installed
- interpreting a failing command in a setup workflow
- reporting missing dependencies

## Coordination Model

The standard coordination loop is:

1. receive the task
2. classify the intent
3. ask Planner Agent for a plan
4. request approval when needed
5. hand the plan to Executor Agent
6. invoke Coding Agent or Analysis Agent only when the current step requires them
7. record outcomes and finish the task

This keeps planning, execution, coding, and diagnostics separated while still allowing collaboration between agents.

## Example Task

For `add authentication to this fastapi project`:

1. Planner Agent produces a bounded code-modification plan
2. Executor Agent requests repository indexing if the project is not indexed
3. Coding Agent retrieves relevant files, proposes changes, and writes modifications through filesystem tools
4. Executor Agent records the outcome and returns a task summary

## Constraints in v1

The agent system does not aim for broad autonomy in v1. The following are explicitly out of scope:

- large swarms of specialized agents
- self-directed long-running research tasks
- cross-machine coordination
- unrestricted edits across very large repositories

The goal is predictable developer automation, not maximal agent complexity.
