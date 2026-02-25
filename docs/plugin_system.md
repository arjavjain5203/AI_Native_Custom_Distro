# Plugin System

## Purpose

The plugin system allows the platform to extend its tool capabilities without forcing all integrations into the daemon core. This is important for long-term open-source growth and for keeping the system maintainable.

## Plugin Architecture

Plugins are Python modules under the `plugins/` directory. Each plugin provides a dataclass-based interface that wraps lower-level tool implementations from `ai_core/tools/`. A plugin defines:

- a plugin class with configuration
- exported methods that map to tool operations
- authentication handling where needed
- structured return types

## Implemented Plugins

### GitHub Plugin (`plugins/github_plugin.py`)

The GitHub plugin wraps the core GitHub tools for repository management.

```python
from plugins.github_plugin import GitHubPlugin

plugin = GitHubPlugin(token="ghp_...")
plugin.authenticated       # True if token is configured
plugin.create_repo("my-project", private=False)
plugin.push_file("owner", "repo", "path/file.py", content, "commit msg")
```

Features:

- `authenticated` — checks whether a token is configured
- `create_repo(name, private)` — creates a GitHub repository
- `push_file(owner, repo, path, content, message)` — pushes a file to a repository

Authentication uses a personal access token from the `GITHUB_TOKEN` environment variable or explicit configuration.

### Docker Plugin (`plugins/docker_plugin.py`)

The Docker plugin provides container lifecycle management through the Docker CLI.

```python
from plugins.docker_plugin import DockerPlugin

plugin = DockerPlugin()
plugin.build(".", tag="app:latest")
plugin.run("app:latest", name="my-app", ports={"8080": "80"})
plugin.ps(all_containers=True)
plugin.stop("my-app")
```

Features:

- `build(path, tag)` — build a Docker image
- `run(image, name, detach, ports)` — run a container
- `stop(container)` — stop a running container
- `ps(all_containers)` — list containers

All operations run through subprocess, never through direct Docker socket access, to maintain the tool-engine security boundary.

## Registration Model

Plugins register their tools by importing and wrapping the underlying `ai_core/tools/` implementations. At startup, enabled plugins can be loaded and their tools added to the global tool registry.

Plugin loading fails loudly if:

- required metadata is missing
- a tool name collides with an existing tool
- the plugin depends on unavailable runtime features

Plugin configuration is managed through `config.yaml` under the `plugins:` section:

```yaml
plugins:
  github:
    enabled: true
  docker:
    enabled: false
    binary: "docker"
```

## Permission Integration

Plugin tools are subject to the same permission system as core tools. The `permissions.json` file defines per-tool policies:

- `allow` — execute without confirmation (e.g., listing repos)
- `prompt` — require user approval (e.g., creating repos, running containers)
- `deny` — block execution (e.g., system-level installs)

## Creating a New Plugin

To add a new plugin:

1. Create a new file in `plugins/` (e.g., `plugins/my_plugin.py`)
2. Define a dataclass with configuration fields
3. Implement methods that wrap tool operations
4. Add permission entries in `permissions.json`
5. Add configuration in `config.yaml` under `plugins:`
6. Add tests in `tests/test_plugins.py`

Example skeleton:

```python
from dataclasses import dataclass

@dataclass
class MyPlugin:
    api_key: str = ""

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key)

    def my_operation(self, arg: str) -> dict:
        # Implementation here
        return {"success": True, "result": arg}
```

## Why Plugins Matter

A plugin architecture provides three benefits:

- it keeps the daemon core focused on orchestration
- it creates a stable extension point for future contributors
- it supports incremental expansion without redesigning the whole system

## Future Plugin Directions

The long-term plugin ecosystem includes:

- Database and migration tools
- Cloud provider integrations (AWS, GCP, Azure)
- CI/CD systems (GitHub Actions, GitLab CI)
- Project templates and scaffolding packs
- Package registry integrations (PyPI, npm)
