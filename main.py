#!/usr/bin/env python3
"""AI-Native Developer Operating Environment — main entry point.

Starts the local AI daemon, validates the Ollama runtime, and opens
the system for natural-language developer commands.
"""

from __future__ import annotations

import sys
import textwrap

import uvicorn

from ai_core.core.config import API_HOST, API_PORT, OLLAMA_BASE_URL


BANNER = textwrap.dedent(
    """\
    ┌──────────────────────────────────────────────────────┐
    │  AI-Native Developer Operating Environment  v0.1.0   │
    │  Local daemon · Ollama-backed · Multi-agent system   │
    └──────────────────────────────────────────────────────┘
    """
)


def _check_ollama() -> bool:
    """Return True if the local Ollama runtime is reachable."""
    from urllib import error, request

    try:
        req = request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with request.urlopen(req, timeout=5):
            return True
    except (error.URLError, error.HTTPError, OSError):
        return False


def main() -> None:
    """Start the AI daemon."""
    print(BANNER)

    if not _check_ollama():
        print(
            f"⚠  Ollama is not reachable at {OLLAMA_BASE_URL}\n"
            "   Install Ollama (https://ollama.com) and run `ollama serve`.\n"
            "   The daemon will start anyway, but model calls will fail.\n",
            file=sys.stderr,
        )

    print(f"→ Starting daemon on http://{API_HOST}:{API_PORT}")
    uvicorn.run(
        "ai_core.daemon.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
