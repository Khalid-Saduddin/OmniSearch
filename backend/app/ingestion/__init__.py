"""OmniSearch Document Ingestion and Extraction Engine."""

from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.file_detector import FileTypeDetector
from app.ingestion.hashing import calculate_sha256, try_calculate_sha256
from app.ingestion.registry import ExtractorRegistry, default_registry
from app.ingestion.scanner import FolderScanner

__all__ = [
    "IngestionCoordinator",
    "FileTypeDetector",
    "FolderScanner",
    "ExtractorRegistry",
    "default_registry",
    "calculate_sha256",
    "try_calculate_sha256",
]
