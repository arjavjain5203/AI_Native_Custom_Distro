"""Daemon launcher."""

from __future__ import annotations

import uvicorn

from ai_core.core.config import API_HOST, API_PORT


def main() -> None:
    """Run the local FastAPI daemon with uvicorn."""
    uvicorn.run(
        "ai_core.daemon.app:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
