"""Central ingestion coordinator orchestrating hashing, validation, and multi-format extraction."""

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Iterable, List, Optional, Union
from app.core.logging import get_logger
from app.ingestion.file_detector import FileTypeDetector
from app.ingestion.hashing import try_calculate_sha256
from app.ingestion.registry import ExtractorRegistry, default_registry
from app.schemas.extraction import (
    ExtractedDocument,
    ExtractionBatchSummary,
    ExtractionStatus,
    ScannedFile,
)

logger = get_logger(__name__)


class IngestionCoordinator:
    """Orchestrates document extraction across multiple files with complete fault isolation."""

    def __init__(self, registry: Optional[ExtractorRegistry] = None) -> None:
        self.registry = registry or default_registry

    def extract_document(
        self,
        file_path: Union[str, Path, ScannedFile],
        compute_hash: bool = True,
        precomputed_sha256: Optional[str] = None,
    ) -> ExtractedDocument:
        """Extract a single document with full exception isolation.

        Args:
            file_path: File system path or ScannedFile object.
            compute_hash: Whether to calculate the streaming SHA-256 hash if not precomputed.
            precomputed_sha256: Pre-computed SHA-256 hex string to avoid redundant hashing.

        Returns:
            ExtractedDocument populated with results, status, segments, and error messages if any.
        """
        if isinstance(file_path, ScannedFile):
            target_path = file_path.path.resolve()
        else:
            target_path = Path(file_path).resolve()

        if not target_path.exists():
            return ExtractedDocument(
                file_path=str(target_path),
                filename=target_path.name,
                extension=target_path.suffix.lower(),
                file_type="unknown",
                file_size=0,
                sha256=None,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.FAILED,
                segments=[],
                metadata={},
                error_message=f"File does not exist: {target_path}",
            )

        try:
            file_size = target_path.stat().st_size
        except (OSError, PermissionError) as exc:
            return ExtractedDocument(
                file_path=str(target_path),
                filename=target_path.name,
                extension=target_path.suffix.lower(),
                file_type="unknown",
                file_size=0,
                sha256=None,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.FAILED,
                segments=[],
                metadata={},
                error_message=f"Permission or I/O error checking file stat: {exc}",
            )

        # Compute SHA-256 hash safely using streaming chunks if not precomputed
        sha256_hash: Optional[str] = None
        if precomputed_sha256 is not None:
            sha256_hash = precomputed_sha256
        elif compute_hash:
            sha256_hash = try_calculate_sha256(target_path)

        # 1. Inspect signature and extension validation
        is_valid, category, error_reason = FileTypeDetector.validate_file(target_path)
        if not is_valid:
            logger.warning("File validation rejected '%s': %s", target_path.name, error_reason)
            return ExtractedDocument(
                file_path=str(target_path),
                filename=target_path.name,
                extension=target_path.suffix.lower(),
                file_type=category,
                file_size=file_size,
                sha256=sha256_hash,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=(
                    ExtractionStatus.UNSUPPORTED
                    if category == "unsupported"
                    else ExtractionStatus.FAILED
                ),
                segments=[],
                metadata={},
                error_message=error_reason or "File signature validation failed",
            )

        # 2. Look up registered extractor
        extractor = self.registry.get_extractor_for_file(target_path)
        if not extractor:
            logger.info("No registered extractor for extension '%s'", target_path.suffix)
            return ExtractedDocument(
                file_path=str(target_path),
                filename=target_path.name,
                extension=target_path.suffix.lower(),
                file_type=category,
                file_size=file_size,
                sha256=sha256_hash,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.UNSUPPORTED,
                segments=[],
                metadata={},
                error_message=f"No extractor registered for '{target_path.suffix.lower()}'",
            )

        # 3. Execute extraction with complete exception containment
        try:
            logger.debug("Executing extractor '%s' for '%s'", extractor.__class__.__name__, target_path.name)
            result = extractor.extract(target_path, sha256=sha256_hash)
            return result
        except Exception as exc:
            logger.error("Unhandled extractor exception on '%s': %s", target_path.name, exc, exc_info=True)
            return ExtractedDocument(
                file_path=str(target_path),
                filename=target_path.name,
                extension=target_path.suffix.lower(),
                file_type=category,
                file_size=file_size,
                sha256=sha256_hash,
                extracted_at=datetime.now(timezone.utc),
                extraction_status=ExtractionStatus.FAILED,
                segments=[],
                metadata={},
                error_message=f"Extraction crashed with unexpected error: {exc}",
            )

    def extract_batch(
        self,
        files: Iterable[Union[str, Path, ScannedFile]],
        compute_hash: bool = True,
    ) -> ExtractionBatchSummary:
        """Process an iterable collection of files sequentially, isolating any failure.

        Args:
            files: Collection of file paths or ScannedFile objects.
            compute_hash: Whether to calculate streaming SHA-256 for each document.

        Returns:
            ExtractionBatchSummary aggregating individual results and operational counts.
        """
        start_time = time.perf_counter()
        documents: List[ExtractedDocument] = []

        successful = 0
        partial = 0
        failed = 0
        empty = 0
        unsupported = 0

        for item in files:
            doc = self.extract_document(item, compute_hash=compute_hash)
            documents.append(doc)

            if doc.extraction_status == ExtractionStatus.SUCCESS:
                successful += 1
            elif doc.extraction_status == ExtractionStatus.PARTIAL:
                partial += 1
            elif doc.extraction_status == ExtractionStatus.EMPTY:
                empty += 1
            elif doc.extraction_status == ExtractionStatus.UNSUPPORTED:
                unsupported += 1
            elif doc.extraction_status == ExtractionStatus.FAILED:
                failed += 1

        duration = time.perf_counter() - start_time

        summary = ExtractionBatchSummary(
            total_files=len(documents),
            successful=successful,
            partial=partial,
            failed=failed,
            empty=empty,
            unsupported=unsupported,
            documents=documents,
            duration_seconds=round(duration, 4),
        )

        logger.info(
            "Batch extraction finished in %.2fs: %d total, %d success, %d partial, %d empty, %d failed, %d unsupported",
            duration,
            summary.total_files,
            summary.successful,
            summary.partial,
            summary.empty,
            summary.failed,
            summary.unsupported,
        )

        return summary

