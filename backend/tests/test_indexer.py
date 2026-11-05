"""Tests for persistent indexing service: new files, unchanged skipping, reindexing, and reconciliation."""

from pathlib import Path
import docx
import pymupdf
from app.database.initialization import init_db
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.schemas.processing import IndexJobStatus
from app.services.indexer import IndexingService


def test_index_folder_new_files(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "indexer.db")
    folder_dir = tmp_path / "documents"
    folder_dir.mkdir()

    # Create test files
    (folder_dir / "notes.txt").write_text("OmniSearch local persistent indexing test notes.", encoding="utf-8")
    (folder_dir / "script.py").write_text("def solve():\n    return 42\n", encoding="utf-8")
    (folder_dir / "data.csv").write_text("id,val\n1,Alpha\n2,Beta\n", encoding="utf-8")

    service = IndexingService(db=db)
    job = service.index_folder(folder_dir)

    assert job.status == IndexJobStatus.COMPLETED
    assert job.total_files == 3
    assert job.successful_files == 3
    assert job.failed_files == 0
    assert job.skipped_files == 0

    with db.connection() as conn:
        doc = FileRepository.get_by_path(conn, str(folder_dir / "notes.txt"))
        assert doc is not None
        assert doc.status == "success"
        assert doc.sha256 is not None
        assert len(doc.sha256) == 64

        chunks = ChunkRepository.get_by_file_id(conn, doc.id)
        assert len(chunks) >= 1
        assert "OmniSearch local persistent indexing" in chunks[0].content


def test_index_folder_skips_unchanged_files(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "skip_test.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    file_path = folder_dir / "unchanged.txt"
    file_path.write_text("Persistent content that remains unchanged.", encoding="utf-8")

    service = IndexingService(db=db)

    # Initial run: indexes the file
    job1 = service.index_folder(folder_dir)
    assert job1.successful_files == 1
    assert job1.skipped_files == 0

    # Second run without file modifications: should skip
    job2 = service.index_folder(folder_dir)
    assert job2.successful_files == 0
    assert job2.skipped_files == 1
    assert job2.total_files == 1


def test_index_folder_reindexes_modified_file_and_replaces_chunks(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "modify_test.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    file_path = folder_dir / "article.txt"
    file_path.write_text("Original version content.", encoding="utf-8")

    service = IndexingService(db=db)
    service.index_folder(folder_dir)

    with db.connection() as conn:
        initial_file = FileRepository.get_by_path(conn, str(file_path))
        assert initial_file is not None
        initial_sha = initial_file.sha256
        initial_chunks = ChunkRepository.get_by_file_id(conn, initial_file.id)
        assert "Original version content" in initial_chunks[0].content

    # Modify file on disk
    file_path.write_text("Updated version content with new information.", encoding="utf-8")

    # Re-index
    service.index_folder(folder_dir)

    with db.connection() as conn:
        updated_file = FileRepository.get_by_path(conn, str(file_path))
        assert updated_file is not None
        assert updated_file.sha256 != initial_sha

        updated_chunks = ChunkRepository.get_by_file_id(conn, updated_file.id)
        assert len(updated_chunks) >= 1
        assert "Updated version content" in updated_chunks[0].content
        assert "Original version content" not in updated_chunks[0].content


def test_index_folder_reconciliation_removes_deleted_files(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "reconciliation.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    f1 = folder_dir / "keep.txt"
    f1.write_text("Keep me", encoding="utf-8")
    f2 = folder_dir / "delete_me.txt"
    f2.write_text("Delete me soon", encoding="utf-8")

    service = IndexingService(db=db)
    service.index_folder(folder_dir)

    with db.connection() as conn:
        assert FileRepository.get_by_path(conn, str(f2)) is not None

    # Delete f2 from disk
    f2.unlink()

    # Re-index with reconciliation
    service.index_folder(folder_dir, reconcile_deleted=True)

    with db.connection() as conn:
        assert FileRepository.get_by_path(conn, str(f1)) is not None
        assert FileRepository.get_by_path(conn, str(f2)) is None


def test_index_folder_isolates_corrupted_file(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "fault_isolation.db")
    folder_dir = tmp_path / "mixed"
    folder_dir.mkdir()

    good_file = folder_dir / "valid.txt"
    good_file.write_text("Valid text content", encoding="utf-8")

    bad_file = folder_dir / "broken.pdf"
    bad_file.write_bytes(b"Invalid PDF header bytes")

    service = IndexingService(db=db)
    job = service.index_folder(folder_dir)

    assert job.status == IndexJobStatus.COMPLETED_WITH_ERRORS
    assert job.successful_files == 1
    assert job.failed_files == 1

    with db.connection() as conn:
        good_rec = FileRepository.get_by_path(conn, str(good_file))
        assert good_rec is not None
        assert good_rec.status == "success"

        bad_rec = FileRepository.get_by_path(conn, str(bad_file))
        assert bad_rec is not None
        assert bad_rec.status == "failed"
        assert "lacks '%PDF-'" in (bad_rec.error_message or "")


def test_index_folder_with_real_pdf_and_docx(tmp_path: Path) -> None:
    db = init_db(db_path=tmp_path / "rich_docs.db")
    folder_dir = tmp_path / "rich"
    folder_dir.mkdir()

    # Create real PDF
    pdf_path = folder_dir / "report.pdf"
    pdoc = pymupdf.open()
    p1 = pdoc.new_page()
    p1.insert_text((50, 72), "OmniSearch Financial Page 1")
    pdoc.set_metadata({"title": "Annual Report"})
    pdoc.save(str(pdf_path))
    pdoc.close()

    # Create real DOCX
    docx_path = folder_dir / "manual.docx"
    ddoc = docx.Document()
    ddoc.add_heading("User Manual", level=1)
    ddoc.add_paragraph("Step 1: Launch application.")
    ddoc.save(str(docx_path))

    service = IndexingService(db=db)
    job = service.index_folder(folder_dir)

    assert job.status == IndexJobStatus.COMPLETED
    assert job.successful_files == 2

    with db.connection() as conn:
        pdf_chunks = ChunkRepository.get_by_file_id(conn, FileRepository.get_by_path(conn, str(pdf_path)).id)
        assert len(pdf_chunks) >= 1
        assert "OmniSearch Financial Page 1" in pdf_chunks[0].content
        assert pdf_chunks[0].page_number == 1

        docx_chunks = ChunkRepository.get_by_file_id(conn, FileRepository.get_by_path(conn, str(docx_path)).id)
        assert len(docx_chunks) >= 1
        assert "User Manual" in docx_chunks[0].content or "Launch application" in docx_chunks[0].content


def test_unchanged_detection_identifies_modified_file_with_preserved_mtime_and_size(tmp_path: Path) -> None:
    """Regression test 1: File with identical byte size and preserved mtime must re-index if content hash differs."""
    import os

    db = init_db(db_path=tmp_path / "sha_check.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    file_path = folder_dir / "state.txt"
    # Content A: 16 bytes
    file_path.write_bytes(b"State: ALPHA 001")

    stat_before = file_path.stat()
    orig_atime = stat_before.st_atime
    orig_mtime = stat_before.st_mtime

    service = IndexingService(db=db)
    job1 = service.index_folder(folder_dir)
    assert job1.successful_files == 1
    assert job1.skipped_files == 0

    with db.connection() as conn:
        f1 = FileRepository.get_by_path(conn, str(file_path))
        assert f1 is not None
        c1 = ChunkRepository.get_by_file_id(conn, f1.id)
        assert "ALPHA 001" in c1[0].content

    # Now modify content to Content B with the EXACT SAME size (16 bytes)
    file_path.write_bytes(b"State: OMEGA 999")
    # Restore the previous atime and mtime so timestamps and file size are identical!
    os.utime(file_path, (orig_atime, orig_mtime))

    stat_after = file_path.stat()
    assert stat_after.st_size == stat_before.st_size
    assert stat_after.st_mtime == stat_before.st_mtime

    # Second indexing run: Must NOT skip, because SHA-256 hash has changed!
    job2 = service.index_folder(folder_dir)
    assert job2.successful_files == 1
    assert job2.skipped_files == 0

    with db.connection() as conn:
        f2 = FileRepository.get_by_path(conn, str(file_path))
        assert f2 is not None
        assert f2.sha256 != f1.sha256
        c2 = ChunkRepository.get_by_file_id(conn, f2.id)
        assert len(c2) == 1
        assert "OMEGA 999" in c2[0].content
        assert "ALPHA 001" not in c2[0].content


def test_safe_failed_reindexing_preserves_previously_committed_chunks(tmp_path: Path) -> None:
    """Regression test 2: When extraction of a modified file fails, previously committed chunks must be preserved."""
    db = init_db(db_path=tmp_path / "safe_reindex.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    # Step 1: Create a valid PDF and successfully index it
    pdf_path = folder_dir / "spec.pdf"
    pdoc = pymupdf.open()
    p1 = pdoc.new_page()
    p1.insert_text((50, 72), "OmniSearch Reliable Chunks Version 1.0")
    pdoc.save(str(pdf_path))
    pdoc.close()

    service = IndexingService(db=db)
    job1 = service.index_folder(folder_dir)
    assert job1.successful_files == 1

    with db.connection() as conn:
        f_init = FileRepository.get_by_path(conn, str(pdf_path))
        assert f_init is not None
        init_chunks = ChunkRepository.get_by_file_id(conn, f_init.id)
        assert len(init_chunks) >= 1
        assert "Version 1.0" in init_chunks[0].content
        chunk_count_before = len(init_chunks)

    # Step 2: Corrupt the file on disk (e.g. invalid bytes mimicking broken save or corruption)
    pdf_path.write_bytes(b"%PDF-1.4 Corrupted content truncated header")

    # Step 3: Run indexing again. Re-indexing fails for this file
    job2 = service.index_folder(folder_dir)
    assert job2.status == IndexJobStatus.COMPLETED_WITH_ERRORS
    assert job2.failed_files == 1

    # Step 4: Verify the database state
    with db.connection() as conn:
        f_after = FileRepository.get_by_path(conn, str(pdf_path))
        assert f_after is not None
        assert f_after.status == "failed"
        assert f_after.error_message is not None

        # CRUCIAL ASSERTION: Previously committed chunks must NOT have been deleted!
        chunks_after = ChunkRepository.get_by_file_id(conn, f_after.id)
        assert len(chunks_after) == chunk_count_before
        assert "OmniSearch Reliable Chunks Version 1.0" in chunks_after[0].content


def test_avoid_repeated_hashing_during_extraction(tmp_path: Path, monkeypatch) -> None:
    """Regression test 3: Verify SHA-256 calculation is not repeated unnecessarily for the same file."""
    import app.services.indexer as indexer_mod

    db = init_db(db_path=tmp_path / "hash_count.db")
    folder_dir = tmp_path / "docs"
    folder_dir.mkdir()

    file_path = folder_dir / "doc.txt"
    file_path.write_text("Test single hash invocation per file.", encoding="utf-8")

    hash_call_count = 0
    orig_try_calculate = indexer_mod.try_calculate_sha256

    def counting_hasher(path):
        nonlocal hash_call_count
        hash_call_count += 1
        return orig_try_calculate(path)

    monkeypatch.setattr(indexer_mod, "try_calculate_sha256", counting_hasher)

    service = IndexingService(db=db)
    job = service.index_folder(folder_dir)

    assert job.successful_files == 1
    # During index_folder, try_calculate_sha256 must be called exactly once for this file
    assert hash_call_count == 1

