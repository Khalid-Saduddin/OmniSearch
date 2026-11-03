"""Excel spreadsheet (.xlsx) extractor using openpyxl."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import openpyxl

from app.core.logging import get_logger
from app.ingestion.extractors.base import BaseExtractor
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus, SegmentType

logger = get_logger(__name__)


class XlsxExtractor(BaseExtractor):
    """Extracts worksheet text and row data from Excel workbooks using openpyxl.

    Notes on Formulas and Security:
        The workbook is loaded with `data_only=True` to extract pre-evaluated cached values
        where available, preventing code execution. VBA macros and formula scripts are NEVER executed.
    """

    @property
    def supported_extensions(self) -> Set[str]:
        return {".xlsx"}

    @property
    def category(self) -> str:
        return "xlsx"

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
        wb: Optional[openpyxl.Workbook] = None

        try:
            # read_only=True for streaming memory efficiency, data_only=True for cached values
            wb = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)

            sheet_names = wb.sheetnames
            doc_metadata = {
                "sheet_names": sheet_names,
                "sheet_count": len(sheet_names),
                "formula_handling": "cached_values_only",
            }

            has_any_content = False

            for sheet_name in sheet_names:
                sheet = wb[sheet_name]
                sheet_rows: List[str] = []
                sheet_has_text = False

                for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    # Filter out trailing/leading None values
                    formatted_cells = [str(val).strip() if val is not None else "" for val in row]
                    # Check if row has any non-empty content
                    if any(c for c in formatted_cells):
                        sheet_has_text = True
                        has_any_content = True
                        row_line = " | ".join(formatted_cells)
                        sheet_rows.append(f"[Row {row_idx}] {row_line}")

                        # To preserve row-level location while avoiding micro-fragmentation,
                        # we can create individual row segments or structured sheet chunks.
                        segments.append(
                            ExtractedSegment(
                                content=row_line,
                                segment_index=len(segments),
                                segment_type=SegmentType.ROW,
                                sheet_name=sheet_name,
                                row_number=row_idx,
                                metadata={
                                    "sheet_name": sheet_name,
                                    "column_count": len(formatted_cells),
                                },
                            )
                        )

            if not has_any_content:
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
                    error_message="Workbook contains no non-empty cell values across all sheets",
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
            logger.error("Error extracting XLSX '%s': %s", path.name, exc)
            return self.create_failed_document(
                path,
                f"XLSX extraction error: {exc}",
                sha256=sha256,
                file_size=file_size,
                metadata=doc_metadata,
                partial_segments=segments if segments else None,
            )
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass
