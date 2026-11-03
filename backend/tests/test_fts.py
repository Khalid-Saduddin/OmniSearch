"""Tests for SQLite FTS5 virtual table, triggers, and FtsRepository operations."""

import json
from pathlib import Path
import tempfile
import pytest
from app.database.connection import DatabaseConnectionManager
from app.database.migrations import apply_migrations
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.database.repositories.fts import FtsRepository
from app.schemas.processing import DocumentChunk, FileRecord


@pytest.fixture
def temp_db(tmp_path: Path) -> DatabaseConnectionManager:
    """Provide a fresh SQLite database initialized with all migrations."""
    db_file = tmp_path / "test_fts.db"
    db = DatabaseConnectionManager(db_file)
    with db.connection() as conn:
        apply_migrations(conn)
    return db


def test_fts_virtual_table_and_triggers_exist(temp_db: DatabaseConnectionManager) -> None:
    """Verify that chunks_fts virtual table and synchronization triggers are created."""
    with temp_db.connection() as conn:
        cursor = conn.cursor()
        # Verify table in sqlite_master
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts';")
        assert cursor.fetchone() is not None

        # Verify triggers
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger';")
        trigger_names = {row[0] for row in cursor.fetchall()}
        assert "trg_chunks_ai" in trigger_names
        assert "trg_chunks_ad" in trigger_names
        assert "trg_files_ad" in trigger_names
        assert "trg_files_au" in trigger_names
        cursor.close()


def test_insert_chunks_automatically_populates_fts(temp_db: DatabaseConnectionManager) -> None:
    """Verify inserting chunks into canonical chunks table automatically syncs to chunks_fts."""
    with temp_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "C:/docs")
        file_rec = FileRecord(
            folder_id=folder.id,
            path="C:/docs/report.txt",
            filename="report.txt",
            extension=".txt",
            file_type="txt",
            status="success",
            modified_at="2026-11-04T00:00:00Z",
            metadata_json=json.dumps({"title": "Annual Financial Report"}),
        )
        file_id = FileRepository.upsert(conn, file_rec)

        chunk1 = DocumentChunk(
            chunk_index=0,
            content="Total net revenue grew by 25% year over year.",
            token_count=10,
        )
        chunk2 = DocumentChunk(
            chunk_index=1,
            content="Operating expenses remained flat due to efficiency gains.",
            token_count=10,
        )
        ChunkRepository.insert_chunks(conn, file_id, [chunk1, chunk2])

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 2
        # Search content
        cur = conn.cursor()
        cur.execute("SELECT chunk_id, file_id, filename, doc_title FROM chunks_fts WHERE chunks_fts MATCH ?;", ('"revenue"',))
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["filename"] == "report.txt"
        assert rows[0]["doc_title"] == "Annual Financial Report"

        # Search title
        cur.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?;", ('"Financial"',))
        assert len(cur.fetchall()) == 2
        cur.close()


def test_chunk_deletion_syncs_to_fts(temp_db: DatabaseConnectionManager) -> None:
    """Verify deleting chunks removes corresponding FTS entries."""
    with temp_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "C:/docs")
        file_rec = FileRecord(
            folder_id=folder.id,
            path="C:/docs/notes.md",
            filename="notes.md",
            extension=".md",
            file_type="markdown",
            status="success",
            modified_at="2026-11-04T00:00:00Z",
        )
        file_id = FileRepository.upsert(conn, file_rec)
        ChunkRepository.insert_chunks(
            conn,
            file_id,
            [DocumentChunk(chunk_index=0, content="Machine learning models", token_count=5)],
        )

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 1

    with temp_db.transaction() as conn:
        ChunkRepository.delete_by_file_id(conn, file_id)

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 0


def test_file_deletion_cascades_to_fts(temp_db: DatabaseConnectionManager) -> None:
    """Verify deleting a file cascades to purge corresponding FTS entries."""
    with temp_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "C:/docs")
        file_rec = FileRecord(
            folder_id=folder.id,
            path="C:/docs/paper.pdf",
            filename="paper.pdf",
            extension=".pdf",
            file_type="pdf",
            status="success",
            modified_at="2026-11-04T00:00:00Z",
        )
        file_id = FileRepository.upsert(conn, file_rec)
        ChunkRepository.insert_chunks(
            conn,
            file_id,
            [
                DocumentChunk(chunk_index=0, content="Deep convolutional networks", token_count=5),
                DocumentChunk(chunk_index=1, content="Residual connections", token_count=5),
            ],
        )

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 2

    with temp_db.transaction() as conn:
        FileRepository.delete(conn, file_id)

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 0


def test_file_metadata_update_syncs_to_fts(temp_db: DatabaseConnectionManager) -> None:
    """Verify renaming a file or updating title metadata propagates to FTS records."""
    with temp_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "C:/docs")
        file_rec = FileRecord(
            folder_id=folder.id,
            path="C:/docs/draft.txt",
            filename="draft.txt",
            extension=".txt",
            file_type="txt",
            status="success",
            modified_at="2026-11-04T00:00:00Z",
            metadata_json=json.dumps({"title": "Initial Draft"}),
        )
        file_id = FileRepository.upsert(conn, file_rec)
        ChunkRepository.insert_chunks(
            conn,
            file_id,
            [DocumentChunk(chunk_index=0, content="Introduction to search engines", token_count=5)],
        )

    # Rename file and update title
    with temp_db.transaction() as conn:
        updated_file = file_rec.model_copy(
            update={
                "id": file_id,
                "filename": "final.txt",
                "metadata_json": json.dumps({"title": "Complete Handbook"}),
            }
        )
        FileRepository.upsert(conn, updated_file)

    with temp_db.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filename, doc_title FROM chunks_fts WHERE file_id = ?;", (file_id,))
        row = cur.fetchone()
        assert row["filename"] == "final.txt"
        assert row["doc_title"] == "Complete Handbook"
        cur.close()


def test_fts_repository_rebuild_index(temp_db: DatabaseConnectionManager) -> None:
    """Verify FtsRepository.rebuild_index clears and reconstructs the full FTS index."""
    with temp_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "C:/docs")
        f1 = FileRepository.upsert(
            conn,
            FileRecord(
                folder_id=folder.id,
                path="C:/docs/f1.txt",
                filename="f1.txt",
                extension=".txt",
                file_type="txt",
                status="success",
                modified_at="2026-11-04T00:00:00Z",
            ),
        )
        f2 = FileRepository.upsert(
            conn,
            FileRecord(
                folder_id=folder.id,
                path="C:/docs/f2.txt",
                filename="f2.txt",
                extension=".txt",
                file_type="txt",
                status="success",
                modified_at="2026-11-04T00:00:00Z",
            ),
        )
        ChunkRepository.insert_chunks(
            conn, f1, [DocumentChunk(chunk_index=0, content="Chunk one", token_count=2)]
        )
        ChunkRepository.insert_chunks(
            conn, f2, [DocumentChunk(chunk_index=0, content="Chunk two", token_count=2)]
        )

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 2

    # Simulate index corruption or manual truncate
    with temp_db.transaction() as conn:
        conn.execute("DELETE FROM chunks_fts;")
        assert FtsRepository.count_total(conn) == 0
        rebuilt = FtsRepository.rebuild_index(conn)
        assert rebuilt == 2

    with temp_db.connection() as conn:
        assert FtsRepository.count_total(conn) == 2
        FtsRepository.optimize(conn)
