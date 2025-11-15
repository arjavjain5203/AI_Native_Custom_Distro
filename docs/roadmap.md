# Roadmap

## Purpose

This roadmap describes how to reach Version 1 from the current repository state. The project is currently planned as a solo build, so responsibilities are organized by workstream and phase rather than separate team members.

## Ownership Model

Version 1 assumes one primary developer owns:

- architecture and daemon implementation
- Arch packaging and `archiso` integration
- retrieval and code-understanding pipeline
- documentation and validation

If the project later grows into a team, the workstreams can be split, but v1 planning should assume sequential execution by one owner.

## Phase 1: Arch Environment Baseline

### Goal

Establish the Linux distribution baseline and package layout.

### Outputs

- confirm and clean the `archlive/` build base
- define required packages and service files
- finalize `i3` as the default desktop

### Acceptance Criteria

- the ISO build base is reproducible
- required runtime dependencies are identified

## Phase 2: AI Daemon and Local API

### Goal

Create the daemon skeleton and local FastAPI surface.

### Outputs

- daemon process structure
- local API endpoints
- task lifecycle model

### Acceptance Criteria

- tasks can be created and queried through the API
- health reporting works locally

## Phase 3: Terminal Client

### Goal

Build the primary user interface.

### Outputs

- terminal command entry flow
- task status display
- plan presentation and approval collection

### Acceptance Criteria

- a local user can submit a command and see task state changes

## Phase 4: Tool Registry and Permissions

### Goal

Introduce the safe execution layer.

### Outputs

- tool registry
- filesystem tools
- git tools
- permission manager

### Acceptance Criteria

- approved tool calls execute through the registry
- risky steps trigger confirmation

## Phase 5: GitHub Workflow

### Goal

Implement the first complete developer automation path.

### Outputs

- GitHub plugin
- PAT-based authentication flow
- repository creation support

### Acceptance Criteria

- the system can create a project, initialize git, create a GitHub repository, and push code

## Phase 6: Persistence and Memory

### Goal

Add structured state and task history.

### Outputs

- SQLite persistence
- user preferences
- task history
- permission state
- model assignments

### Acceptance Criteria

- task state survives process restarts where intended
- approvals and settings can be reused

## Phase 7: Code Indexing and Retrieval

### Goal

Add semantic code retrieval for existing repositories.

### Outputs

- repository scanner
- chunking pipeline
- FAISS index
- SQLite metadata mapping

### Acceptance Criteria

- a small or medium FastAPI project can be indexed and queried for relevant context

## Phase 8: Coding Workflow

### Goal

Enable bounded code modifications on indexed repositories.

### Outputs

- Coding Agent integration
- retrieval-grounded edits
- validation flow for modified files

### Acceptance Criteria

- the system can modify an existing supported project in response to a bounded feature request

## Phase 9: Environment Setup and Diagnostics

### Goal

Support developer environment setup tasks and basic analysis.

### Outputs

- `pacman` tool integration
- installation verification
- Analysis Agent basics

### Acceptance Criteria

- the system can install a developer tool and verify the setup

## Phase 10: ISO Integration and First-Boot Setup

### Goal

Turn the runtime into an integrated developer operating environment.

### Outputs

- daemon service included in the Arch image
- terminal configured by default
- first-boot hardware detection
- model recommendation and install flow

### Acceptance Criteria

- a fresh installed system can start the daemon and guide the user through model setup

## Phase 11: Stretch Work

### Goal

Add optional features if the core system is stable.

### Outputs

- Docker plugin
- minimal settings or status dashboard

### Acceptance Criteria

- stretch features do not block v1 delivery if unfinished

## Major Risks

The main delivery risks are:

- over-broad scope
- unstable code modification behavior
- unsafe command execution
- large-model resource constraints
- coupling too much logic into prompts instead of deterministic runtime code

The roadmap is ordered to reduce those risks by building the execution and safety layers before broad feature expansion.
