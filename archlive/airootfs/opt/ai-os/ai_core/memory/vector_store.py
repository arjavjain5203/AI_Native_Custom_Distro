"""Repository retrieval store with optional FAISS support."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from ai_core.memory.embeddings import EmbeddingProvider

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    faiss = None


SUPPORTED_EXTENSIONS = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json"}


class VectorStore:
    """Persist and search repository chunks."""

    def __init__(self, db_path: str | Path = "ai_core_vectors.db", embedding_provider: EmbeddingProvider | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        self._initialize()

    def index_repository(self, repo_path: str | Path) -> int:
        repo_root = Path(repo_path).expanduser().resolve()
        chunks = list(self._iter_chunks(repo_root))
        embeddings = self.embedding_provider.embed_texts([chunk["content"] for chunk in chunks])

        with self._connect() as connection:
            connection.execute("DELETE FROM indexed_chunks WHERE repo_path = ?", (str(repo_root),))
            for chunk, embedding in zip(chunks, embeddings):
                connection.execute(
                    """
                    INSERT INTO indexed_chunks
                        (repo_path, file_path, chunk_id, content, embedding_json)
                    VALUES
                        (?, ?, ?, ?, ?)
                    """,
                    (
                        str(repo_root),
                        chunk["file_path"],
                        chunk["chunk_id"],
                        chunk["content"],
                        json.dumps(embedding),
                    ),
                )
            connection.commit()
        return len(chunks)

    def search(self, repo_path: str | Path, query: str, limit: int = 5) -> list[dict[str, Any]]:
        repo_root = Path(repo_path).expanduser().resolve()
        query_vector = self.embedding_provider.embed_text(query)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT file_path, chunk_id, content, embedding_json
                FROM indexed_chunks
                WHERE repo_path = ?
                """,
                (str(repo_root),),
            ).fetchall()

        if not rows:
            return []

        if faiss is not None:
            return self._search_with_faiss(
                rows,
                query_vector,
                limit,
                lambda row, score: {
                    "file_path": row["file_path"],
                    "chunk_id": row["chunk_id"],
                    "content": row["content"],
                    "score": score,
                },
            )

        ranked: list[dict[str, Any]] = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            score = self.embedding_provider.cosine_similarity(query_vector, embedding)
            ranked.append(
                {
                    "file_path": row["file_path"],
                    "chunk_id": row["chunk_id"],
                    "content": row["content"],
                    "score": score,
                }
            )
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

    def index_task_summary(self, task_id: str, cwd: str, summary: str) -> None:
        """Persist an embedding for a completed task summary."""
        cleaned_task_id = task_id.strip()
        cleaned_cwd = str(Path(cwd).expanduser().resolve())
        cleaned_summary = summary.strip()
        if not cleaned_task_id or not cleaned_summary:
            return

        embedding = self.embedding_provider.embed_text(cleaned_summary)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO task_summary_embeddings
                    (task_id, cwd, summary, embedding_json)
                VALUES
                    (?, ?, ?, ?)
                """,
                (
                    cleaned_task_id,
                    cleaned_cwd,
                    cleaned_summary,
                    json.dumps(embedding),
                ),
            )
            connection.commit()

    def get_related_tasks(self, query: str, cwd: str, limit: int = 3) -> list[dict[str, str]]:
        """Return top matching task summaries, preferring the current workspace."""
        cleaned_query = query.strip()
        if not cleaned_query or limit <= 0:
            return []

        query_vector = self.embedding_provider.embed_text(cleaned_query)
        if not any(query_vector):
            return []

        cleaned_cwd = str(Path(cwd).expanduser().resolve())
        with self._connect() as connection:
            workspace_rows = connection.execute(
                """
                SELECT task_id, cwd, summary, embedding_json
                FROM task_summary_embeddings
                WHERE cwd = ?
                """,
                (cleaned_cwd,),
            ).fetchall()
            global_rows = connection.execute(
                """
                SELECT task_id, cwd, summary, embedding_json
                FROM task_summary_embeddings
                WHERE cwd != ?
                """,
                (cleaned_cwd,),
            ).fetchall()

        ranked: list[dict[str, Any]] = []
        seen_task_ids: set[str] = set()
        for rows in (workspace_rows, global_rows):
            for item in self._rank_task_rows(rows, query_vector, limit=limit):
                task_id = str(item["task_id"])
                if task_id in seen_task_ids:
                    continue
                seen_task_ids.add(task_id)
                ranked.append(
                    {
                        "task_id": task_id,
                        "summary": str(item["summary"]),
                    }
                )
                if len(ranked) >= limit:
                    return ranked
        return ranked

    def _search_with_faiss(
        self,
        rows: list[sqlite3.Row],
        query_vector: list[float],
        limit: int,
        row_mapper: Callable[[sqlite3.Row, float], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        import numpy as np  # type: ignore

        vectors = [json.loads(row["embedding_json"]) for row in rows]
        matrix = np.array(vectors, dtype="float32")
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        distances, indices = index.search(np.array([query_vector], dtype="float32"), min(limit, len(rows)))

        results: list[dict[str, Any]] = []
        for score, row_index in zip(distances[0], indices[0]):
            row = rows[int(row_index)]
            results.append(row_mapper(row, float(score)))
        return results

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_chunks (
                    repo_path TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    PRIMARY KEY (repo_path, file_path, chunk_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_summary_embeddings (
                    task_id TEXT PRIMARY KEY,
                    cwd TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    embedding_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _iter_chunks(self, repo_root: Path) -> list[dict[str, str]]:
        chunks: list[dict[str, str]] = []
        for file_path in sorted(repo_root.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            relative_path = file_path.relative_to(repo_root).as_posix()
            content = file_path.read_text(encoding="utf-8", errors="replace")
            chunks.append(
                {
                    "file_path": relative_path,
                    "chunk_id": "full",
                    "content": content,
                }
            )
        return chunks

    def _rank_task_rows(self, rows: list[sqlite3.Row], query_vector: list[float], limit: int) -> list[dict[str, Any]]:
        if not rows:
            return []

        if faiss is not None:
            ranked = self._search_with_faiss(
                rows,
                query_vector,
                min(limit, len(rows)),
                lambda row, score: {
                    "task_id": row["task_id"],
                    "cwd": row["cwd"],
                    "summary": row["summary"],
                    "score": score,
                },
            )
        else:
            ranked = []
            for row in rows:
                summary = str(row["summary"]).strip()
                if not summary:
                    continue
                embedding = json.loads(row["embedding_json"])
                score = self.embedding_provider.cosine_similarity(query_vector, embedding)
                if score <= 0.0:
                    continue
                ranked.append(
                    {
                        "task_id": row["task_id"],
                        "cwd": row["cwd"],
                        "summary": summary,
                        "score": score,
                    }
                )
            ranked = sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

        filtered: list[dict[str, Any]] = []
        for item in ranked:
            summary = str(item.get("summary", "")).strip()
            if not summary:
                continue
            score = float(item.get("score", 0.0))
            if score <= 0.0:
                continue
            filtered.append(item)
        return filtered[:limit]
