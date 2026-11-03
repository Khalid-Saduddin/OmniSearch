"""Pydantic schemas for keyword search requests, filters, results, and responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SearchFilter(BaseModel):
    """Filtering criteria for narrowing keyword search results."""

    file_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by specific file types (e.g. ['pdf', 'docx', 'code']).",
    )
    folder_ids: Optional[List[int]] = Field(
        default=None,
        description="Filter by indexed folder database IDs.",
    )
    folder_paths: Optional[List[str]] = Field(
        default=None,
        description="Filter by root folder file paths.",
    )
    max_chunks_per_file: Optional[int] = Field(
        default=3,
        ge=1,
        le=50,
        description="Maximum matching chunks to return per file (prevents single-document dominance).",
    )


class SearchQuery(BaseModel):
    """Incoming keyword search query request."""

    query: str = Field(..., min_length=1, description="Raw keyword or phrase search query.")
    filter: Optional[SearchFilter] = Field(default=None, description="Optional search filters.")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of results to return.")
    offset: int = Field(default=0, ge=0, description="Offset for pagination.")


class SearchResultItem(BaseModel):
    """Individual document chunk keyword search match with structural metadata and snippet."""

    file_id: int
    chunk_id: int
    filename: str
    file_path: str
    file_type: str
    file_status: str
    is_stale: bool = Field(
        default=False,
        description="True if previously indexed content was retained after a subsequent re-indexing error.",
    )
    chunk_index: int
    content: str
    snippet: str = Field(..., description="Contextual snippet with highlighted match terms.")
    highlights: List[str] = Field(
        default_factory=list,
        description="Exact terms or phrases matching the search query.",
    )
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    score: float = Field(..., description="Normalized positive relevance score (higher is better).")
    bm25_rank: float = Field(..., description="Raw SQLite FTS5 BM25 rank score (negative value; lower is better).")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom chunk metadata.")


class SearchResponse(BaseModel):
    """Structured keyword search response returned to clients."""

    query: str
    total_results: int
    results: List[SearchResultItem]
    limit: int
    offset: int
    execution_time_ms: float
