"""Word document (.docx) extractor using python-docx."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import docx

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)


class DocxExtractor(BaseExtractor):
    """Extracts paragraphs and tables from Word (.docx) files using python-docx."""

    @property
    def supported_extensions(self) -> Set[str]:
        return {".docx"}

    @property
    def category(self) -> str:
        return "docx"

    def extract(self, file_path: Path, sha256: Optional[str] = None) -> ExtractedDocument:
        path = Path(file_path).resolve()
        if not path.is_file():
            return self.create_failed_document(path, f"File does not exist: {path}", sha256=sha256)

        try:
            file_size = path.stat().st_size
        except OSError as exc:
            return self.create_failed_document(path, f"Cannot read file stat: {exc}", sha256=sha256)

        if file_size == 0:
            return self.create_empty_document(path, sha256=sha256, file_size=0)

        segments: List[ExtractedSegment] = []
        doc_metadata: Dict[str, Any] = {}

        try:
            doc = docx.Document(str(path))

            # Extract document core properties
            try:
                props = doc.core_properties
                doc_metadata = {
                    "title": props.title or None,
                    "author": props.author or None,
                    "created": props.created.isoformat() if props.created else None,
                    "modified": props.modified.isoformat() if props.modified else None,
                    "comments": props.comments or None,
                    "category": props.category or None,
                }
            except Exception as prop_err:
                logger.debug("Could not read core properties for '%s': %s", path.name, prop_err)

            # Traverse paragraphs and tables preserving logical flow
            # python-docx exposes body elements in order via doc.paragraphs and doc.tables,
            # or traversing doc.element.body
            para_index = 0
            for p in doc.paragraphs:
                text = p.text.strip()
                if not text:
                    continue
                para_index += 1
                is_heading = p.style and p.style.name and p.style.name.startswith("Heading")
                seg_type = SegmentType.HEADING if is_heading else SegmentType.PARAGRAPH

                segments.append(
                    ExtractedSegment(
                        content=text,
                        segment_index=len(segments),
                        segment_type=seg_type,
                        metadata={
                            "paragraph_number": para_index,
                            "style_name": p.style.name if p.style else None,
                        },
                    )
                )

            table_index = 0
            for table in doc.tables:
                table_index += 1
                table_rows: List[str] = []
                for row_idx, row in enumerate(table.rows):
                    row_cells = [cell.text.strip() for cell in row.cells]
                    # Filter duplicate merged cell text in horizontal cells if any
                    row_line = " | ".join(row_cells)
                    if row_line.strip():
                        table_rows.append(row_line)

                if table_rows:
                    table_content = "\n".join(table_rows)
                    segments.append(
                        ExtractedSegment(
                            content=table_content,
                            segment_index=len(segments),
                            segment_type=SegmentType.TABLE,
                            metadata={
                                "table_number": table_index,
                                "row_count": len(table.rows),
                                "column_count": len(table.columns),
                            },
                        )
                    )

            if not segments:
                return ExtractedDocument(
                    file_path=str(path),
                    filename=path.name,
                    extension=path.suffix.lower(),
                    file_type=self.category,
                    file_size=file_size,
                    sha256=sha256,
                    extracted_at=datetime.now(timezone.utc),
                    extraction_status=ExtractionStatus.EMPTY,
                    segments=[],
                    metadata=doc_metadata,
                    error_message="Document contains no extractable paragraphs or tables",
                )

            return ExtractedDocument(
                file_path=str(path),
                filename=path.name,
                extension=path.suffix.lower(),
                file_type=self.category,
                file_size=file_size,
                sha256=sha256,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.SUCCESS,
                segments=segments,
                metadata=doc_metadata,
            )

        except Exception as exc:
            logger.error("Error extracting DOCX '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"DOCX extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )
