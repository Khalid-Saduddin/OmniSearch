"""Tabular CSV and TSV file extractor using standard library csv."""

import csv
from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import charset_normalizer

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.ingestion.file_detector import CSV_EXTENSIONS
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)


class CsvExtractor(BaseExtractor):
    """Extracts structured rows and columns from CSV and TSV files using csv.reader."""

    @property
    def supported_extensions(self) -> Set[str]:
        return CSV_EXTENSIONS

    @property
    def category(self) -> str:
        return "csv"

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
            text_content, detected_encoding = self._read_text(path)
            if not text_content.strip():
                return self.create_empty_document(
                    path,
                    sha256=sha256,
                    file_size=file_size,
                    metadata={"encoding": detected_encoding},
                )

            # Determine delimiter
            sample = text_content[:4096]
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=",\t;|")
                delimiter = dialect.delimiter
            except Exception as sniff_err:
                logger.debug("CSV delimiter sniff failed for '%s', using default: %s", path.name, sniff_err)

            doc_metadata = {
                "encoding": detected_encoding,
                "delimiter": repr(delimiter),
            }

            reader = csv.reader(io.StringIO(text_content), delimiter=delimiter)
            header_row: Optional[List[str]] = None
            total_data_rows = 0

            for row_idx, row in enumerate(reader, start=1):
                clean_cells = [cell.strip() for cell in row]
                if not any(clean_cells):
                    continue

                if header_row is None:
                    header_row = clean_cells
                    doc_metadata["headers"] = header_row
                    doc_metadata["column_count"] = len(header_row)

                total_data_rows += 1
                row_text = " | ".join(clean_cells)

                segments.append(
                    ExtractedSegment(
                        content=row_text,
                        segment_index=len(segments),
                        segment_type=SegmentType.ROW,
                        row_number=row_idx,
                        metadata={
                            "column_count": len(clean_cells),
                            "is_header": (row_idx == 1),
                        },
                    )
                )

            doc_metadata["total_rows"] = total_data_rows

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
            logger.error("Error reading CSV file '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"CSV extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )
