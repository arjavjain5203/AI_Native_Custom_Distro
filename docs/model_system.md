# Model System

## Purpose

This document describes how v1 uses Ollama to manage local models, how models are selected for different tasks, and how lifecycle management works at installation time and during runtime.

## Ollama as the Runtime

Ollama is the local model runtime for v1. It provides a practical way to:

- install models on demand
- run models locally without building a custom inference stack
- switch between multiple model roles
- keep the system local-first and hardware-aware

The platform depends on Ollama rather than embedding model execution logic directly into the daemon.

## Model Roles

Version 1 uses role-based model assignment instead of hard-coding a single model for everything.

The required roles are:

- `intent_model` for task classification
- `planning_model` for step generation
- `coding_model` for code generation and modification

This design allows the installer and runtime settings to select different concrete models on different hardware while preserving a stable orchestration model.

## Model Routing

The daemon uses rule-based routing:

- simple task classification uses `intent_model`
- plan generation uses `planning_model`
- code understanding and modification use `coding_model`
- environment diagnostics may use the planning or coding model depending on context

Routing is decided by the daemon, not by the models themselves.

## Installation-Time Recommendation Flow

Models are not bundled in the ISO. Instead, during setup or first boot the platform:

1. detects RAM, CPU, and available disk space
2. recommends suitable models for each role
3. lets the user accept the defaults or override them
4. downloads models through Ollama only after confirmation

This prevents unnecessary storage usage and keeps the ISO manageable.

## Runtime Lifecycle

The model manager must support:

- checking whether a role has an assigned model
- detecting whether the model is already installed
- loading a model when a task requires it
- releasing resources when heavy models are idle
- changing model assignments after installation

The lifecycle goal is practical resource use on developer hardware, not always-on multi-model residency.

## Configuration Requirements

The system should persist:

- installed models
- role assignments
- recommendation history
- user overrides

Configuration belongs in structured settings rather than prompts so the daemon can route work consistently.

## Failure Modes

Common model-related failures include:

- model not installed
- insufficient system resources
- Ollama not running
- user-selected model unsuitable for the task

The daemon should surface these conditions clearly and give corrective actions, such as installing a missing model or selecting a smaller one.

## v1 Boundaries

Version 1 does not attempt to:

- train models
- benchmark every available model family
- support fully automatic model replacement without user awareness
- maintain many simultaneously loaded large models

The focus is stable local execution with configurable model roles.
