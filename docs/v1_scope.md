# Version 1 Scope

## Purpose

This document defines what Version 1 includes, what it deliberately leaves out, and what counts as success for the first release.

## Included in v1

### Core Platform

- Arch Linux distribution built with `archiso`
- `i3` as the default lightweight desktop
- AI daemon running as a `systemd` service
- terminal-first user interface
- local FastAPI API surface
- Ollama integration for local model execution

### Agent System

- Planner Agent
- Executor Agent
- Coding Agent
- Analysis Agent with basic diagnostics

### Tooling

- filesystem operations
- git operations
- GitHub integration
- `pacman` integration

### Codebase Understanding

- indexing for small and medium repositories
- SQLite metadata store
- FAISS vector retrieval
- bounded code modifications for Python/FastAPI projects

### Installation and Configuration

- hardware detection
- recommended models by role
- user override of model selection
- post-install model download through Ollama

## Must-Work Demo Workflows

Version 1 must reliably support:

1. project creation plus GitHub integration
2. codebase modification for a supported repository
3. development environment setup and verification

## Limitations in v1

The following are explicitly limited or excluded:

- large monorepos
- broad multi-language repository support
- voice interface as a core feature
- heavy GUI or dashboard-first workflow
- bundled models inside the ISO
- guaranteed Docker support
- large-scale distributed agent systems

## Success Criteria

Version 1 is successful if a developer can install the environment, configure models, create or modify a supported project through the AI terminal, and complete real developer tasks locally with approval-controlled execution.
