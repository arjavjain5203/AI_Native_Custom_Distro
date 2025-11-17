# System Design

## Purpose

This document describes the internal service design of the v1 system, with a focus on the AI daemon, its components, and runtime interactions.

## Core Runtime

The central runtime component is a Python daemon running as a `systemd` service. The daemon is responsible for coordinating everything that happens after the user submits a request. It is not just a model wrapper. It is the platform controller.

The daemon should be designed as a set of focused subsystems rather than one large script.

## Daemon Components

### API Server

The daemon exposes a local FastAPI service on localhost. It accepts task creation requests, reports task status, exposes model recommendations, and receives permission decisions.

### Task Manager

The task manager creates and tracks task lifecycle state:

- created
- planning
- awaiting_approval
- running
- completed
- failed
- cancelled

Each task keeps metadata such as request text, working directory, generated plan, step results, timestamps, and failure context.

### Agent Coordinator

The coordinator decides which agent should act next. It also enforces the handoff order:

- planner before executor
- executor before coding if code access is required
- analysis agent when environment verification or diagnosis is needed

### Tool Registry

The registry maps structured tool calls to concrete implementations. It validates tool names, argument schemas, permission categories, and expected outputs before execution.

### Permission Manager

The permission manager enforces the plan-first approval model. It decides whether the user must confirm a full plan, a sensitive step, or a category-specific persistent permission.

### Model Manager

The model manager owns:

- installed model inventory
- role assignments such as `intent_model`, `planning_model`, and `coding_model`
- model startup and teardown
- hardware-based recommendations

### Persistence Layer

Persistence combines SQLite and FAISS. SQLite stores structured state. FAISS stores embeddings used for semantic retrieval.

## Service Interaction Model

The daemon interacts with other runtime components through explicit interfaces:

- FastAPI endpoint handlers submit work to the task manager
- the task manager asks the agent coordinator to progress a task
- agents request model inference through the model manager
- executor and coding agents call tools through the tool registry
- tools return structured results that are written to SQLite and surfaced to the client

This structure keeps the system testable and avoids direct coupling between API handlers, models, and shell operations.

## Logging and Observability

The daemon should write structured logs that capture:

- task IDs
- agent transitions
- tool execution start and stop events
- permission prompts
- model selection decisions
- failure details

Task-local logs are useful for the terminal client. System-level logs should also be emitted to standard output or journald so operators can inspect the daemon through standard Linux tooling.

## Failure Handling

The system design assumes failures are normal:

- commands can fail
- models can be missing
- permissions can be denied
- repositories can be unsupported
- network-dependent actions can partially complete

The daemon should fail safely and explicitly. A failed step should stop dependent execution, record context, and return a useful error rather than silently continuing with invalid state.

## Current Repo Alignment

The repository already contains an `archiso` base under `archlive/`, but it does not yet contain the daemon, API, or agent implementation. This document therefore describes the target internal design that will be added on top of the existing distribution build base.
