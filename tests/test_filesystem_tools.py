"""Tests for filesystem tool operations."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestFilesystemTools:
    """Validate filesystem tool behavior."""

    def test_read_file_returns_content(self, tmp_path: Path) -> None:
        """Reading a file should return its content as a string."""
        target = tmp_path / "hello.txt"
        target.write_text("hello world")

        from ai_core.tools.filesystem import read_file

        result = read_file(str(target))
        assert "hello world" in result

    def test_read_file_missing_raises(self, tmp_path: Path) -> None:
        """Reading a nonexistent file should raise FileNotFoundError."""
        from ai_core.tools.filesystem import read_file

        with pytest.raises(FileNotFoundError):
            read_file(str(tmp_path / "nonexistent.txt"))

    def test_write_file_creates_file(self, tmp_path: Path) -> None:
        """Writing to a new path should create the file and return its path."""
        from ai_core.tools.filesystem import write_file

        target = tmp_path / "output.txt"
        result = write_file(str(target), "test content")
        assert target.exists()
        assert target.read_text() == "test content"
        assert str(target) in result

    def test_create_file(self, tmp_path: Path) -> None:
        """create_file should create a file with content."""
        from ai_core.tools.filesystem import create_file

        target = tmp_path / "new.py"
        result = create_file(str(target), "print('hello')")
        assert target.exists()
        assert target.read_text() == "print('hello')"
        assert str(target) in result

    def test_create_folder(self, tmp_path: Path) -> None:
        """create_folder should create a directory tree."""
        from ai_core.tools.filesystem import create_folder

        target = tmp_path / "deep" / "nested" / "dir"
        result = create_folder(str(target))
        assert target.is_dir()
        assert str(target) in result

    def test_list_files(self, tmp_path: Path) -> None:
        """list_files should return all files recursively."""
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "c.txt").touch()

        from ai_core.tools.filesystem import list_files

        result = list_files(str(tmp_path))
        assert len(result) == 3

    def test_update_file_existing(self, tmp_path: Path) -> None:
        """update_file should overwrite an existing file."""
        from ai_core.tools.filesystem import update_file

        target = tmp_path / "existing.txt"
        target.write_text("old content")
        result = update_file(str(target), "new content")
        assert target.read_text() == "new content"
        assert str(target) in result

    def test_update_file_missing_raises(self, tmp_path: Path) -> None:
        """update_file should raise when the file does not exist."""
        from ai_core.tools.filesystem import update_file

        with pytest.raises(FileNotFoundError):
            update_file(str(tmp_path / "missing.txt"), "content")
