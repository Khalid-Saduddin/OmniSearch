"""Search API endpoints for executing FTS5 keyword and ChromaDB semantic searches."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from app.core.config import get_settings
from app.database.connection import DatabaseConnectionManager
from app.embeddings.configuration import EmbeddingConfig
from app.embeddings.embedder import EmbeddingGemmaEmbedder
from app.schemas.search import (
    SearchFilter,
    SearchQuery,
    SearchResponse,
    SemanticSearchQuery,
    SemanticSearchResponse,
)
from app.search.keyword_search import KeywordSearchEngine
from app.search.semantic_search import SemanticSearchEngine
from app.vector_store.chroma import ChromaVectorStore

router = APIRouter()


def get_search_engine() -> KeywordSearchEngine:
    """Dependency providing a configured KeywordSearchEngine instance."""
    db = DatabaseConnectionManager()
    return KeywordSearchEngine(db=db)


def get_semantic_search_engine() -> SemanticSearchEngine:
    """Dependency providing a configured SemanticSearchEngine instance."""
    db = DatabaseConnectionManager()
    settings = get_settings()
    vector_store = ChromaVectorStore(persist_dir=settings.vectors_dir)
    config = EmbeddingConfig(
        model_id=settings.embedding_model_id,
        dimension=settings.embedding_dimension,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
        precision=settings.embedding_precision,
    )
    embedder = EmbeddingGemmaEmbedder(config=config)
    return SemanticSearchEngine(db=db, vector_store=vector_store, embedder=embedder)


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


@router.post(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    summary="Execute Semantic Search",
    description="Search indexed documents using dense vector similarity retrieval powered by ChromaDB.",
)
async def execute_semantic_search(
    request: SemanticSearchQuery,
    engine: SemanticSearchEngine = Depends(get_semantic_search_engine),
) -> SemanticSearchResponse:
    """Execute semantic vector search using structured request model."""
    return engine.search(request)


@router.get(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    summary="Execute Semantic Search (GET)",
    description="Search indexed documents using natural language query parameters via ChromaDB.",
)
async def semantic_search_get(
    q: str = Query(..., min_length=1, description="Natural language semantic search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    min_similarity: float = Query(
        default=-1.0, ge=-1.0, le=1.0, description="Minimum cosine similarity threshold"
    ),
    file_type: Optional[List[str]] = Query(default=None, description="Optional file type filter(s)"),
    max_chunks_per_file: int = Query(default=3, ge=1, le=50, description="Max chunks per file"),
    engine: SemanticSearchEngine = Depends(get_semantic_search_engine),
) -> SemanticSearchResponse:
    """Execute semantic vector search via GET query parameters."""
    filters = SearchFilter(
        file_types=file_type,
        max_chunks_per_file=max_chunks_per_file,
    )
    search_req = SemanticSearchQuery(
        query=q,
        filter=filters,
        limit=limit,
        offset=offset,
        min_similarity=min_similarity,
    )
    return engine.search(search_req)
