"""AI Developer Terminal — the primary user interface.

Provides the natural-language command line for interacting with
the AI daemon.  Re-exports the CLI entry point from ``ai_core.cli``.
"""

from __future__ import annotations

from ai_core.cli.main import main  # noqa: F401

__all__ = ["main"]
