# Security

## Purpose

This document describes the safety and security model, especially around command execution, permissions, and credential handling.

## Security Principles

The platform is powerful because it can modify files, install packages, and interact with external developer systems. The security model is based on five rules:

- plans are shown before execution
- sensitive steps require explicit approval
- models never execute arbitrary shell directly
- tools enforce validation and permission boundaries
- secrets are stored separately from general memory

## Permission Model

Permissions are defined in `permissions.json` and organized by tool and category.

### Per-Tool Policies

Each tool has a policy that controls execution:

| Policy | Behavior |
|--------|----------|
| `allow` | Execute without confirmation (safe, read-only operations) |
| `prompt` | Show the operation and require user approval |
| `deny` | Block execution entirely |

### Category Defaults

Tools are grouped into categories with default policies:

| Category | Default | Examples |
|----------|---------|----------|
| `read_only` | `allow` | `read_file`, `list_directory`, `git_status` |
| `write` | `prompt` | `write_file`, `git_commit`, `create_repo` |
| `destructive` | `prompt` | `delete_file`, `git_push` |
| `network` | `prompt` | `create_repo`, `push_file_contents` |
| `system` | `deny` | `install_package` |

### Approval Flow

When a plan step requires approval:

1. The execution engine creates an approval token
2. The terminal displays the pending operation
3. The user decides to `approve` or `deny`
4. The approval decision is resolved through `POST /approvals/{id}`
5. Execution continues or stops based on the decision

The `ApprovalStore` (`ai_core/core/approvals.py`) manages pending approvals with token validation.

## Safe Command Execution

The daemon does not accept raw shell text from the model. Instead:

- the model selects a tool from the allowed set
- the tool registry validates the tool name and arguments
- the tool uses structured subprocess calls where possible
- the daemon records command results and errors
- file changes are snapshotted by the rollback manager

When a step requires elevated privileges, the system makes that visible before execution.

## Rollback Support

The rollback manager (`ai_core/core/rollback.py`) provides safety through:

- snapshotting file contents before modification
- tracking which task and step modified each file
- supporting undo of any completed task step
- exposing rollback candidates through the API (`GET /rollback`, `POST /rollback`)

## Token and Credential Handling

### GitHub Tokens

GitHub integration uses a personal access token. The token:

- is read from environment variables (`GITHUB_TOKEN` or `AI_OS_GITHUB_TOKEN`)
- is stored in `.env` which is listed in `.gitignore`
- is never stored in SQLite memory tables
- is never logged in task history
- is never included in plan step arguments

### General Credential Rules

- never commit `.env` or secrets to version control
- use environment variables for all sensitive configuration
- keep generated artifacts (databases, logs) out of source control
- the `.gitignore` file excludes `.env`, `*.db`, and `*.log` files

## Logging and Redaction

Logs are necessary for debugging, but they must avoid leaking sensitive data. The daemon should redact:

- tokens
- secrets
- private credential values

Logs preserve enough structure to explain what happened during a failed step.

## Threat Model

The platform is a local developer system, not a multi-user server. The main security concerns are:

- unsafe command execution
- accidental destructive actions
- leaking credentials into logs or databases
- over-trusting model output

The tool engine, permission model, approval flow, and rollback manager are designed to address exactly those risks.
