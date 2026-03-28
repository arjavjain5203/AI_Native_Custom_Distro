"""AI system daemon — main service that orchestrates all components.

Re-exports from the core implementation in ``ai_core.daemon``.
"""

from ai_core.daemon.app import app, create_app  # noqa: F401
from ai_core.daemon.main import main  # noqa: F401

__all__ = ["app", "create_app", "main"]
