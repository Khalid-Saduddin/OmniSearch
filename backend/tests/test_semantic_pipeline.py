"""Automated tests for SemanticPipeline synchronization and vector reconciliation."""

from pathlib import Path
import pytest
from app.database.connection import DatabaseConnectionManager
from app.database.migrations import apply_migrations
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.embeddings import ChunkEmbeddingRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.embeddings.test_embedder import DeterministicTestEmbedder
from app.schemas.extraction import ExtractionStatus
from app.schemas.processing import DocumentChunk, FileRecord
from app.services.indexer import IndexingService
from app.services.semantic_pipeline import SemanticPipeline
from app.vector_store.chroma import ChromaVectorStore


@pytest.fixture
def test_db(tmp_path):
    """Provide a fresh initialized SQLite database with all migrations applied."""
    db_file = tmp_path / "test_omnisearch.db"
    db = DatabaseConnectionManager(db_path=db_file)
    with db.transaction() as conn:
        apply_migrations(conn)
    return db


@pytest.fixture
def vector_store(tmp_path):
    """Provide a fresh ChromaVectorStore in a temporary directory."""
    return ChromaVectorStore(persist_dir=tmp_path / "vectors", collection_name="pipeline_test")


@pytest.fixture
def test_embedder():
    """Provide a deterministic test embedder with 256 dimensions."""
    return DeterministicTestEmbedder(dimension=256)


def test_semantic_pipeline_sync_and_idempotency(test_db, vector_store, test_embedder, tmp_path):
    """Test generating embeddings for indexed chunks, verifying SQLite tracking and idempotency."""
    # 1. Setup sample file and chunks in SQLite
    with test_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, str(tmp_path))
        file_rec = FileRecord(
            folder_id=folder.id,
            path=str(tmp_path / "doc.txt"),
            filename="doc.txt",
            extension=".txt",
            file_type="text",
            sha256="abc123hash",
            size_bytes=1024,
            modified_at="2026-11-04T00:00:00Z",
            status=ExtractionStatus.SUCCESS.value,
        )
        file_id = FileRepository.upsert(conn, file_rec)
        chunks = [
            DocumentChunk(
                chunk_index=0,
                content="OmniSearch provides fast desktop search across documents.",
                token_count=10,
                char_count=55,
            ),
            DocumentChunk(
                chunk_index=1,
                content="EmbeddingGemma 2 computes dense vector representations.",
                token_count=10,
                char_count=52,
            ),
        ]
        ChunkRepository.insert_chunks(conn, file_id, chunks)

    # 2. Run sync_embeddings
    pipeline = SemanticPipeline(
        db=test_db,
        embedder=test_embedder,
        vector_store=vector_store,
        batch_size=10,
    )

    embedded_count = pipeline.sync_embeddings()
    assert embedded_count == 2
    assert vector_store.count() == 2

    # Verify SQLite tracking
    with test_db.connection() as conn:
        tracked_ids = ChunkEmbeddingRepository.get_all_embedded_chunk_ids(conn)
        assert len(tracked_ids) == 2
        count_tracked = ChunkEmbeddingRepository.count_embedded(conn)
        assert count_tracked == 2

    # 3. Idempotency check: sync again should do 0 work
    second_sync = pipeline.sync_embeddings()
    assert second_sync == 0
    assert vector_store.count() == 2


def test_semantic_pipeline_reconciliation(test_db, vector_store, test_embedder, tmp_path):
    """Test reconciliation removes vectors from Chroma that no longer exist in SQLite."""
    # Insert 1 chunk in SQLite
    with test_db.transaction() as conn:
        folder = FolderRepository.get_or_create(conn, str(tmp_path))
        file_rec = FileRecord(
            folder_id=folder.id,
            path=str(tmp_path / "sample.txt"),
            filename="sample.txt",
            extension=".txt",
            file_type="text",
            modified_at="2026-11-04T00:00:00Z",
            status=ExtractionStatus.SUCCESS.value,
        )
        file_id = FileRepository.upsert(conn, file_rec)
        chunks = [DocumentChunk(chunk_index=0, content="Valid chunk content", token_count=5, char_count=20)]
        ChunkRepository.insert_chunks(conn, file_id, chunks)
        db_chunks = ChunkRepository.get_by_file_id(conn, file_id)
        valid_chunk_id = db_chunks[0].id

    pipeline = SemanticPipeline(db=test_db, embedder=test_embedder, vector_store=vector_store)
    pipeline.sync_embeddings()
    assert vector_store.count() == 1

    # Manually inject an orphaned vector into Chroma (chunk_id 999999)
    vector_store.upsert(
        chunk_ids=[999999],
        embeddings=[[0.1] * 256],
        metadatas=[{"file_id": 888, "filename": "orphan.txt"}],
    )
    assert vector_store.count() == 2

    # Run reconciliation
    orphaned_removed = pipeline.reconcile_vector_store()
    assert orphaned_removed == 1
    assert vector_store.count() == 1
    assert vector_store.get_all_chunk_ids() == {valid_chunk_id}


def test_indexing_service_with_semantic_pipeline(test_db, vector_store, test_embedder, tmp_path):
    """Test full integration: IndexingService generates embeddings when enabled."""
    # Create test file on disk
    doc_path = tmp_path / "info.txt"
    doc_path.write_text("OmniSearch architecture includes local semantic search.", encoding="utf-8")

    pipeline = SemanticPipeline(db=test_db, embedder=test_embedder, vector_store=vector_store)
    indexer = IndexingService(db=test_db, semantic_pipeline=pipeline)

    # Index folder with generate_embeddings=True
    job = indexer.index_folder(tmp_path, generate_embeddings=True)
    assert job.successful_files == 1
    assert vector_store.count() >= 1

    with test_db.connection() as conn:
        assert ChunkEmbeddingRepository.count_embedded(conn) >= 1
