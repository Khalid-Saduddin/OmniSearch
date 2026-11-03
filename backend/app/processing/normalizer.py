"""Format-aware text normalization preserving structural boundaries and indentation."""

import re
import unicodedata
from app.schemas.extraction import ExtractedSegment, SegmentType

# Regex to collapse 3 or more consecutive line breaks down to 2
_EXCESSIVE_NEWLINES = re.compile(r"\n{3,}")

# Regex to strip trailing whitespace from individual lines without touching leading indentation
_TRAILING_LINE_WHITESPACE = re.compile(r"[ \t]+$", re.MULTILINE)

# Regex to collapse multiple horizontal spaces (excluding newlines and tabs)
_MULTIPLE_SPACES = re.compile(r"[^\S\r\n\t]{2,}")


class TextNormalizer:
    """Sanitizes and normalizes extracted text according to content structure."""

    @staticmethod
    def strip_control_characters(text: str) -> str:
        """Remove null bytes and non-printable control characters, preserving tab and newline."""
        # Normalize carriage returns before character filtering to prevent \r\n turning into \n\n
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = []
        for ch in text:
            if ch in ("\n", "\t"):
                cleaned.append(ch)
            elif ch == "\x00":
                continue
            else:
                cat = unicodedata.category(ch)
                # Keep letters, numbers, punctuation, symbols, and standard separator spaces
                if not cat.startswith("C"):
                    cleaned.append(ch)
        return "".join(cleaned)

    @classmethod
    def normalize_text(
        cls,
        text: str,
        is_code: bool = False,
        is_table_or_csv: bool = False,
    ) -> str:
        """Normalize textual content while respecting code indentation and table structure.

        Args:
            text: Raw input string.
            is_code: True if content is source code requiring exact indentation preservation.
            is_table_or_csv: True if content represents rows/columns with delimiter structure.

        Returns:
            Cleaned and normalized text.
        """
        if not text:
            return ""

        # 1. Unicode normalization (NFKC decomposes compatibility characters like ligatures)
        normalized = unicodedata.normalize("NFKC", text)

        # 2. Control character removal (null bytes, invalid terminal sequences)
        normalized = cls.strip_control_characters(normalized)

        # 3. Line ending normalization (\r\n and \r -> \n)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Strip trailing whitespace from every line
        normalized = _TRAILING_LINE_WHITESPACE.sub("", normalized)

        # 5. Format-specific whitespace handling
        if is_code:
            # For source code: NEVER strip leading whitespace / tabs, preserve indentation strictly!
            # Only collapse excessive blank lines (more than 2 consecutive blank lines)
            normalized = _EXCESSIVE_NEWLINES.sub("\n\n", normalized)
            return normalized.strip("\n")

        if is_table_or_csv:
            # Preserve pipe | delimiters and row structure
            normalized = _EXCESSIVE_NEWLINES.sub("\n", normalized)
            return normalized.strip()

        # Natural language / Markdown / General text:
        # Collapse multiple horizontal spaces on a single line to a single space
        lines = []
        for line in normalized.split("\n"):
            # Check if line looks like markdown list or quote
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue

            # Check if line has leading list markers (preserve up to 4 spaces for nested lists)
            indent_match = re.match(r"^(\s+)", line)
            leading_indent = indent_match.group(1) if indent_match else ""
            # Only preserve leading indent if it's modest (e.g. 2-4 spaces for bullet points)
            if len(leading_indent) > 4:
                leading_indent = "    "

            collapsed_line = _MULTIPLE_SPACES.sub(" ", stripped)
            lines.append(f"{leading_indent}{collapsed_line}" if leading_indent else collapsed_line)

        joined = "\n".join(lines)
        # Collapse 3+ blank lines into maximum 2 (paragraph break)
        joined = _EXCESSIVE_NEWLINES.sub("\n\n", joined)
        return joined.strip()

    @classmethod
    def normalize_segment(cls, segment: ExtractedSegment, file_type: str = "text") -> ExtractedSegment:
        """Produce a normalized copy of an ExtractedSegment."""
        is_code = (file_type == "code" or segment.segment_type == SegmentType.CODE_BLOCK)
        is_table = (file_type == "csv" or segment.segment_type in (SegmentType.TABLE, SegmentType.ROW))

        normalized_content = cls.normalize_text(
            segment.content,
            is_code=is_code,
            is_table_or_csv=is_table,
        )

        return segment.model_copy(update={"content": normalized_content})
