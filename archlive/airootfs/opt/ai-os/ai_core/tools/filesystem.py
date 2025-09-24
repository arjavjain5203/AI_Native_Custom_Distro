"""Filesystem tools."""

from pathlib import Path


def create_file(path: str | Path, content: str = "") -> str:
    """Create or overwrite a file and return its resolved path."""
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def create_folder(path: str | Path) -> str:
    """Create a folder and return its resolved path."""
    folder_path = Path(path).expanduser().resolve()
    folder_path.mkdir(parents=True, exist_ok=True)
    return str(folder_path)


def read_file(path: str | Path) -> str:
    """Read and return UTF-8 text from a file."""
    file_path = Path(path).expanduser().resolve()
    return file_path.read_text(encoding="utf-8")


def write_file(path: str | Path, content: str) -> str:
    """Write file content and return its resolved path."""
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def update_file(path: str | Path, content: str) -> str:
    """Overwrite an existing file and return its resolved path."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"file does not exist: {file_path}")
    file_path.write_text(content, encoding="utf-8")
    return str(file_path)


def list_files(path: str | Path) -> list[str]:
    """Return a sorted list of files under the target directory."""
    root = Path(path).expanduser().resolve()
    return sorted(str(file_path) for file_path in root.rglob("*") if file_path.is_file())
