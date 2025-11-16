# Security

## Purpose

This document describes the safety and security model for v1, especially around command execution, permissions, and credential handling.

## Security Principles

The platform is powerful because it can modify files, install packages, and interact with external developer systems. That also makes it risky. The v1 security model is based on five rules:

- plans are shown before execution
- sensitive steps require explicit approval
- models never execute arbitrary shell directly
- tools enforce validation and permission boundaries
- secrets are stored separately from general memory

## Permission Model

Permissions are organized by action category rather than by every individual command. Relevant categories include:

- filesystem changes
- git operations
- GitHub operations
- package installation
- privileged system commands

The default v1 pattern is:

- approve the full plan once
- re-confirm risky or destructive steps
- allow users to persist category-level decisions

This keeps the product usable while still protecting the system.

## Safe Command Execution

The daemon should not accept raw shell text from the model and pass it to a shell unchecked. Instead:

- the model selects a tool
- the tool validates arguments
- the tool uses structured subprocess calls where possible
- the daemon records command results and errors

When a step requires elevated privileges, the system must make that visible before execution.

## Token Handling

GitHub integration in v1 uses a personal access token. That token must not be stored in:

- SQLite memory tables
- plaintext configuration files
- task logs

Instead, it should be placed in a secure OS-backed secret store or equivalent protected storage.

## Logging and Redaction

Logs are necessary for debugging, but they must avoid leaking sensitive data. The daemon should redact:

- tokens
- secrets
- private credential values

Logs should still preserve enough structure to explain what happened during a failed step.

## Threat Model for v1

Version 1 is a local developer system, not a multi-user server platform. The main security concerns are:

- unsafe command execution
- accidental destructive actions
- leaking credentials into logs or databases
- over-trusting model output

The design choices in the tool engine and permission model are meant to address exactly those risks.
