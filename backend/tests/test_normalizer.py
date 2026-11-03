"""Tests for text normalization, Unicode handling, and format awareness."""

from app.processing.normalizer import TextNormalizer
from app.schemas.extraction import ExtractedSegment, SegmentType


def test_unicode_nfkc_normalization() -> None:
    # Test ligature 'ﬁ' -> 'fi' and fullwidth letters
    ligature_text = "The ﬁrst speciﬁcation"
    normalized = TextNormalizer.normalize_text(ligature_text)
    assert normalized == "The first specification"


def test_control_character_removal() -> None:
    # Null byte and terminal control sequences removed, newlines and tabs kept
    raw_text = "Hello\x00 World!\x07 This is\tvalid\ntext."
    normalized = TextNormalizer.normalize_text(raw_text)
    assert normalized == "Hello World! This is\tvalid\ntext."
    assert "\x00" not in normalized
    assert "\x07" not in normalized


def test_line_ending_normalization() -> None:
    mixed_endings = "Line 1\r\nLine 2\rLine 3\nLine 4"
    normalized = TextNormalizer.normalize_text(mixed_endings)
    assert normalized == "Line 1\nLine 2\nLine 3\nLine 4"


def test_excessive_newlines_collapsed() -> None:
    many_newlines = "Paragraph 1\n\n\n\n\nParagraph 2\n\n\nParagraph 3"
    normalized = TextNormalizer.normalize_text(many_newlines)
    assert normalized == "Paragraph 1\n\nParagraph 2\n\nParagraph 3"


def test_code_indentation_strictly_preserved() -> None:
    code_text = (
        "def compute_total(items):\n"
        "    # Indented 4 spaces\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        total += item.price\n"
        "    return total"
    )
    normalized = TextNormalizer.normalize_text(code_text, is_code=True)
    assert normalized == code_text
    # Verify leading indentation was not stripped
    assert "    total = 0" in normalized
    assert "        total += item.price" in normalized


def test_table_and_csv_pipes_preserved() -> None:
    table_text = (
        "Column 1 | Column 2 | Column 3\n"
        "Row 1 A   | Row 1 B   | Row 1 C\n"
    )
    normalized = TextNormalizer.normalize_text(table_text, is_table_or_csv=True)
    assert "Column 1 | Column 2 | Column 3" in normalized
    assert "Row 1 A" in normalized


def test_normalize_segment_helper() -> None:
    seg = ExtractedSegment(
        content="def hello():\n    return 'world'\r\n",
        segment_index=0,
        segment_type=SegmentType.CODE_BLOCK,
    )
    norm_seg = TextNormalizer.normalize_segment(seg, file_type="code")
    assert norm_seg.content == "def hello():\n    return 'world'"
    assert norm_seg.segment_index == 0


def test_empty_content_returns_empty_string() -> None:
    assert TextNormalizer.normalize_text("") == ""
    assert TextNormalizer.normalize_text("   \n\n   ") == ""
