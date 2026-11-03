"""Streaming cryptographic hash computation for local files."""

import hashlib
from pathlib import Path
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CHUNK_SIZE = 65536  # 64 KB blocks for memory-efficient streaming


class HashingError(Exception):
    """Raised when SHA-256 hash computation fails."""
    pass


def calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    """Compute the SHA-256 hexadecimal digest of a file using chunked streaming.

    Args:
        file_path: Path to the target file.
        chunk_size: Size of data chunks read per iteration (bytes).

    Returns:
        Hexadecimal string digest of the SHA-256 hash.

    Raises:
        HashingError: If the file is inaccessible, missing, or an I/O error occurs.
    """
    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise HashingError(f"File not found or is not a regular file: {path_obj}")

    hasher = hashlib.sha256()
    try:
        with open(path_obj, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError) as exc:
        logger.error("Failed to calculate SHA-256 for '%s': %s", path_obj, exc)
        raise HashingError(f"I/O error calculating hash for {path_obj.name}: {exc}") from exc


def try_calculate_sha256(file_path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Optional[str]:
    """Safely attempt to calculate SHA-256 hash, returning None on failure.

    Args:
        file_path: Target file path.
        chunk_size: Chunk buffer size in bytes.

    Returns:
        SHA-256 hex string or None if calculation fails.
    """
    try:
        return calculate_sha256(file_path, chunk_size=chunk_size)
    except HashingError:
        return None
