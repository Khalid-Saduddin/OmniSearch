"""PDF text and structure extractor using PyMuPDF."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import pymupdf

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)


class PdfExtractor(BaseExtractor):
    """Extracts text page by page from PDF documents using PyMuPDF."""

    @property
    def supported_extensions(self) -> Set[str]:
        return {".pdf"}

    @property
    def category(self) -> str:
        return "pdf"

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

        doc: Optional[pymupdf.Document] = None
        segments: List[ExtractedSegment] = []
        doc_metadata: Dict[str, Any] = {}

        try:
            doc = pymupdf.open(str(path))

            # Handle password protection / encryption
            if doc.is_encrypted and not doc.authenticate(""):
                logger.warning("PDF document is encrypted/password-protected: %s", path.name)
                return self.create_failed_document(
                    path,
                    "PDF is encrypted and password-protected",
                    sha256=sha256,
                    file_size=file_size,
                    metadata={"encrypted": True},
                )

            # Extract document-level metadata
            raw_meta = doc.metadata or {}
            doc_metadata = {
                "title": raw_meta.get("title") or None,
                "author": raw_meta.get("author") or None,
                "subject": raw_meta.get("subject") or None,
                "creator": raw_meta.get("creator") or None,
                "producer": raw_meta.get("producer") or None,
                "page_count": len(doc),
            }

            has_any_text = False
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                page_rect = page.rect
                page_meta = {
                    "width": float(page_rect.width),
                    "height": float(page_rect.height),
                    "rotation": page.rotation,
                }

                page_text = page.get_text("text").strip()
                if page_text:
                    has_any_text = True
                    segments.append(
                        ExtractedSegment(
                            content=page_text,
                            segment_index=len(segments),
                            segment_type=SegmentType.PAGE,
                            page_number=page_num,
                            metadata=page_meta,
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
                    error_message="Document contains no extractable text (may be image-only scan)",
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
            logger.error("Error extracting PDF '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"PDF extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )
        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
