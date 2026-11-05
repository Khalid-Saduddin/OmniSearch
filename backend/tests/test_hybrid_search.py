"""Comprehensive integration tests for HybridSearchEngine, RRF ranking, degraded modes, and API endpoints."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.search import get_hybrid_search_engine
from app.database.connection import DatabaseConnectionManager
from app.database.migrations import apply_migrations
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.embeddings.test_embedder import DeterministicTestEmbedder
from app.main import create_app
from app.schemas.extraction import ExtractionStatus
from app.schemas.processing import DocumentChunk, FileRecord
from app.schemas.search import (
    HybridSearchQuery,
    HybridSearchResponse,
    SearchFilter,
)
from app.search.hybrid_search import HybridSearchEngine
from app.search.keyword_search import KeywordSearchEngine
from app.search.semantic_search import SemanticSearchEngine
from app.vector_store.chroma import ChromaVectorStore


@pytest.fixture
def hybrid_env(tmp_path: Path):
    """Setup populated SQLite database (FTS5) and ChromaVectorStore for hybrid search."""
    db_file = tmp_path / "hybrid_test.db"
    db = DatabaseConnectionManager(db_path=db_file)
    with db.connection() as conn:
        apply_migrations(conn)

    vector_store = ChromaVectorStore(
        persist_dir=tmp_path / "vectors", collection_name="test_hybrid_search"
    )
    embedder = DeterministicTestEmbedder(dimension=256)

    # Populate SQLite tables: folders, files, chunks (FTS triggers sync automatically)
    with db.transaction() as conn:
        folder_ai = FolderRepository.get_or_create(conn, str(tmp_path / "docs" / "ai"))
        folder_db = FolderRepository.get_or_create(conn, str(tmp_path / "docs" / "db"))

        # File 1: PDF AI paper
        f1 = FileRecord(
            folder_id=folder_ai.id,
            path=str(tmp_path / "docs" / "ai" / "transformers.pdf"),
            filename="transformers.pdf",
            extension=".pdf",
            file_type="pdf",
            status=ExtractionStatus.SUCCESS.value,
            modified_at="2026-11-04T12:00:00Z",
        )
        fid1 = FileRepository.upsert(conn, f1)
        chunks1 = [
            DocumentChunk(
                chunk_index=0,
                content="Deep learning transformer neural networks and multi-head self-attention mechanism.",
                token_count=12,
                page_number=1,
            ),
            DocumentChunk(
                chunk_index=1,
                content="Positional encoding vectors and gradient descent backpropagation training.",
                token_count=10,
                page_number=2,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid1, chunks1)

        # File 2: DOCX Database manual
        f2 = FileRecord(
            folder_id=folder_db.id,
            path=str(tmp_path / "docs" / "db" / "databases.docx"),
            filename="databases.docx",
            extension=".docx",
            file_type="docx",
            status=ExtractionStatus.SUCCESS.value,
            modified_at="2026-11-04T12:00:00Z",
        )
        fid2 = FileRepository.upsert(conn, f2)
        chunks2 = [
            DocumentChunk(
                chunk_index=0,
                content="Relational database normalization SQL indexing and ACID transaction guarantees.",
                token_count=11,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid2, chunks2)

        # File 3: Stale Text file (failed reindex)
        f3 = FileRecord(
            folder_id=folder_ai.id,
            path=str(tmp_path / "docs" / "ai" / "stale_report.txt"),
            filename="stale_report.txt",
            extension=".txt",
            file_type="text",
            status=ExtractionStatus.FAILED.value,
            modified_at="2026-11-04T12:00:00Z",
        )
        fid3 = FileRepository.upsert(conn, f3)
        chunks3 = [
            DocumentChunk(
                chunk_index=0,
                content="Quarterly financial performance earnings summary and revenue metrics.",
                token_count=9,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid3, chunks3)

    # Sync chunks to Chroma vector store
    with db.connection() as conn:
        all_chunks = []
        for fid, fn, ft, fld in [
            (fid1, "transformers.pdf", "pdf", folder_ai.id),
            (fid2, "databases.docx", "docx", folder_db.id),
            (fid3, "stale_report.txt", "text", folder_ai.id),
        ]:
            db_chunks = ChunkRepository.get_by_file_id(conn, fid)
            for c in db_chunks:
                all_chunks.append((c, fid, fn, ft, fld))

    c_ids = [c[0].id for c in all_chunks]
    c_docs = [c[0].content for c in all_chunks]
    c_metas = [
        {"file_id": c[1], "filename": c[2], "file_type": c[3], "folder_id": c[4]}
        for c in all_chunks
    ]
    embeddings = embedder.embed_documents(c_docs)
    vector_store.upsert(
        chunk_ids=c_ids,
        embeddings=embeddings,
        metadatas=c_metas,
        documents=c_docs,
    )

    kw_engine = KeywordSearchEngine(db=db)
    sem_engine = SemanticSearchEngine(db=db, vector_store=vector_store, embedder=embedder)
    hybrid_engine = HybridSearchEngine(
        db=db,
        keyword_engine=kw_engine,
        semantic_engine=sem_engine,
        use_concurrency=True,
    )

    return hybrid_engine, kw_engine, sem_engine, db


def test_hybrid_search_fusion_ranking(hybrid_env):
    """Verify hybrid search executes both engines, computes RRF scores, and ranks descending."""
    hybrid_engine, _, _, _ = hybrid_env
    response = hybrid_engine.search("transformer neural networks")

    assert isinstance(response, HybridSearchResponse)
    assert response.search_mode == "hybrid"
    assert response.keyword_available is True
    assert response.semantic_available is True
    assert response.total_results >= 1

    # Verify RRF scores strictly descend
    rrf_scores = [r.rrf_score for r in response.results]
    assert rrf_scores == sorted(rrf_scores, reverse=True)

    # Check top item properties
    top_item = response.results[0]
    assert top_item.filename == "transformers.pdf"
    assert top_item.rrf_score > 0.0
    # Both engines found it, so both ranks should be present
    assert top_item.keyword_rank is not None
    assert top_item.semantic_rank is not None
    assert top_item.bm25_score is not None
    assert top_item.cosine_similarity is not None


def test_hybrid_search_empty_query(hybrid_env):
    """Verify empty query string returns 0 results cleanly."""
    hybrid_engine, _, _, _ = hybrid_env
    res = hybrid_engine.search("   ")
    assert res.total_results == 0
    assert len(res.results) == 0
    assert res.search_mode == "hybrid"


def test_hybrid_search_degraded_semantic_unavailable(hybrid_env):
    """Verify fallback to keyword-only mode when semantic engine is None or raises."""
    _, kw_engine, _, db = hybrid_env

    # Hybrid engine with no semantic engine
    engine = HybridSearchEngine(
        db=db,
        keyword_engine=kw_engine,
        semantic_engine=None,
        use_concurrency=False,
    )
    res = engine.search("transformer")

    assert res.search_mode == "keyword_only"
    assert res.keyword_available is True
    assert res.semantic_available is False
    assert res.total_results >= 1
    assert res.results[0].keyword_rank == 1
    assert res.results[0].semantic_rank is None
    assert res.results[0].cosine_similarity is None
    assert res.results[0].bm25_score is not None


def test_hybrid_search_degraded_keyword_unavailable(hybrid_env):
    """Verify fallback to semantic-only mode when keyword engine is None or raises."""
    _, _, sem_engine, db = hybrid_env

    # Hybrid engine with no keyword engine
    engine = HybridSearchEngine(
        db=db,
        keyword_engine=None,
        semantic_engine=sem_engine,
        use_concurrency=False,
    )
    res = engine.search("database normalization")

    assert res.search_mode == "semantic_only"
    assert res.keyword_available is False
    assert res.semantic_available is True
    assert res.total_results >= 1
    assert res.results[0].semantic_rank == 1
    assert res.results[0].keyword_rank is None
    assert res.results[0].cosine_similarity is not None
    assert res.results[0].bm25_score is None


def test_hybrid_search_both_unavailable(hybrid_env):
    """Verify unavailable search mode when both engines are unavailable."""
    _, _, _, db = hybrid_env

    engine = HybridSearchEngine(
        db=db,
        keyword_engine=None,
        semantic_engine=None,
        use_concurrency=False,
    )
    res = engine.search("test query")

    assert res.search_mode == "unavailable"
    assert res.keyword_available is False
    assert res.semantic_available is False
    assert res.total_results == 0
    assert len(res.results) == 0


def test_hybrid_search_engine_runtime_exception_handling(hybrid_env):
    """Verify graceful fallback when an engine raises a runtime exception."""
    from unittest.mock import MagicMock
    _, kw_engine, sem_engine, db = hybrid_env

    failing_sem_engine = MagicMock()
    failing_sem_engine.search.side_effect = RuntimeError("ChromaDB connection dropped")

    engine = HybridSearchEngine(
        db=db,
        keyword_engine=kw_engine,
        semantic_engine=failing_sem_engine,
        use_concurrency=True,
    )
    res = engine.search("transformer")

    assert res.search_mode == "keyword_only"
    assert res.keyword_available is True
    assert res.semantic_available is False
    assert res.total_results >= 1


def test_hybrid_search_file_type_filtering(hybrid_env):
    """Verify file_types filter applies to candidate generation."""
    hybrid_engine, _, _, _ = hybrid_env

    filters = SearchFilter(file_types=["docx"])
    res = hybrid_engine.search("database normalization", filters=filters)

    assert res.total_results >= 1
    for r in res.results:
        assert r.file_type == "docx"


def test_hybrid_search_limit_and_offset(hybrid_env):
    """Verify pagination limit and offset correctly partition fused results."""
    hybrid_engine, _, _, _ = hybrid_env

    res_all = hybrid_engine.search("learning database financial", limit=10, offset=0)
    if res_all.total_results >= 2:
        res_page1 = hybrid_engine.search("learning database financial", limit=1, offset=0)
        res_page2 = hybrid_engine.search("learning database financial", limit=1, offset=1)

        assert len(res_page1.results) == 1
        assert len(res_page2.results) == 1
        assert res_page1.results[0].chunk_id != res_page2.results[0].chunk_id
        assert res_page1.results[0].chunk_id == res_all.results[0].chunk_id
        assert res_page2.results[0].chunk_id == res_all.results[1].chunk_id


def test_hybrid_search_custom_rrf_k(hybrid_env):
    """Verify rrf_k configuration influences score calculation without error."""
    hybrid_engine, _, _, _ = hybrid_env

    res_k10 = hybrid_engine.search("transformer", rrf_k=10)
    res_k100 = hybrid_engine.search("transformer", rrf_k=100)

    assert res_k10.rrf_k == 10
    assert res_k100.rrf_k == 100
    # Lower k produces larger 1/(k+rank) scores
    assert res_k10.results[0].rrf_score > res_k100.results[0].rrf_score


def test_hybrid_search_stale_flag_preservation(hybrid_env):
    """Verify is_stale=True flag is preserved for chunks belonging to failed file re-indexing."""
    hybrid_engine, _, _, _ = hybrid_env
    res = hybrid_engine.search("Quarterly financial performance earnings")

    stale_items = [r for r in res.results if r.filename == "stale_report.txt"]
    assert len(stale_items) >= 1
    assert stale_items[0].is_stale is True


def test_hybrid_search_api_post_endpoint(hybrid_env):
    """Verify HTTP POST /api/v1/search/hybrid endpoint."""
    hybrid_engine, _, _, _ = hybrid_env
    app = create_app()
    app.dependency_overrides[get_hybrid_search_engine] = lambda: hybrid_engine

    client = TestClient(app)
    payload = {
        "query": "transformer self-attention",
        "limit": 5,
        "offset": 0,
        "rrf_k": 60,
    }
    response = client.post("/api/v1/search/hybrid", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "transformer self-attention"
    assert data["total_results"] >= 1
    assert data["search_mode"] in ("hybrid", "keyword_only", "semantic_only")
    assert isinstance(data["results"], list)
    first_result = data["results"][0]
    assert "chunk_id" in first_result
    assert "rrf_score" in first_result
    assert "keyword_rank" in first_result
    assert "semantic_rank" in first_result


def test_hybrid_search_api_get_endpoint(hybrid_env):
    """Verify HTTP GET /api/v1/search/hybrid endpoint."""
    hybrid_engine, _, _, _ = hybrid_env
    app = create_app()
    app.dependency_overrides[get_hybrid_search_engine] = lambda: hybrid_engine

    client = TestClient(app)
    response = client.get("/api/v1/search/hybrid?q=database&limit=2&rrf_k=50")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "database"
    assert data["rrf_k"] == 50
    assert len(data["results"]) <= 2
    assert "search_mode" in data
