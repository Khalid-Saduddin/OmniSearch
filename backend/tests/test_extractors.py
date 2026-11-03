"""Genuine extraction tests for all supported file formats using programmatic fixtures."""

from pathlib import Path
from bs4 import BeautifulSoup
import docx
import openpyxl
import pptx
import pymupdf
import pytest

from app.ingestion.extractors.csv import CsvExtractor
from app.ingestion.extractors.docx import DocxExtractor
from app.ingestion.extractors.html import HtmlExtractor
from app.ingestion.extractors.pdf import PdfExtractor
from app.ingestion.extractors.pptx import PptxExtractor
from app.ingestion.extractors.text import TextExtractor
from app.ingestion.extractors.xlsx import XlsxExtractor
from app.schemas.extraction import ExtractionStatus, SegmentType


# ==========================================
# 1. PDF Tests
# ==========================================

def test_pdf_extraction(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    doc = pymupdf.open()

    p1 = doc.new_page()
    p1.insert_text((50, 72), "First Page Header\nFirst Page Content for OmniSearch.")

    p2 = doc.new_page()
    p2.insert_text((50, 72), "Second Page Content\nArchitecture and indexing details.")

    doc.set_metadata({"title": "Test PDF Document", "author": "OmniSearch Team"})
    doc.save(str(pdf_path))
    doc.close()

    extractor = PdfExtractor()
    result = extractor.extract(pdf_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "pdf"
    assert result.metadata["title"] == "Test PDF Document"
    assert result.metadata["author"] == "OmniSearch Team"
    assert result.metadata["page_count"] == 2
    assert len(result.segments) == 2

    seg1 = result.segments[0]
    assert seg1.page_number == 1
    assert "First Page Content" in seg1.content

    seg2 = result.segments[1]
    assert seg2.page_number == 2
    assert "Second Page Content" in seg2.content


def test_pdf_empty_file(tmp_path: Path) -> None:
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(b"")

    extractor = PdfExtractor()
    result = extractor.extract(empty_pdf)
    assert result.extraction_status == ExtractionStatus.EMPTY
    assert len(result.segments) == 0


def test_pdf_corrupted_file(tmp_path: Path) -> None:
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"%PDF-1.4\nCorrupted binary payload that is not valid pdf structure")

    extractor = PdfExtractor()
    result = extractor.extract(corrupt_pdf)
    assert result.extraction_status == ExtractionStatus.FAILED
    assert result.error_message is not None


# ==========================================
# 2. DOCX Tests
# ==========================================

def test_docx_extraction(tmp_path: Path) -> None:
    docx_path = tmp_path / "sample.docx"
    doc = docx.Document()
    doc.add_heading("OmniSearch Architecture", level=1)
    doc.add_paragraph("This is the main introduction paragraph.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Header 1"
    table.cell(0, 1).text = "Header 2"
    table.cell(1, 0).text = "Value A"
    table.cell(1, 1).text = "Value B"

    doc.core_properties.title = "OmniSearch Docx"
    doc.core_properties.author = "System Architect"
    doc.save(str(docx_path))

    extractor = DocxExtractor()
    result = extractor.extract(docx_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "docx"
    assert result.metadata["title"] == "OmniSearch Docx"
    assert result.metadata["author"] == "System Architect"
    assert len(result.segments) >= 3

    types = [s.segment_type for s in result.segments]
    assert SegmentType.HEADING in types
    assert SegmentType.PARAGRAPH in types
    assert SegmentType.TABLE in types

    table_seg = next(s for s in result.segments if s.segment_type == SegmentType.TABLE)
    assert "Header 1" in table_seg.content
    assert "Value A" in table_seg.content


def test_docx_empty_file(tmp_path: Path) -> None:
    empty_docx = tmp_path / "empty.docx"
    empty_docx.write_bytes(b"")

    extractor = DocxExtractor()
    result = extractor.extract(empty_docx)
    assert result.extraction_status == ExtractionStatus.EMPTY


# ==========================================
# 3. PPTX Tests
# ==========================================

def test_pptx_extraction(tmp_path: Path) -> None:
    pptx_path = tmp_path / "sample.pptx"
    prs = pptx.Presentation()

    # Slide 1 (title slide)
    title_layout = prs.slide_layouts[0]
    slide1 = prs.slides.add_slide(title_layout)
    slide1.shapes.title.text = "OmniSearch Overview"
    slide1.placeholders[1].text = "One search. Your entire digital world."

    # Slide 2 (bullet slide)
    bullet_layout = prs.slide_layouts[1]
    slide2 = prs.slides.add_slide(bullet_layout)
    slide2.shapes.title.text = "Core Pillars"
    slide2.placeholders[1].text = "Local-First\nPrivacy Preserving\nOffline Capable"

    prs.core_properties.title = "Deck Title"
    prs.save(str(pptx_path))

    extractor = PptxExtractor()
    result = extractor.extract(pptx_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "pptx"
    assert result.metadata["slide_count"] == 2
    assert len(result.segments) == 2

    assert result.segments[0].slide_number == 1
    assert "OmniSearch Overview" in result.segments[0].content

    assert result.segments[1].slide_number == 2
    assert "Local-First" in result.segments[1].content


# ==========================================
# 4. XLSX Tests
# ==========================================

def test_xlsx_extraction(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Inventory"
    ws1.append(["SKU", "Item", "Quantity", "Price"])
    ws1.append(["A101", "Desktop Workstation", 5, 1500])
    ws1.append(["B202", "Mechanical Keyboard", 20, 120])

    ws2 = wb.create_sheet(title="Vendors")
    ws2.append(["Vendor Name", "Region"])
    ws2.append(["TechSupply Inc", "North America"])

    wb.save(str(xlsx_path))
    wb.close()

    extractor = XlsxExtractor()
    result = extractor.extract(xlsx_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "xlsx"
    assert "Inventory" in result.metadata["sheet_names"]
    assert "Vendors" in result.metadata["sheet_names"]

    sheet_names_in_segments = {s.sheet_name for s in result.segments}
    assert "Inventory" in sheet_names_in_segments
    assert "Vendors" in sheet_names_in_segments

    first_row = result.segments[0]
    assert first_row.row_number == 1
    assert "Desktop Workstation" in result.segments[1].content


# ==========================================
# 5. Text, Markdown, and Code Tests
# ==========================================

def test_text_and_code_extraction(tmp_path: Path) -> None:
    code_path = tmp_path / "script.py"
    code_content = (
        '"""Sample python script."""\n\n'
        'def compute_answer() -> int:\n'
        '    """Return life, universe, and everything."""\n'
        '    return 42\n'
    )
    code_path.write_text(code_content, encoding="utf-8")

    extractor = TextExtractor()
    result = extractor.extract(code_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "code"
    assert result.metadata["total_lines"] >= 5
    assert len(result.segments) >= 1
    assert result.segments[0].start_line == 1
    assert result.segments[0].segment_type == SegmentType.CODE_BLOCK
    assert "compute_answer" in result.segments[0].content


def test_markdown_extraction(tmp_path: Path) -> None:
    md_path = tmp_path / "notes.md"
    md_content = "# Project Notes\n\n- Task 1\n- Task 2\n"
    md_path.write_text(md_content, encoding="utf-8")

    extractor = TextExtractor()
    result = extractor.extract(md_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "markdown"
    assert "Project Notes" in result.segments[0].content


# ==========================================
# 6. CSV Tests
# ==========================================

def test_csv_extraction(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    csv_content = (
        'id,name,role,notes\n'
        '1,"Alice Smith",Engineer,"Handles backend & API"\n'
        '2,"Bob Jones",Designer,"UI / UX"\n'
    )
    csv_path.write_text(csv_content, encoding="utf-8")

    extractor = CsvExtractor()
    result = extractor.extract(csv_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "csv"
    assert result.metadata["total_rows"] == 3
    assert len(result.segments) == 3

    assert result.segments[0].row_number == 1
    assert "Alice Smith" in result.segments[1].content
    assert "Bob Jones" in result.segments[2].content


# ==========================================
# 7. HTML Tests
# ==========================================

def test_html_extraction(tmp_path: Path) -> None:
    html_path = tmp_path / "page.html"
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>OmniSearch Documentation</title>
    <meta name="description" content="Local search architecture">
    <style>body { background: #000; }</style>
    <script>alert('malicious code');</script>
</head>
<body>
    <h1>Welcome to OmniSearch</h1>
    <p>Local-first personal knowledge discovery engine.</p>
    <ul>
        <li>Privacy preserved</li>
        <li>Offline capable</li>
    </ul>
</body>
</html>"""
    html_path.write_text(html_content, encoding="utf-8")

    extractor = HtmlExtractor()
    result = extractor.extract(html_path)

    assert result.extraction_status == ExtractionStatus.SUCCESS
    assert result.file_type == "html"
    assert result.metadata["title"] == "OmniSearch Documentation"
    assert result.metadata["description"] == "Local search architecture"

    all_content = " ".join(s.content for s in result.segments)
    assert "Welcome to OmniSearch" in all_content
    assert "Local-first personal knowledge discovery" in all_content
    assert "Privacy preserved" in all_content

    # Verify script and style elements were stripped
    assert "alert(" not in all_content
    assert "background: #000" not in all_content
