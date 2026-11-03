"""HTML document extractor using BeautifulSoup."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from bs4 import BeautifulSoup
import charset_normalizer

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.ingestion.file_detector import HTML_EXTENSIONS
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)

# Elements to discard completely from extraction
DISCARD_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe", "meta", "link"}


class HtmlExtractor(BaseExtractor):
    """Extracts cleaned readable text and semantic sections from HTML documents."""

    @property
    def supported_extensions(self) -> Set[str]:
        return HTML_EXTENSIONS

    @property
    def category(self) -> str:
        return "html"

    def _read_text(self, path: Path) -> tuple[str, str]:
        raw_bytes = path.read_bytes()
        if not raw_bytes:
            return "", "utf-8"
        try:
            return raw_bytes.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            pass

        try:
            matches = charset_normalizer.from_bytes(raw_bytes)
            best = matches.best()
            if best and best.encoding:
                return str(best), best.encoding
        except Exception:
            pass

        return raw_bytes.decode("latin-1", errors="replace"), "latin-1 (fallback)"

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
            html_text, encoding = self._read_text(path)
            if not html_text.strip():
                return self.create_empty_document(
                    path,
                    sha256=sha256,
                    file_size=file_size,
                    metadata={"encoding": encoding},
                )

            soup = BeautifulSoup(html_text, "html.parser")

            # Extract metadata: page title and meta description
            title_tag = soup.find("title")
            doc_title = title_tag.get_text(strip=True) if title_tag else None

            meta_desc = None
            desc_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
            if desc_tag and desc_tag.get("content"):
                meta_desc = desc_tag["content"].strip()

            doc_metadata = {
                "title": doc_title,
                "description": meta_desc,
                "encoding": encoding,
            }

            # Remove unwanted tags
            for unwanted in soup.find_all(DISCARD_TAGS):
                unwanted.decompose()

            # Process meaningful blocks in order: headings, paragraphs, lists, table cells
            content_tags = soup.find_all(
                ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "td", "th"]
            )

            seen_texts: Set[str] = set()

            for tag in content_tags:
                clean_text = tag.get_text(" ", strip=True)
                if not clean_text or clean_text in seen_texts:
                    continue

                seen_texts.add(clean_text)
                is_heading = tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}
                seg_type = SegmentType.HEADING if is_heading else SegmentType.PARAGRAPH

                segments.append(
                    ExtractedSegment(
                        content=clean_text,
                        segment_index=len(segments),
                        segment_type=seg_type,
                        metadata={"tag_name": tag.name},
                    )
                )

            # Fallback if no specific tags found but body has raw text
            if not segments:
                body = soup.find("body") or soup
                fallback_text = body.get_text(" ", strip=True)
                if fallback_text:
                    segments.append(
                        ExtractedSegment(
                            content=fallback_text,
                            segment_index=0,
                            segment_type=SegmentType.TEXT_BLOCK,
                            metadata={"fallback": True},
                        )
                    )

            if not segments:
                return self.create_empty_document(
                    path,
                    sha256=sha256,
                    file_size=file_size,
                    metadata=doc_metadata,
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
            logger.error("Error extracting HTML '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"HTML extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )

