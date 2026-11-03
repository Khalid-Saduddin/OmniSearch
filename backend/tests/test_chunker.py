"""Tests for document chunking, boundary preservation, and token counting."""

from app.processing.chunker import DocumentChunker
from app.processing.token_counter import ApproximateTokenCounter
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType


def test_approximate_token_counter() -> None:
    counter = ApproximateTokenCounter()
    assert counter.count_tokens("") == 0
    assert counter.count_tokens("hello") == 2  # 5 chars -> 2 subword tokens
    # Short sentence
    text = "OmniSearch is a local-first search engine."
    count = counter.count_tokens(text)
    assert 6 <= count <= 15


def test_short_document_creates_single_chunk() -> None:
    chunker = DocumentChunker(target_tokens=500, overlap_tokens=80)
    doc = ExtractedDocument(
        file_path="/docs/guide.txt",
        filename="guide.txt",
        extension=".txt",
        file_type="text",
        file_size=120,
        extraction_status=ExtractionStatus.SUCCESS,
        segments=[
            ExtractedSegment(
                content="This is a short document fitting comfortably within target token size.",
                segment_index=0,
                segment_type=SegmentType.TEXT_BLOCK,
                start_line=1,
                end_line=2,
            )
        ],
    )
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
    assert "short document" in chunks[0].content
    assert chunks[0].metadata["filename"] == "guide.txt"


def test_long_document_splits_with_overlap() -> None:
    # Use smaller target_tokens in test to trigger multi-chunk splitting
    chunker = DocumentChunker(target_tokens=50, overlap_tokens=15)

    paragraphs = [
        f"Paragraph {i}: This is structured prose for OmniSearch testing sentence boundaries. "
        f"Document retrieval requires meaningful semantic overlap across chunks."
        for i in range(1, 10)
    ]
    long_text = "\n\n".join(paragraphs)

    doc = ExtractedDocument(
        file_path="/docs/manual.md",
        filename="manual.md",
        extension=".md",
        file_type="markdown",
        file_size=len(long_text),
        extraction_status=ExtractionStatus.SUCCESS,
        segments=[
            ExtractedSegment(
                content=long_text,
                segment_index=0,
                segment_type=SegmentType.PARAGRAPH,
                page_number=1,
            )
        ],
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) > 1

    # Verify sequential chunk ordering
    for idx, c in enumerate(chunks):
        assert c.chunk_index == idx
        assert c.page_number == 1
        assert c.token_count > 0

    # Verify consecutive chunks have content overlap
    c0_words = set(chunks[0].content.split()[-10:])
    c1_words = set(chunks[1].content.split()[:15])
    assert len(c0_words.intersection(c1_words)) > 0


def test_code_chunking_preserves_line_integrity() -> None:
    chunker = DocumentChunker(target_tokens=40, overlap_tokens=10)
    code_lines = [f"    line_{i} = compute_value({i}) + {i * 2}" for i in range(1, 25)]
    code_content = "def sample_function():\n" + "\n".join(code_lines)

    doc = ExtractedDocument(
        file_path="/src/math.py",
        filename="math.py",
        extension=".py",
        file_type="code",
        file_size=len(code_content),
        extraction_status=ExtractionStatus.SUCCESS,
        segments=[
            ExtractedSegment(
                content=code_content,
                segment_index=0,
                segment_type=SegmentType.CODE_BLOCK,
                start_line=1,
                end_line=25,
            )
        ],
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) > 1

    for c in chunks:
        # None of the code lines should be chopped mid-word
        lines = c.content.split("\n")
        for line in lines:
            if line.strip():
                assert "compute_value" in line or "def sample_function" in line


def test_preserves_multi_page_pdf_location_metadata() -> None:
    chunker = DocumentChunker(target_tokens=500, overlap_tokens=80)
    doc = ExtractedDocument(
        file_path="/books/report.pdf",
        filename="report.pdf",
        extension=".pdf",
        file_type="pdf",
        file_size=1500,
        extraction_status=ExtractionStatus.SUCCESS,
        metadata={"title": "Quarterly Report"},
        segments=[
            ExtractedSegment(
                content="Page 1 Content: Financial overview and revenue numbers.",
                segment_index=0,
                segment_type=SegmentType.PAGE,
                page_number=1,
            ),
            ExtractedSegment(
                content="Page 2 Content: Cost breakdowns and operating expenses.",
                segment_index=1,
                segment_type=SegmentType.PAGE,
                page_number=2,
            ),
        ],
    )

    chunks = chunker.chunk_document(doc)
    assert len(chunks) >= 1
    # Check that metadata contains doc_title
    for c in chunks:
        assert c.metadata["doc_title"] == "Quarterly Report"


def test_empty_document_produces_no_chunks() -> None:
    chunker = DocumentChunker(target_tokens=500, overlap_tokens=80)
    doc = ExtractedDocument(
        file_path="/docs/empty.txt",
        filename="empty.txt",
        extension=".txt",
        file_type="text",
        file_size=0,
        extraction_status=ExtractionStatus.EMPTY,
        segments=[],
    )
    chunks = chunker.chunk_document(doc)
    assert len(chunks) == 0

