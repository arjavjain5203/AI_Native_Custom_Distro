"""Memory layer — user memory, project memory, and vector storage.

Handles all persistent and ephemeral state:

- **TaskHistoryStore**: SQLite-backed task and command history.
- **VectorStore**: FAISS-backed semantic retrieval for code understanding.
- **WorkingMemoryStore**: Short-lived context for active task sessions.

Re-exports from ``ai_core.memory``.
"""

from ai_core.memory import (  # noqa: F401
    TaskHistoryStore,
    VectorStore,
    WorkingMemoryStore,
)

__all__ = [
    "TaskHistoryStore",
    "VectorStore",
    "WorkingMemoryStore",
]
