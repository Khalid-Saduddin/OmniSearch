"""Automated tests for ChromaDB persistent vector storage client."""

import pytest
from app.vector_store.chroma import (
    ChromaVectorStore,
    chroma_id_to_chunk_id,
    chunk_id_to_chroma_id,
)


def test_chunk_id_conversion():
    """Verify conversion between SQLite integer chunk IDs and Chroma string IDs."""
    assert chunk_id_to_chroma_id(42) == "chunk_42"
    assert chroma_id_to_chunk_id("chunk_42") == 42
    assert chroma_id_to_chunk_id("100") == 100


def test_chroma_vector_store_crud(tmp_path):
    """Test full CRUD lifecycle in persistent ChromaVectorStore."""
    store_dir = tmp_path / "vectors"
    store = ChromaVectorStore(persist_dir=store_dir, collection_name="test_chunks")

    # 1. Empty state
    assert store.count() == 0
    assert store.get_all_chunk_ids() == set()

    # 2. Upsert chunks
    chunk_ids = [1, 2, 3]
    # Synthetic 4-dimensional normalized vectors
    embeddings = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
    ]
    metadatas = [
        {"file_id": 10, "file_type": "pdf", "folder_id": 1, "filename": "doc1.pdf"},
        {"file_id": 10, "file_type": "pdf", "folder_id": 1, "filename": "doc1.pdf"},
        {"file_id": 20, "file_type": "docx", "folder_id": 2, "filename": "notes.docx"},
    ]
    documents = [
        "First chunk content about artificial intelligence.",
        "Second chunk content about deep learning.",
        "Third chunk content about database design.",
    ]

    store.upsert(
        chunk_ids=chunk_ids,
        embeddings=embeddings,
        metadatas=metadatas,
        documents=documents,
    )

    assert store.count() == 3
    assert store.get_all_chunk_ids() == {1, 2, 3}

    # 3. Query nearest neighbor
    query_vec = [0.95, 0.05, 0.0, 0.0]  # Very close to chunk 1
    results = store.query(query_vec, n_results=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == 1
    assert results[0]["similarity"] > 0.9
    assert results[0]["metadata"]["filename"] == "doc1.pdf"
    assert results[0]["document"] == "First chunk content about artificial intelligence."

    # 4. Filtered query
    filtered_results = store.query(
        query_vec,
        n_results=5,
        where={"file_type": "docx"},
    )
    assert len(filtered_results) == 1
    assert filtered_results[0]["chunk_id"] == 3

    # 5. Delete specific chunk
    store.delete([1])
    assert store.count() == 2
    assert store.get_all_chunk_ids() == {2, 3}

    # 6. Delete by file_id
    store.delete_by_file_id(10)
    assert store.count() == 1
    assert store.get_all_chunk_ids() == {3}

    # 7. Delete by folder_id
    store.delete_by_folder_id(2)
    assert store.count() == 0
    assert store.get_all_chunk_ids() == set()


def test_chroma_vector_store_empty_query(tmp_path):
    """Test querying an empty store returns an empty result list without errors."""
    store = ChromaVectorStore(persist_dir=tmp_path / "empty_vectors")
    results = store.query([1.0, 0.0, 0.0], n_results=10)
    assert results == []

