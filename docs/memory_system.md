# Memory System

## Purpose

This document defines the memory design for v1. The memory layer stores structured runtime state, project context, and semantic search artifacts so the system can maintain continuity across tasks.

## Design Overview

The memory layer combines two storage systems:

- SQLite for structured, queryable data
- FAISS for vector-based semantic retrieval

These stores serve different purposes and should not be merged conceptually.

## SQLite Responsibilities

SQLite stores data that needs strong structure and predictable updates, including:

- user profile
- task history
- project metadata
- indexed file metadata
- permission decisions
- model role assignments

Useful examples:

- preferred editor
- GitHub username
- last indexed repository path
- task status and timestamps
- whether the user always allows package installation prompts

## FAISS Responsibilities

FAISS stores vector embeddings for code retrieval. It is used when the system needs to:

- search semantically related code chunks
- locate files relevant to a requested feature
- retrieve implementation context before editing

FAISS should store chunk-level embeddings, while SQLite stores the metadata that maps each vector back to file path, symbol context, and repository identity.

## Memory Domains

### User Memory

User memory stores non-secret persistent preferences and environment context. Examples:

- preferred language
- editor preference
- GitHub username
- active project roots

### Task History

Task history records:

- raw user requests
- generated plans
- approval events
- tool outcomes
- errors

This helps with debugging, future task context, and operator visibility.

### Project Memory

Project memory stores repository-specific state such as:

- project path
- framework type
- indexed files
- last indexing time
- retrieval metadata

## What Must Not Be Stored

The memory system must not store secrets as plain data. In v1, this includes:

- GitHub personal access tokens
- passwords
- private keys

Sensitive credentials should be stored through an OS-backed secure mechanism rather than SQLite.

## Update Lifecycle

The memory layer is updated at specific points:

- when the user changes preferences or model roles
- when a task is created or completed
- when a repository is indexed
- when approval settings change
- when retrieval metadata is refreshed

These updates should be explicit and deterministic. The platform should not depend on a model to decide how persistence works.

## v1 Constraints

Version 1 uses memory for developer continuity, not for broad autonomous recall. The memory design is intentionally simple enough to remain debuggable while still supporting code retrieval and task tracking.
