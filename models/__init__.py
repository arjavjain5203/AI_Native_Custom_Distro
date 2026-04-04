"""Model layer — Ollama client and model routing logic.

Provides the interface between the AI daemon and local LLM backends:

- **OllamaClient**: Low-level HTTP client for the Ollama REST API.
- **ModelManager**: Manages model selection, hardware detection, runtime switching.
- **ModelRouter**: Classifies tasks and selects the appropriate model/agent.
- **Orchestrator**: High-level decision engine for task routing.

Re-exports from ``ai_core.models``.
"""

from ai_core.models import ModelManager, Orchestrator  # noqa: F401
from ai_core.models.ollama import OllamaClient  # noqa: F401
from ai_core.models.router import ModelRouter  # noqa: F401

__all__ = [
    "ModelManager",
    "ModelRouter",
    "OllamaClient",
    "Orchestrator",
]
