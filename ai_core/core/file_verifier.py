"""Filesystem mutation verification helpers."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any


MUTATING_FILE_TOOLS = {
    "clone_repo",
    "create_file",
    "create_folder",
    "update_file",
    "write_file",
}


def is_filesystem_mutating_tool(tool_name: str | None) -> bool:
    """Return whether the tool should produce a verified filesystem mutation."""
    return bool(tool_name) and tool_name in MUTATING_FILE_TOOLS


def resolve_tool_targets(tool_name: str, args: dict[str, Any], cwd: str, output: Any | None = None) -> list[Path]:
    """Resolve the candidate filesystem targets for a tool invocation."""
    repo_root = Path(cwd).expanduser().resolve()
    candidates: list[Path] = []

    def add_path(value: str | None) -> None:
        if not value:
            return
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        candidates.append(candidate)

    if tool_name in {"create_file", "write_file", "update_file", "create_folder"}:
        raw_path = args.get("path")
        if isinstance(raw_path, str):
            add_path(raw_path)
    elif tool_name == "clone_repo":
        destination = args.get("destination")
        if isinstance(destination, str) and destination.strip():
            add_path(destination)
        else:
            repo_url = args.get("repo_url")
            if isinstance(repo_url, str) and repo_url.strip():
                add_path(repo_url.rstrip("/").split("/")[-1].removesuffix(".git"))

    if isinstance(output, str):
        add_path(output)
    elif isinstance(output, list):
        for item in output:
            if isinstance(item, str):
                add_path(item)

    unique_paths: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(candidate)
    return unique_paths


def snapshot_paths(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """Capture lightweight pre/post state for the provided paths."""
    return {str(path): _snapshot_path(path) for path in paths}


def verify_path_mutations(
    snapshots: dict[str, dict[str, Any]],
    *,
    cwd: str,
) -> dict[str, Any]:
    """Return authoritative mutation details for the previously snapshotted paths."""
    repo_root = Path(cwd).expanduser().resolve()
    files_modified: list[str] = []
    details: list[dict[str, Any]] = []

    for path_str, before in snapshots.items():
        path = Path(path_str)
        after = _snapshot_path(path)
        changed = _snapshot_changed(before, after)
        relative_path = _display_path(path, repo_root)
        detail = {
            "path": relative_path,
            "absolute_path": path_str,
            "changed": changed,
            "before": before,
            "after": after,
        }
        details.append(detail)
        if changed:
            files_modified.append(relative_path)

    return {
        "verified": bool(files_modified),
        "files_modified": files_modified,
        "details": details,
    }


def _snapshot_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return (
        before.get("exists") != after.get("exists")
        or before.get("kind") != after.get("kind")
        or before.get("digest") != after.get("digest")
    )


def _snapshot_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "kind": "missing", "digest": None}
    if path.is_file():
        return {"exists": True, "kind": "file", "digest": _hash_file(path)}
    if path.is_dir():
        return {"exists": True, "kind": "dir", "digest": _hash_directory(path)}
    return {"exists": True, "kind": "other", "digest": str(path.stat().st_mtime_ns)}


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_directory(path: Path) -> str:
    digest = sha256()
    for child in sorted(path.rglob("*")):
        relative = child.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        if child.is_file():
            digest.update(_hash_file(child).encode("utf-8"))
        elif child.is_dir():
            digest.update(b"dir")
    return digest.hexdigest()


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)
