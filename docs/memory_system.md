# Memory System

## Purpose

This document defines the memory design for the platform. The memory layer stores structured runtime state, project context, and semantic search artifacts so the system can maintain continuity across tasks.

## Design Overview

The memory layer combines three storage components:

- **TaskHistoryStore** (SQLite) — structured, queryable data
- **VectorStore** (embeddings) — semantic retrieval for code understanding
- **WorkingMemoryStore** — ephemeral context for active sessions

These stores serve different purposes and should not be merged conceptually.

## TaskHistoryStore (`ai_core/memory/store.py`)

The SQLite-backed store handles all structured, persistent data:

- task history (command, plan steps, results, timestamps)
- user preferences
- project metadata
- permission decisions
- model role assignments

The store initializes its schema on first use and provides methods for:

- creating and retrieving tasks
- listing recent tasks with pagination
- storing and querying preferences

## VectorStore (`ai_core/memory/vector_store.py`)

The vector store handles semantic retrieval for code understanding. It is used when the system needs to:

- search semantically related code chunks
- locate files relevant to a requested feature
- retrieve implementation context before editing

The store manages embeddings through the `embeddings.py` module and maps vectors back to file paths and chunk identifiers.

### Indexing Pipeline

1. Scan the repository for supported file types
2. Chunk files into retrieval units
3. Generate embeddings
4. Store embeddings in the vector store
5. Store metadata in SQLite

### Retrieval Workflow

When the Coding Agent needs context:

1. Check whether the repository is indexed
2. Use the task description to query for relevant chunks
3. Supply retrieved context to the coding model
4. Map proposed changes back to real files

## WorkingMemoryStore (`ai_core/memory/working_memory.py`)

Working memory provides short-lived context for active task sessions:

- stores intermediate results during multi-step plans
- tracks per-session state (files viewed, decisions made)
- cleared after task completion

This prevents ephemeral task context from polluting the persistent stores.

## Memory Domains

### User Memory

User memory stores non-secret persistent preferences and environment context:

- preferred language and editor
- GitHub username
- active project roots
- model role overrides

### Task History

Task history records:

- raw user requests
- generated plans with step details
- approval events and decisions
- tool outcomes and artifacts
- errors and failure context
- timestamps

This helps with debugging, future task context, and operator visibility.

### Project Memory

Project memory stores repository-specific state:

- project path
- framework type
- indexed files
- last indexing time
- retrieval metadata

## What Must Not Be Stored

The memory system must not store secrets as plain data:

- GitHub personal access tokens
- passwords
- private keys

Sensitive credentials should be stored in environment variables (`.env`) or through an OS-backed secure mechanism, not in SQLite.

## Update Lifecycle

The memory layer is updated at specific points:

- when the user changes preferences or model roles
- when a task is created or completed
- when a repository is indexed
- when approval settings change
- when retrieval metadata is refreshed

These updates are explicit and deterministic. The platform does not depend on a model to decide how persistence works.

## Configuration

Memory settings are managed through `config.yaml`:

```yaml
memory:
  backend: "sqlite"
  database: "ai_core.db"
  vector_store: "faiss"
```

The database path can also be set via the `AI_OS_MEMORY_DB` environment variable.
