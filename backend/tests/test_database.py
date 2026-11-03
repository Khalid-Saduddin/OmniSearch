"""Tests for SQLite database architecture, foreign-key cascades, transactions, and recovery."""

from pathlib import Path
import pytest
from app.database.connection import DatabaseConnectionManager
from app.database.initialization import init_db, recover_interrupted_jobs
from app.database.migrations import apply_migrations
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.database.repositories.jobs import JobRepository
from app.database.repositories.settings import SettingRepository
from app.schemas.processing import DocumentChunk, FileRecord, IndexJobStatus


def test_init_db_creates_tables_and_indexes(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    db = init_db(db_path=db_file)

    with db.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        cursor.close()

    assert "folders" in tables
    assert "files" in tables
    assert "chunks" in tables
    assert "index_jobs" in tables
    assert "settings" in tables
    assert "schema_migrations" in tables


def test_foreign_key_cascade_deletion(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "cascade.db")

    with db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, "/user/documents")
        file_rec = FileRecord(
            folder_id=folder.id,
            path="/user/documents/doc.txt",
            filename="doc.txt",
            extension=".txt",
            file_type="text",
            modified_at="2026-11-03T00:00:00Z",
            status="success",
        )
        file_id = FileRepository.upsert(conn, file_rec)

        chunk = DocumentChunk(
            chunk_index=0,
            content="Sample chunk content",
            token_count=10,
            source_segment_index=0,
        )
        ChunkRepository.insert_chunks(conn, file_id, [chunk])

    # Verify records exist
    with db.connection() as conn:
        assert FileRepository.get_by_id(conn, file_id) is not None
        assert len(ChunkRepository.get_by_file_id(conn, file_id)) == 1

    # Delete folder -> should CASCADE delete file and chunks
    with db.transaction() as conn:
        assert folder.id is not None
        deleted = FolderRepository.delete(conn, folder.id)
        assert deleted

    with db.connection() as conn:
        assert FileRepository.get_by_id(conn, file_id) is None
        assert len(ChunkRepository.get_by_file_id(conn, file_id)) == 0


def test_transaction_rollback_on_exception(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "rollback.db")

    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            FolderRepository.get_or_create(conn, "/user/test_rollback")
            raise RuntimeError("Forced simulation error")

    # Verify that the folder was NOT persisted due to rollback
    with db.connection() as conn:
        folders = FolderRepository.list_all(conn)
        assert len(folders) == 0


def test_persistence_across_connection_reopen(tmp_path: Path) -> None:
    db_file = tmp_path / "persistent.db"

    # Session 1: Create and write
    db1 = init_db(db_path=db_file)
    with db1.transaction() as conn:
        SettingRepository.set(conn, "app_mode", "desktop_local")
        FolderRepository.get_or_create(conn, "/data/folder1")

    # Session 2: Reopen from same file
    db2 = DatabaseConnectionManager(db_path=db_file)
    with db2.connection() as conn:
        val = SettingRepository.get(conn, "app_mode")
        assert val == "desktop_local"

        folders = FolderRepository.list_all(conn)
        assert len(folders) == 1
        assert folders[0].path.endswith("folder1")


def test_interrupted_jobs_recovery_policy(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "recovery.db", recover_jobs=False)

    with db.transaction() as conn:
        job_id = JobRepository.create(conn, total_files=10)
        # Job starts in 'running' status

    # Simulate process restart by calling recover_interrupted_jobs
    recovered_count = recover_interrupted_jobs(db)
    assert recovered_count == 1

    with db.connection() as conn:
        job = JobRepository.get_by_id(conn, job_id)
        assert job is not None
        assert job.status == IndexJobStatus.INTERRUPTED
        assert job.finished_at is not None
        assert "interrupted" in (job.error_message or "").lower()

