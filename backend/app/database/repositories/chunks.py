"""Chunks repository for managing persistent document chunks."""

import json
import sqlite3
from typing import List, Optional
from app.schemas.processing import ChunkRecord, DocumentChunk


class ChunkRepository:
    """Data access repository for chunks table."""

    @staticmethod
    def insert_chunks(conn: sqlite3.Connection, file_id: int, chunks: List[DocumentChunk]) -> int:
        """Insert a batch of document chunks for a file within the current transaction."""
        if not chunks:
            return 0

        cursor = conn.cursor()
        rows_to_insert = [
            (
                file_id,
                chunk.chunk_index,
                chunk.source_segment_index,
                chunk.content,
                chunk.token_count,
                chunk.page_number,
                chunk.slide_number,
                chunk.sheet_name,
                chunk.row_number,
                chunk.start_line,
                chunk.end_line,
                json.dumps(chunk.metadata),
            )
            for chunk in chunks
        ]

        cursor.executemany(
            """
            INSERT INTO chunks (
                file_id, chunk_index, source_segment_index, content, token_count,
                page_number, slide_number, sheet_name, row_number, start_line, end_line, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows_to_insert,
        )
        inserted_count = cursor.rowcount
        cursor.close()
        return inserted_count

    @staticmethod
    def delete_by_file_id(conn: sqlite3.Connection, file_id: int) -> int:
        """Delete all chunks belonging to a specific file."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks WHERE file_id = ?;", (file_id,))
        count = cursor.rowcount
        cursor.close()
        return count

    @classmethod
    def get_by_file_id(cls, conn: sqlite3.Connection, file_id: int) -> List[ChunkRecord]:
        """Fetch all chunks for a file ordered by chunk_index."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index ASC;", (file_id,))
        rows = cursor.fetchall()
        cursor.close()
        return [cls._row_to_record(r) for r in rows]

    @staticmethod
    def count_by_file_id(conn: sqlite3.Connection, file_id: int) -> int:
        """Return total chunk count for a file."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE file_id = ?;", (file_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    @staticmethod
    def count_total(conn: sqlite3.Connection) -> int:
        """Return total chunk count across entire database."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks;")
        count = cursor.fetchone()[0]
        cursor.close()
        return count

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ChunkRecord:
        return ChunkRecord(
            id=row["id"],
            file_id=row["file_id"],
            chunk_index=row["chunk_index"],
            source_segment_index=row["source_segment_index"],
            content=row["content"],
            token_count=row["token_count"],
            page_number=row["page_number"],
            slide_number=row["slide_number"],
            sheet_name=row["sheet_name"],
            row_number=row["row_number"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            metadata_json=row["metadata_json"],
        )

