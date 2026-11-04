"""Automated tests for scripts/index_folder.py CLI utility."""

from pathlib import Path
import subprocess
import sys
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLI_SCRIPT = REPO_ROOT / "scripts" / "index_folder.py"


def test_cli_help() -> None:
    """Verify that --help runs and displays usage instructions."""
    res = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "OmniSearch — Manual Folder Indexing CLI Utility" in res.stdout
    assert "Usage Examples:" in res.stdout


def test_cli_invalid_path() -> None:
    """Verify non-existent directory path returns exit code 1 with error message."""
    res = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "nonexistent_dir_404"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Folder path does not exist" in res.stderr


def test_cli_file_instead_of_dir(tmp_path: Path) -> None:
    """Verify specifying a file path instead of a directory returns exit code 1."""
    test_file = tmp_path / "single_file.txt"
    test_file.write_text("sample content", encoding="utf-8")

    res = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), str(test_file)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Specified path is a file, not a directory" in res.stderr


def test_cli_successful_indexing(tmp_path: Path) -> None:
    """Verify CLI successfully indexes supported files into an isolated database."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "doc1.txt").write_text("First document text for indexing.", encoding="utf-8")
    (docs_dir / "doc2.md").write_text("# Markdown Notes\nSecond document.", encoding="utf-8")

    db_file = tmp_path / "cli_test.db"

    # 1. First run: index new files
    res = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), str(docs_dir), "--db-path", str(db_file)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Files Discovered  : 2" in res.stdout
    assert "Files Indexed     : 2" in res.stdout
    assert "Files Skipped     : 0" in res.stdout
    assert "Total Chunks      : 2" in res.stdout
    assert "INDEXING SUMMARY" in res.stdout
    assert "[Success]" in res.stdout

    # 2. Second run: unchanged files should be skipped
    res_second = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), str(docs_dir), "--db-path", str(db_file)],
        capture_output=True,
        text=True,
    )
    assert res_second.returncode == 0
    assert "Files Discovered  : 2" in res_second.stdout
    assert "Files Indexed     : 0" in res_second.stdout
    assert "Files Skipped     : 2" in res_second.stdout
    assert "Total Chunks      : 2" in res_second.stdout

