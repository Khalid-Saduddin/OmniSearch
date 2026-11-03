"""Tests for file type detection and security signature validation."""

from pathlib import Path
from app.ingestion.file_detector import FileTypeDetector


def test_supported_extensions() -> None:
    assert FileTypeDetector.is_supported_extension(".pdf")
    assert FileTypeDetector.is_supported_extension(".docx")
    assert FileTypeDetector.is_supported_extension(".pptx")
    assert FileTypeDetector.is_supported_extension(".xlsx")
    assert FileTypeDetector.is_supported_extension(".py")
    assert FileTypeDetector.is_supported_extension(".md")
    assert FileTypeDetector.is_supported_extension(".csv")
    assert FileTypeDetector.is_supported_extension(".html")

    assert not FileTypeDetector.is_supported_extension(".exe")
    assert not FileTypeDetector.is_supported_extension(".dll")
    assert not FileTypeDetector.is_supported_extension(".bin")


def test_rejects_disguised_executable(tmp_path: Path) -> None:
    # A Windows PE executable disguised as a PDF
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00This is malware")

    is_valid, category, error = FileTypeDetector.validate_file(fake_pdf)
    assert not is_valid
    assert category == "rejected_executable"
    assert "executable binary header signature" in (error or "")


def test_rejects_invalid_pdf_signature(tmp_path: Path) -> None:
    bad_pdf = tmp_path / "broken.pdf"
    bad_pdf.write_bytes(b"This is just plain text without any PDF header.")

    is_valid, category, error = FileTypeDetector.validate_file(bad_pdf)
    assert not is_valid
    assert category == "invalid_pdf"
    assert "lacks '%PDF-'" in (error or "")


def test_rejects_invalid_office_file(tmp_path: Path) -> None:
    fake_docx = tmp_path / "document.docx"
    fake_docx.write_bytes(b"Not a zip file at all")

    is_valid, category, error = FileTypeDetector.validate_file(fake_docx)
    assert not is_valid
    assert category == "invalid_docx"
    assert "lacks valid ZIP header" in (error or "")


def test_validates_empty_supported_file(tmp_path: Path) -> None:
    empty_txt = tmp_path / "empty.txt"
    empty_txt.write_bytes(b"")

    is_valid, category, error = FileTypeDetector.validate_file(empty_txt)
    assert is_valid
    assert category == "text"
    assert error is None
