"""Tests for IngestionCoordinator: batch processing and failure isolation."""

import hashlib
from pathlib import Path
import pymupdf
from app.ingestion.coordinator import IngestionCoordinator
from app.schemas.extraction import ExtractionStatus


def test_coordinator_single_document_with_sha256(tmp_path: Path) -> None:
    txt_path = tmp_path / "hello.txt"
    content = "Hello OmniSearch Coordinator"
    txt_path.write_text(content, encoding="utf-8")

    coordinator = IngestionCoordinator()
    doc = coordinator.extract_document(txt_path, compute_hash=True)

    assert doc.extraction_status == ExtractionStatus.SUCCESS
    assert doc.file_type == "text"
    assert doc.filename == "hello.txt"
    assert doc.sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert len(doc.segments) >= 1
    assert "Hello OmniSearch Coordinator" in doc.segments[0].content


def test_coordinator_batch_failure_isolation(tmp_path: Path) -> None:
    coordinator = IngestionCoordinator()

    # 1. Valid text document
    file1 = tmp_path / "doc1.txt"
    file1.write_text("Valid file 1 content", encoding="utf-8")

    # 2. Corrupt / invalid PDF (signature check rejects it)
    file2 = tmp_path / "corrupt.pdf"
    file2.write_bytes(b"Not a real pdf at all")

    # 3. Disguised executable (.docx with MZ header)
    file3 = tmp_path / "trojan.docx"
    file3.write_bytes(b"MZ\x90\x00\x00\x00Fake Word doc")

    # 4. Valid PDF document
    file4 = tmp_path / "valid.pdf"
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page()
    page.insert_text((50, 72), "Valid PDF document content")
    pdf_doc.save(str(file4))
    pdf_doc.close()

    # 5. Unsupported file format
    file5 = tmp_path / "archive.zip"
    file5.write_bytes(b"PK\x03\x04emptyzip")

    # 6. Non-existent file
    file6 = tmp_path / "does_not_exist.txt"

    batch = [file1, file2, file3, file4, file5, file6]
    summary = coordinator.extract_batch(batch)

    # Crucial assertion: coordinator MUST NOT crash and process all files
    assert summary.total_files == 6
    assert summary.successful == 2  # file1 and file4
    assert summary.failed >= 3      # file2 (invalid_pdf), file3 (rejected_executable), file6 (missing)
    assert summary.unsupported == 1 # file5 (zip)

    # Verify individual statuses
    doc_map = {d.filename: d for d in summary.documents}
    assert doc_map["doc1.txt"].extraction_status == ExtractionStatus.SUCCESS
    assert doc_map["valid.pdf"].extraction_status == ExtractionStatus.SUCCESS
    assert doc_map["corrupt.pdf"].extraction_status == ExtractionStatus.FAILED
    assert doc_map["trojan.docx"].extraction_status == ExtractionStatus.FAILED
    assert doc_map["archive.zip"].extraction_status == ExtractionStatus.UNSUPPORTED
    assert doc_map["does_not_exist.txt"].extraction_status == ExtractionStatus.FAILED
