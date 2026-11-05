"""Plain text, Markdown, and source code extractor with charset normalization."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import charset_normalizer

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.ingestion.file_detector import CODE_EXTENSIONS, MARKDOWN_EXTENSIONS, TEXT_EXTENSIONS
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)

# Segment size in lines for long text and source files
SEGMENT_LINE_CHUNK = 80


class TextExtractor(BaseExtractor):
    """Extracts text, markdown, and source code while preserving line references and encodings."""

    @property
    def supported_extensions(self) -> Set[str]:
        return TEXT_EXTENSIONS | MARKDOWN_EXTENSIONS | CODE_EXTENSIONS

    @property
    def category(self) -> str:
        return "text"

    def get_specific_category(self, extension: str) -> str:
        """Determine specialized category: 'markdown', 'code', or 'text'."""
        ext = extension.lower()
        if ext in MARKDOWN_EXTENSIONS:
            return "markdown"
        if ext in CODE_EXTENSIONS:
            return "code"
        return "text"

    def _detect_and_read(self, path: Path) -> tuple[str, str]:
        """Detect encoding and decode file contents safely without crashing.

        Returns:
            Tuple of (decoded_text, detected_encoding_name)
        """
        raw_bytes = path.read_bytes()
        if not raw_bytes:
            return "", "utf-8"

        # First attempt standard UTF-8 (fastest path for 90%+ modern code/text)
        try:
            return raw_bytes.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass

        # Use charset_normalizer to accurately identify legacy/regional encodings
        try:
            matches = charset_normalizer.from_bytes(raw_bytes)
            best_match = matches.best()
            if best_match and best_match.encoding:
                return str(best_match), best_match.encoding
        except Exception as norm_err:
            logger.debug("Charset normalization fallback on '%s': %s", path.name, norm_err)

        # Fallback to windows-1252 / latin-1 with replacement to guarantee zero data loss crash
        return raw_bytes.decode("latin-1", errors="replace"), "latin-1 (fallback)"

    def extract(self, file_path: Path, sha256: Optional[str] = None) -> ExtractedDocument:
        path = Path(file_path).resolve()
        if not path.is_file():
            return self.create_failed_document(path, f"File does not exist: {path}", sha256=sha256)

        try:
            file_size = path.stat().st_size
        except OSError as exc:
            return self.create_failed_document(path, f"Cannot read file stat: {exc}", sha256=sha256)

        specific_cat = self.get_specific_category(path.suffix)

        if file_size == 0:
            return ExtractedDocument(
                file_path=str(path),
                filename=path.name,
                extension=path.suffix.lower(),
                file_type=specific_cat,
                file_size=0,
                sha256=sha256,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.EMPTY,
                segments=[],
                metadata={"total_lines": 0, "encoding": "utf-8"},
                error_message=None,
            )

        segments: List[ExtractedSegment] = []
        doc_metadata: Dict[str, Any] = {}

        try:
            full_text, detected_encoding = self._detect_and_read(path)
            lines = full_text.splitlines(keepends=True)
            total_lines = len(lines)

            doc_metadata = {
                "total_lines": total_lines,
                "encoding": detected_encoding,
                "format_flavor": specific_cat,
            }

            if not full_text.strip():
                return ExtractedDocument(
                    file_path=str(path),
                    filename=path.name,
                    extension=path.suffix.lower(),
                    file_type=specific_cat,
                    file_size=file_size,
                    sha256=sha256,
                    extracted_at=datetime.now(timezone.utc),
                    extraction_status=ExtractionStatus.EMPTY,
                    segments=[],
                    metadata=doc_metadata,
                    error_message="File contains only whitespace",
                )

            # Determine segment type based on file type
            if specific_cat == "code":
                default_seg_type = SegmentType.CODE_BLOCK
            elif specific_cat == "markdown":
                default_seg_type = SegmentType.PARAGRAPH
            else:
                default_seg_type = SegmentType.TEXT_BLOCK

            # Chunk into structural segments preserving exact line number offsets
            for i in range(0, total_lines, SEGMENT_LINE_CHUNK):
                chunk_lines = lines[i : i + SEGMENT_LINE_CHUNK]
                chunk_text = "".join(chunk_lines).strip()
                if not chunk_text:
                    continue

                start_line = i + 1
                end_line = min(i + len(chunk_lines), total_lines)

                segments.append(
                    ExtractedSegment(
                        content=chunk_text,
                        segment_index=len(segments),
                        segment_type=default_seg_type,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={
                            "line_count": len(chunk_lines),
                        },
                    )
                )

            return ExtractedDocument(
                file_path=str(path),
                filename=path.name,
                extension=path.suffix.lower(),
                file_type=specific_cat,
                file_size=file_size,
                sha256=sha256,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.SUCCESS,
                segments=segments,
                metadata=doc_metadata,
            )

        except Exception as exc:
            logger.error("Error reading text file '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"Text extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )

