"""Tests for streaming SHA-256 hash calculation."""

import hashlib
from pathlib import Path
import pytest
from app.ingestion.hashing import HashingError, calculate_sha256, try_calculate_sha256


def test_calculate_sha256_known_content(tmp_path: Path) -> None:
    test_file = tmp_path / "test.txt"
    content = b"OmniSearch local-first search engine hash test"
    test_file.write_bytes(content)

    expected_hash = hashlib.sha256(content).hexdigest()
    computed_hash = calculate_sha256(test_file)

    assert computed_hash == expected_hash
    assert len(computed_hash) == 64


def test_calculate_sha256_large_chunking(tmp_path: Path) -> None:
    test_file = tmp_path / "large_chunk.bin"
    # Create 256 KB of deterministic data
    content = b"A" * (256 * 1024)
    test_file.write_bytes(content)

    expected_hash = hashlib.sha256(content).hexdigest()
    # Test with a very small chunk size to verify multi-chunk iteration
    computed_hash = calculate_sha256(test_file, chunk_size=1024)

    assert computed_hash == expected_hash


def test_calculate_sha256_empty_file(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.txt"
    empty_file.write_bytes(b"")

    expected_hash = hashlib.sha256(b"").hexdigest()
    assert calculate_sha256(empty_file) == expected_hash


def test_calculate_sha256_nonexistent_file(tmp_path: Path) -> None:
    missing_file = tmp_path / "does_not_exist.bin"
    with pytest.raises(HashingError):
        calculate_sha256(missing_file)


def test_try_calculate_sha256_returns_none_on_failure(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.bin"
    assert try_calculate_sha256(missing_file) is None
