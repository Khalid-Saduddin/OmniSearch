"""Automated tests for SemanticSearchEngine, metadata joining, ranking, and API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.search import get_semantic_search_engine
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
    SearchFilter,
    SemanticSearchQuery,
    SemanticSearchResponse,
)
from app.search.semantic_search import SemanticSearchEngine
from app.services.semantic_pipeline import SemanticPipeline
from app.vector_store.chroma import ChromaVectorStore


@pytest.fixture
def setup_search_env(tmp_path):
    """Setup a populated SQLite database and ChromaVectorStore with test documents."""
    db_file = tmp_path / "test_search.db"
    db = DatabaseConnectionManager(db_path=db_file)
    with db.transaction() as conn:
        apply_migrations(conn)

    vector_store = ChromaVectorStore(
        persist_dir=tmp_path / "vectors", collection_name="test_search_engine"
    )
    embedder = DeterministicTestEmbedder(dimension=256)

    # Populate files and chunks in SQLite
    with test_db_session(db) as conn:
        folder_a = FolderRepository.get_or_create(conn, str(tmp_path / "folder_a"))
        folder_b = FolderRepository.get_or_create(conn, str(tmp_path / "folder_b"))

        # File 1: AI document in folder A (PDF)
        file1 = FileRecord(
            folder_id=folder_a.id,
            path=str(tmp_path / "folder_a" / "ai_paper.pdf"),
            filename="ai_paper.pdf",
            extension=".pdf",
            file_type="pdf",
            modified_at="2026-11-04T12:00:00Z",
            status=ExtractionStatus.SUCCESS.value,
        )
        fid1 = FileRepository.upsert(conn, file1)
        chunks1 = [
            DocumentChunk(
                chunk_index=0,
                content="Deep learning and artificial intelligence neural networks architectures.",
                token_count=10,
                char_count=70,
                page_number=1,
            ),
            DocumentChunk(
                chunk_index=1,
                content="Attention mechanisms and transformer layers in natural language processing.",
                token_count=10,
                char_count=72,
                page_number=2,
            ),
            DocumentChunk(
                chunk_index=2,
                content="Backpropagation gradient descent optimization algorithms.",
                token_count=8,
                char_count=60,
                page_number=3,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid1, chunks1)

        # File 2: Database document in folder B (DOCX)
        file2 = FileRecord(
            folder_id=folder_b.id,
            path=str(tmp_path / "folder_b" / "databases.docx"),
            filename="databases.docx",
            extension=".docx",
            file_type="docx",
            modified_at="2026-11-04T12:00:00Z",
            status=ExtractionStatus.SUCCESS.value,
        )
        fid2 = FileRepository.upsert(conn, file2)
        chunks2 = [
            DocumentChunk(
                chunk_index=0,
                content="Relational database normalization SQL indexing and ACID transactions.",
                token_count=10,
                char_count=71,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid2, chunks2)

        # File 3: Stale failed reindexing file (previously committed content retained)
        file3 = FileRecord(
            folder_id=folder_a.id,
            path=str(tmp_path / "folder_a" / "stale_report.txt"),
            filename="stale_report.txt",
            extension=".txt",
            file_type="text",
            modified_at="2026-11-04T12:00:00Z",
            status=ExtractionStatus.FAILED.value,  # Stale state
        )
        fid3 = FileRepository.upsert(conn, file3)
        chunks3 = [
            DocumentChunk(
                chunk_index=0,
                content="Retained financial report quarterly earnings overview.",
                token_count=8,
                char_count=52,
            ),
        ]
        ChunkRepository.insert_chunks(conn, fid3, chunks3)

    # Sync vectors to ChromaDB
    # Note: To index File 3 in Chroma despite failed status for this test, insert manually
    pipeline = SemanticPipeline(db=db, embedder=embedder, vector_store=vector_store)
    pipeline.sync_embeddings()

    # Manually add file 3's chunk to Chroma to test stale detection
    with db.connection() as conn:
        f3_chunks = ChunkRepository.get_by_file_id(conn, fid3)
        if f3_chunks:
            c3 = f3_chunks[0]
            vector_store.upsert(
                chunk_ids=[c3.id],
                embeddings=embedder.embed_documents([c3.content]),
                metadatas=[{"file_id": fid3, "filename": "stale_report.txt", "file_type": "text", "folder_id": folder_a.id}],
                documents=[c3.content],
            )

    engine = SemanticSearchEngine(db=db, vector_store=vector_store, embedder=embedder)
    return engine, db, vector_store, embedder


class test_db_session:
    """Helper context manager for test database transactions."""

    def __init__(self, db: DatabaseConnectionManager):
        self.db = db
        self.conn = None

    def __enter__(self):
        self._ctx = self.db.transaction()
        self.conn = self._ctx.__enter__()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._ctx.__exit__(exc_type, exc_val, exc_tb)


def test_semantic_search_empty_query(setup_search_env):
    """Verify empty query returns 0 results cleanly."""
    engine, _, _, _ = setup_search_env
    res = engine.search("   ")
    assert res.total_results == 0
    assert len(res.results) == 0


def test_semantic_search_retrieval(setup_search_env):
    """Verify semantic search retrieves relevant chunks with normalized scores."""
    engine, _, _, _ = setup_search_env
    res = engine.search("neural networks and deep learning")

    assert res.total_results > 0
    top = res.results[0]
    assert 0.0 <= top.score <= 1.0
    assert -1.0 <= top.cosine_similarity <= 1.0
    assert top.filename in ("ai_paper.pdf", "databases.docx", "stale_report.txt")
    assert top.snippet != ""


def test_semantic_search_file_type_filtering(setup_search_env):
    """Verify metadata filtering by file_type."""
    engine, _, _, _ = setup_search_env
    query = SemanticSearchQuery(
        query="relational database SQL transactions",
        filter=SearchFilter(file_types=["docx"]),
    )
    res = engine.search(query)
    assert len(res.results) > 0
    for item in res.results:
        assert item.file_type == "docx"


def test_semantic_search_folder_id_filtering(setup_search_env):
    """Verify metadata filtering by folder_id."""
    engine, db, _, _ = setup_search_env
    with db.connection() as conn:
        folder_a = FolderRepository.get_by_id(conn, 1)
        assert folder_a is not None

    query = SemanticSearchQuery(
        query="artificial intelligence",
        filter=SearchFilter(folder_ids=[1]),
    )
    res = engine.search(query)
    for item in res.results:
        assert item.filename in ("ai_paper.pdf", "stale_report.txt")


def test_semantic_search_max_chunks_per_file(setup_search_env):
    """Verify max_chunks_per_file prevents single file dominance."""
    engine, _, _, _ = setup_search_env
    query = SemanticSearchQuery(
        query="learning",
        filter=SearchFilter(max_chunks_per_file=1),
    )
    res = engine.search(query)

    file_counts = {}
    for item in res.results:
        file_counts[item.file_id] = file_counts.get(item.file_id, 0) + 1

    for fid, count in file_counts.items():
        assert count <= 1


def test_semantic_search_stale_flag(setup_search_env):
    """Verify is_stale=True when document belongs to a file with failed status."""
    engine, _, _, _ = setup_search_env
    res = engine.search("retained financial report quarterly")

    stale_items = [item for item in res.results if item.filename == "stale_report.txt"]
    if stale_items:
        assert stale_items[0].is_stale is True


def test_semantic_search_api_post(setup_search_env):
    """Test POST /api/v1/search/semantic endpoint."""
    engine, _, _, _ = setup_search_env
    app = create_app()
    app.dependency_overrides[get_semantic_search_engine] = lambda: engine

    client = TestClient(app)
    payload = {
        "query": "artificial intelligence neural networks",
        "limit": 5,
        "offset": 0,
        "min_similarity": -1.0,
    }
    response = client.post("/api/v1/search/semantic", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "total_results" in data
    assert "results" in data
    assert "model_id" in data
    assert isinstance(data["results"], list)


def test_semantic_search_api_get(setup_search_env):
    """Test GET /api/v1/search/semantic endpoint."""
    engine, _, _, _ = setup_search_env
    app = create_app()
    app.dependency_overrides[get_semantic_search_engine] = lambda: engine

    client = TestClient(app)
    response = client.get("/api/v1/search/semantic?q=database&limit=3&file_type=docx")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "database"
    assert len(data["results"]) <= 3
    for item in data["results"]:
        assert item["file_type"] == "docx"
