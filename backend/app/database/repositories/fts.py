"""FTS repository for managing full-text search virtual table operations and maintenance."""

import sqlite3
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class FtsRepository:
    """Data access repository for SQLite FTS5 virtual table operations."""

    @staticmethod
    def rebuild_index(conn: sqlite3.Connection) -> int:
        """Truncate and fully rebuild the FTS5 chunks index from canonical SQLite tables.

        Args:
            conn: Active SQLite connection in transaction.

        Returns:
            Total number of chunks indexed into FTS.
        """
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks_fts;")
        cursor.execute("""
        INSERT INTO chunks_fts (content, filename, doc_title, chunk_id, file_id)
        SELECT c.content,
               f.filename,
               COALESCE(json_extract(f.metadata_json, '$.title'), f.filename),
               c.id,
               c.file_id
        FROM chunks c
        JOIN files f ON c.file_id = f.id;
        """)
        rebuilt_count = cursor.rowcount
        cursor.close()
        logger.info("Rebuilt FTS5 index containing %d chunk(s)", rebuilt_count)
        return rebuilt_count

    @staticmethod
    def delete_by_file_id(conn: sqlite3.Connection, file_id: int) -> int:
        """Manually purge all FTS5 records belonging to a file ID."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks_fts WHERE file_id = ?;", (file_id,))
        count = cursor.rowcount
        cursor.close()
        return count

    @staticmethod
    def delete_by_chunk_id(conn: sqlite3.Connection, chunk_id: int) -> int:
        """Manually purge a specific chunk record from FTS5."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks_fts WHERE chunk_id = ?;", (chunk_id,))
        count = cursor.rowcount
        cursor.close()
        return count

    @staticmethod
    def count_total(conn: sqlite3.Connection) -> int:
        """Return total number of indexed entries in chunks_fts."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks_fts;")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    @staticmethod
    def optimize(conn: sqlite3.Connection) -> None:
        """Execute FTS5 optimize command to consolidate B-tree segments."""
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize');")
        cursor.close()
        logger.debug("Optimized chunks_fts FTS5 index segments")
