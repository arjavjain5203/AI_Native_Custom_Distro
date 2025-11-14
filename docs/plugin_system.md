# Plugin System

## Purpose

The plugin system allows the platform to extend its tool capabilities without forcing all integrations into the daemon core. This is important for long-term open-source growth and for keeping v1 maintainable.

## Plugin Architecture

Plugins in v1 are Python modules that register tools with the tool registry. A plugin should define:

- plugin name
- version
- declared permissions
- exported tools
- any required configuration

This keeps integrations discoverable and testable.

## Registration Model

At startup, the daemon should load enabled plugins and register their tools into the global tool registry. Registration should fail loudly if:

- required metadata is missing
- a tool name collides with an existing tool
- the plugin depends on unavailable runtime features

Plugin loading should be deterministic rather than driven by model prompts.

## v1 Plugins

The required plugin domains in v1 are:

- filesystem
- git
- GitHub
- package manager

Docker should be designed as a plugin but treated as optional.

## GitHub Plugin Example

The GitHub plugin is the main external-service integration in v1. It should provide tools such as:

- create repository
- fetch repository metadata
- verify authentication

It should use a GitHub personal access token stored securely outside the normal memory database.

## Docker Plugin Example

Docker is not part of baseline v1 acceptance, but the architecture should make it easy to add a Docker plugin with tools such as:

- install Docker
- start or enable the Docker service
- verify Docker availability

Treat this as a stretch integration that benefits from the same plugin contract used by GitHub.

## Why Plugins Matter

A plugin architecture provides three benefits:

- it keeps the daemon core focused on orchestration
- it creates a stable extension point for future contributors
- it supports incremental expansion without redesigning the whole system

## v1 Boundaries

Version 1 should not overcomplicate plugins with remote marketplaces or hot-reload systems. The goal is a clean local registration model that supports future growth.
