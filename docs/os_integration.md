# OS Integration

## Purpose

This document explains how the platform integrates with Linux at the operating-system level while still treating Linux as the trusted base platform.

## Integration Model

AI-Native Developer Operating Environment is built on Arch Linux using `archiso`. The system does not alter the kernel. Instead, it adds an AI-native orchestration layer on top of standard Linux services and tools.

The central integration point is the AI daemon, which runs as a `systemd` service and interacts with the operating system through normal Linux mechanisms:

- filesystem operations
- process execution
- package management
- service management
- developer tooling

## systemd Service Design

The daemon should start automatically through a dedicated `systemd` unit. The service design should support:

- startup on boot
- restart on failure
- standard logging through journald
- clear dependency ordering when required

Because the AI layer is a long-running background service, `systemd` is the correct runtime manager for v1.

## Filesystem Interaction

The platform needs controlled access to the filesystem to:

- create and modify projects
- read existing repositories
- manage indexes and structured state
- write generated files

Filesystem actions must always flow through the tool engine so that path validation, approval checks, and task logging remain consistent.

## Process and Command Interaction

The platform interacts with processes for:

- running git commands
- installing packages through `pacman`
- invoking environment checks
- talking to Ollama

These actions must be explicit and auditable. The daemon should use structured subprocess calls where possible and should capture return codes and output for debugging.

## Arch Linux Integration

The repository already contains an `archiso` profile under `archlive/`. That profile is the current OS packaging base for the project. Version 1 will extend that base by adding:

- the AI daemon
- terminal client
- Ollama runtime dependencies
- configuration for the default `i3` environment
- first-boot setup and model recommendation flow

This means the distribution work is incremental. The project starts from an Arch image build pipeline that already exists in the repository rather than starting from a blank ISO definition.

## v1 Desktop Environment

Version 1 uses `i3` as the default lightweight environment. This keeps resource usage low and aligns with a developer-focused workflow. Supporting multiple desktop environments is a future concern and should not complicate the first release.

## Why OS Integration Matters

The project becomes substantially more useful once it can interact with the real system instead of behaving like a standalone chat application. OS integration enables:

- installation and verification of developer tools
- repository creation and modification using local paths
- package installation workflows
- process-level diagnostics

That is what moves the project from a generic AI assistant to an AI-native developer environment.
