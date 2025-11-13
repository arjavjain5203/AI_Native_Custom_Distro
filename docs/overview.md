# AI-Native Developer Operating Environment

## Purpose

AI-Native Developer Operating Environment is a Linux-based developer platform built on top of Arch Linux using `archiso`. It combines a custom operating system environment with a local AI orchestration layer so developers can perform common engineering tasks through a natural language terminal instead of manually chaining shell commands, code generation tools, and web workflows.

The system does not replace the Linux kernel or core userland. Linux remains the base platform. The AI layer sits above it as a local service that understands developer intent, plans work, invokes trusted tools, and coordinates local models through Ollama.

## Problem Statement

Modern development workflows are fragmented. A typical task such as creating a service and pushing it to GitHub requires multiple disconnected actions:

- create the project structure
- install dependencies
- configure local tooling
- initialize git
- create a remote repository
- push code
- verify the environment

Developers also lose time when modifying existing repositories because understanding the codebase, locating relevant files, and applying consistent changes is still mostly manual. Cloud-based assistants can reduce some friction, but they introduce privacy, cost, and connectivity constraints.

## High-Level Solution

This project provides a local-first developer environment with the following core elements:

- an AI daemon running as a `systemd` service
- a terminal-first interface for developer commands
- a multi-agent execution model for planning, code changes, and diagnostics
- a tool engine that mediates all file, git, package, and system operations
- Ollama for local model execution
- a memory and retrieval layer built with SQLite and FAISS

At a high level, the user types a natural language request into the AI terminal. The daemon classifies the task, chooses the correct model, builds an execution plan, asks for approval when needed, and then executes the plan through registered tools.

## Version 1 Focus

Version 1 is intentionally narrow so that the system is stable and demonstrable:

- primary interface: AI terminal
- operating system base: Arch Linux via `archiso`
- desktop environment: `i3`
- core workflows:
  - create a project and push it to GitHub
  - modify a small or medium existing codebase
  - install and verify developer tooling
- local models managed through Ollama
- code retrieval limited to small and medium projects

Voice interaction, richer dashboards, and a broad plugin ecosystem are future features, not v1 requirements.

## Build Philosophy

The platform is designed as a real implementation target, not a concept demo. Every major subsystem is constrained by practical choices:

- the daemon is local and Python-based
- execution goes through explicit tools, not freeform shell output from a model
- the ISO ships with runtime support but not bundled models
- model recommendations are hardware-aware and user-approved
- permissions are enforced before sensitive operations

This design keeps the system buildable while still demonstrating OS integration, AI orchestration, and developer automation.
