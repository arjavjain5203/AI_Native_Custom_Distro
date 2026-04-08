"""Plugin integrations — GitHub, Docker, and other external services.

Plugins extend the AI daemon with connectors to third-party platforms.
Each plugin registers its tools with the tool registry so agents can
invoke them during plan execution.

Available plugins:

- **github**: Repository creation, PR management, issue tracking via PAT.
- **docker**: Container lifecycle management (build, run, stop).
"""

__all__: list[str] = []
