"""Abstract base interface for all document format extractors."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.core.logging import get_logger
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, ExtractionStatus

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """Abstract base class establishing the contract for document extractors."""

    @property
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """Set of lowercased file extensions (with leading dot) handled by this extractor."""
        raise NotImplementedError

    @property
    @abstractmethod
    def category(self) -> str:
        """Categorical identifier for this format family (e.g. 'pdf', 'docx', 'code')."""
        raise NotImplementedError

    def can_extract(self, file_path: Path) -> bool:
        """Determine whether this extractor supports the given file path based on extension."""
        return Path(file_path).suffix.lower() in self.supported_extensions

    @abstractmethod
    def extract(self, file_path: Path, sha256: Optional[str] = None) -> ExtractedDocument:
        """Extract textual content, structure, and metadata from a target file.

        Args:
            file_path: Absolute or relative Path to target file.
            sha256: Pre-computed or optional SHA-256 digest string.

        Returns:
            ExtractedDocument instance populated with extracted segments and metadata.
        """
        raise NotImplementedError

    def create_empty_document(
        self,
        file_path: Path,
        sha256: Optional[str] = None,
        file_size: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractedDocument:
        """Utility helper to produce an ExtractedDocument representing an empty file."""
        path = Path(file_path).resolve()
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
            metadata=metadata or {},
            error_message=None,
        )

    def create_failed_document(
        self,
        file_path: Path,
        error_message: str,
        sha256: Optional[str] = None,
        file_size: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        partial_segments: Optional[List[ExtractedSegment]] = None,
    ) -> ExtractedDocument:
        """Utility helper to produce an ExtractedDocument representing a failure or partial extraction."""
        path = Path(file_path).resolve()
        status = ExtractionStatus.PARTIAL if partial_segments else ExtractionStatus.FAILED
        return ExtractedDocument(
            file_path=str(path),
            filename=path.name,
            extension=path.suffix.lower(),
            file_type=self.category,
            file_size=file_size,
            sha256=sha256,
            extracted_at=datetime.now(timezone.utc),
            extraction_status=status,
            segments=partial_segments or [],
            metadata=metadata or {},
            error_message=error_message,
        )
