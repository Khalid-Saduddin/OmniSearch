"""Pydantic schemas for API request and response data models."""

from app.schemas.health import HealthResponse
from app.schemas.extraction import (
    ExtractedDocument,
    ExtractedSegment,
    ExtractionBatchSummary,
    ExtractionStatus,
    ScanReport,
    ScannedFile,
    SegmentType,
)
from app.schemas.processing import (
    ChunkRecord,
    DocumentChunk,
    FileRecord,
    FolderRecord,
    IndexJobRecord,
    IndexJobStatus,
)
from app.schemas.search import (
    HybridSearchQuery,
    HybridSearchResponse,
    HybridSearchResultItem,
    SearchFilter,
    SearchQuery,
    SearchResultItem,
    SearchResponse,
    SemanticSearchQuery,
    SemanticSearchResultItem,
    SemanticSearchResponse,
)

__all__ = [
    "HealthResponse",
    "ExtractedDocument",
    "ExtractedSegment",
    "ExtractionBatchSummary",
    "ExtractionStatus",
    "ScanReport",
    "ScannedFile",
    "SegmentType",
    "DocumentChunk",
    "FolderRecord",
    "FileRecord",
    "ChunkRecord",
    "IndexJobRecord",
    "IndexJobStatus",
    "SearchFilter",
    "SearchQuery",
    "SearchResultItem",
    "SearchResponse",
    "SemanticSearchQuery",
    "SemanticSearchResultItem",
    "SemanticSearchResponse",
    "HybridSearchQuery",
    "HybridSearchResultItem",
    "HybridSearchResponse",
]
