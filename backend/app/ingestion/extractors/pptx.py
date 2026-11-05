"""PowerPoint presentation (.pptx) extractor using python-pptx."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import pptx

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)


class PptxExtractor(BaseExtractor):
    """Extracts text slide-by-slide from PowerPoint presentations using python-pptx."""

    @property
    def supported_extensions(self) -> Set[str]:
        return {".pptx"}

    @property
    def category(self) -> str:
        return "pptx"

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
            prs = pptx.Presentation(str(path))

            # Core document properties
            try:
                props = prs.core_properties
                doc_metadata = {
                    "title": props.title or None,
                    "author": props.author or None,
                    "slide_count": len(prs.slides),
                    "created": props.created.isoformat() if props.created else None,
                    "modified": props.modified.isoformat() if props.modified else None,
                }
            except Exception as prop_err:
                logger.debug("Could not read PPTX properties for '%s': %s", path.name, prop_err)
                doc_metadata["slide_count"] = len(prs.slides)

            has_any_text = False
            for slide_idx, slide in enumerate(prs.slides):
                slide_num = slide_idx + 1
                slide_texts: List[str] = []
                slide_title: Optional[str] = None

                # Check for standard slide title shape
                if slide.shapes.title and slide.shapes.title.has_text_frame:
                    title_text = slide.shapes.title.text_frame.text.strip()
                    if title_text:
                        slide_title = title_text

                for shape in slide.shapes:
                    # Skip the title shape if we already recorded it
                    if shape == slide.shapes.title:
                        continue

                    # Extract text frame shapes (text boxes, callouts, body placeholders)
                    if shape.has_text_frame:
                        for paragraph in shape.text_frame.paragraphs:
                            para_text = paragraph.text.strip()
                            if para_text:
                                slide_texts.append(para_text)

                    # Extract table shapes inside slides
                    if shape.has_table:
                        for row in shape.table.rows:
                            row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                            if row_cells:
                                slide_texts.append(" | ".join(row_cells))

                # Combine slide text
                combined_parts = []
                if slide_title:
                    combined_parts.append(f"Title: {slide_title}")
                if slide_texts:
                    combined_parts.extend(slide_texts)

                if combined_parts:
                    has_any_text = True
                    slide_content = "\n".join(combined_parts)
                    segments.append(
                        ExtractedSegment(
                            content=slide_content,
                            segment_index=len(segments),
                            segment_type=SegmentType.SLIDE,
                            slide_number=slide_num,
                            metadata={
                                "title": slide_title,
                                "shape_count": len(slide.shapes),
                            },
                        )
                    )

            if not has_any_text:
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
                    error_message="Presentation contains no extractable text across all slides",
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
            logger.error("Error extracting PPTX '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"PPTX extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )

