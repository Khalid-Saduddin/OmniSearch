"""Keyword search API endpoints for executing FTS5 searches."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from app.database.connection import DatabaseConnectionManager
from app.schemas.search import (
    SearchFilter,
    SearchQuery,
    SearchResponse,
)
from app.search.keyword_search import KeywordSearchEngine

router = APIRouter()


def get_search_engine() -> KeywordSearchEngine:
    """Dependency providing a configured KeywordSearchEngine instance."""
    db = DatabaseConnectionManager()
    return KeywordSearchEngine(db=db)


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Execute Keyword Search",
    description="Search indexed documents using SQLite FTS5, BM25 ranking, and metadata filters.",
)
async def execute_search(
    request: SearchQuery,
    engine: KeywordSearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Execute keyword search using structured search request model."""
    return engine.search(request)


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Execute Keyword Search (GET)",
    description="Search indexed documents using query parameters for simple keyword lookups.",
)
async def search_get(
    q: str = Query(..., min_length=1, description="Keyword or phrase query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    file_type: Optional[List[str]] = Query(default=None, description="Optional file type filter(s)"),
    max_chunks_per_file: int = Query(default=3, ge=1, le=50, description="Max chunks per file"),
    engine: KeywordSearchEngine = Depends(get_search_engine),
) -> SearchResponse:
    """Execute keyword search via GET query parameters."""
    filters = SearchFilter(
        file_types=file_type,
        max_chunks_per_file=max_chunks_per_file,
    )
    search_req = SearchQuery(
        query=q,
        filter=filters,
        limit=limit,
        offset=offset,
    )
    return engine.search(search_req)
