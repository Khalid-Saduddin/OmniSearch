"""Comprehensive integration tests for KeywordSearchEngine, filters, BM25 ranking, and API endpoints."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.database.connection import DatabaseConnectionManager
from app.database.migrations import apply_migrations
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.main import create_app
from app.schemas.processing import DocumentChunk, FileRecord
from app.schemas.search import SearchFilter, SearchQuery
from app.search.keyword_search import KeywordSearchEngine
from app.services.indexer import IndexingService


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseConnectionManager:
    """Provide a fresh SQLite database initialized with all migrations."""
    db_file = tmp_path / "search_test.db"
    db = DatabaseConnectionManager(db_file)
    with db.connection() as conn:
        apply_migrations(conn)
    return db


@pytest.fixture
def populated_search_engine(test_db: DatabaseConnectionManager) -> KeywordSearchEngine:
    """Seed test documents across multiple formats and folders."""
    with test_db.transaction() as conn:
        fld_ai = FolderRepository.get_or_create(conn, "C:/docs/ai")
        fld_web = FolderRepository.get_or_create(conn, "C:/docs/web")

        # 1. AI Paper (PDF) - 4 chunks
        f_ai = FileRepository.upsert(
            conn,
            FileRecord(
                folder_id=fld_ai.id,
                path="C:/docs/ai/transformers.pdf",
                filename="transformers.pdf",
                extension=".pdf",
                file_type="pdf",
                status="success",
                modified_at="2026-11-04T00:00:00Z",
                metadata_json=json.dumps({"title": "Attention Is All You Need"}),
            ),
        )
        ai_chunks = [
            DocumentChunk(
                chunk_index=0,
                content="The Transformer is the first transduction model relying entirely on self-attention.",
                token_count=15,
                page_number=1,
            ),
            DocumentChunk(
                chunk_index=1,
                content="Multi-head attention allows the model to jointly attend to information from different representation subspaces.",
                token_count=18,
                page_number=2,
            ),
            DocumentChunk(
                chunk_index=2,
                content="Positional encoding is added to the input embeddings at the bottoms of the encoder and decoder stacks.",
                token_count=18,
                page_number=3,
            ),
            DocumentChunk(
                chunk_index=3,
                content="Self-attention layers connect all positions with a constant number of sequentially executed operations.",
                token_count=16,
                page_number=4,
            ),
        ]
        ChunkRepository.insert_chunks(conn, f_ai, ai_chunks)

        # 2. Web Guide (Markdown) - 2 chunks
        f_web = FileRepository.upsert(
            conn,
            FileRecord(
                folder_id=fld_web.id,
                path="C:/docs/web/react_guide.md",
                filename="react_guide.md",
                extension=".md",
                file_type="markdown",
                status="success",
                modified_at="2026-11-04T00:00:00Z",
                metadata_json=json.dumps({"title": "React Frontend Guide"}),
            ),
        )
        web_chunks = [
            DocumentChunk(
                chunk_index=0,
                content="React components implement a render() method that takes input data and returns what to display.",
                token_count=16,
                start_line=1,
                end_line=20,
            ),
            DocumentChunk(
                chunk_index=1,
                content="Hooks let you use state and other React features without writing a class.",
                token_count=14,
                start_line=21,
                end_line=40,
            ),
        ]
        ChunkRepository.insert_chunks(conn, f_web, web_chunks)

        # 3. Failed Re-indexed file (Stale content)
        f_stale = FileRepository.upsert(
            conn,
            FileRecord(
                folder_id=fld_ai.id,
                path="C:/docs/ai/stale_notes.txt",
                filename="stale_notes.txt",
                extension=".txt",
                file_type="txt",
                status="failed",
                error_message="Corrupted encoding",
                modified_at="2026-11-04T00:00:00Z",
            ),
        )
        stale_chunks = [
            DocumentChunk(
                chunk_index=0,
                content="Self-attention mechanisms in neural networks legacy notes.",
                token_count=10,
            )
        ]
        ChunkRepository.insert_chunks(conn, f_stale, stale_chunks)

    return KeywordSearchEngine(test_db)


def test_basic_keyword_search(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify basic search returns matches with snippets and highlights."""
    res = populated_search_engine.search("self-attention")
    assert res.total_results >= 1
    assert len(res.results) >= 1
    top_result = res.results[0]
    assert "self-attention" in top_result.snippet.lower() or "attention" in top_result.snippet.lower()
    assert len(top_result.highlights) > 0
    assert top_result.score > 0
    assert top_result.bm25_rank < 0


def test_exact_phrase_search(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify exact quoted phrase search matches only the specific sequence."""
    res = populated_search_engine.search('"Multi-head attention"')
    assert res.total_results == 1
    assert res.results[0].filename == "transformers.pdf"
    assert res.results[0].page_number == 2


def test_structural_metadata_preservation(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify chunk structural location metadata (page, lines) is correctly returned."""
    # PDF page metadata
    res_pdf = populated_search_engine.search("Positional encoding")
    assert len(res_pdf.results) == 1
    assert res_pdf.results[0].page_number == 3
    assert res_pdf.results[0].start_line is None

    # Code/Markdown line number metadata
    res_md = populated_search_engine.search("render() method")
    assert len(res_md.results) == 1
    assert res_md.results[0].start_line == 1
    assert res_md.results[0].end_line == 20
    assert res_md.results[0].page_number is None


def test_file_type_filtering(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify file_types filter restricts matches to specified formats."""
    # Search without filter matches both PDF and Markdown
    res_unfiltered = populated_search_engine.search("model")
    assert any(r.file_type == "pdf" for r in res_unfiltered.results)

    # Filter to only markdown
    filt = SearchFilter(file_types=["markdown"])
    res_filtered = populated_search_engine.search("model", filters=filt)
    assert all(r.file_type == "markdown" for r in res_filtered.results)


def test_folder_filtering(populated_search_engine: KeywordSearchEngine, test_db: DatabaseConnectionManager) -> None:
    """Verify folder_ids filter restricts matches to target folder."""
    with test_db.connection() as conn:
        ai_fld = FolderRepository.get_or_create(conn, "C:/docs/ai")

    filt = SearchFilter(folder_ids=[ai_fld.id])
    res = populated_search_engine.search("attention", filters=filt)
    assert res.total_results > 0
    assert all("ai" in r.file_path for r in res.results)


def test_duplicate_consolidation_per_file_limit(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify max_chunks_per_file prevents single-file result dominance."""
    # In transformers.pdf, 3 chunks match 'attention'.
    # With max_chunks_per_file=2, at most 2 chunks should be returned for transformers.pdf.
    filt = SearchFilter(max_chunks_per_file=2)
    res = populated_search_engine.search("attention", filters=filt)
    pdf_results = [r for r in res.results if r.filename == "transformers.pdf"]
    assert len(pdf_results) == 2


def test_pagination_limit_and_offset(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify limit and offset slice results consistently."""
    all_res = populated_search_engine.search("attention", limit=10, offset=0)
    assert all_res.total_results >= 2

    page1 = populated_search_engine.search("attention", limit=1, offset=0)
    page2 = populated_search_engine.search("attention", limit=1, offset=1)

    assert len(page1.results) == 1
    assert len(page2.results) == 1
    assert page1.results[0].chunk_id != page2.results[0].chunk_id


def test_failed_reindexing_stale_flag(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify retained chunks for a failed re-indexed file are marked with is_stale=True."""
    res = populated_search_engine.search("legacy notes")
    assert len(res.results) == 1
    item = res.results[0]
    assert item.filename == "stale_notes.txt"
    assert item.file_status == "failed"
    assert item.is_stale is True


def test_end_to_end_indexing_and_search(tmp_path: Path) -> None:
    """Verify full end-to-end flow: index a real disk folder, then search indexed chunks."""
    docs_dir = tmp_path / "my_docs"
    docs_dir.mkdir()
    (docs_dir / "science.txt").write_text(
        "Astrophysics is a branch of space science that applies the laws of physics and chemistry.",
        encoding="utf-8",
    )
    (docs_dir / "code.py").write_text(
        "def compute_orbit(mass: float, radius: float) -> float:\n    return mass / radius\n",
        encoding="utf-8",
    )

    db_file = tmp_path / "e2e.db"
    db = DatabaseConnectionManager(db_file)
    with db.connection() as conn:
        apply_migrations(conn)

    service = IndexingService(db=db)
    job = service.index_folder(docs_dir)
    assert job.successful_files == 2

    engine = KeywordSearchEngine(db=db)
    search_res = engine.search("Astrophysics physics")
    assert search_res.total_results == 1
    assert search_res.results[0].filename == "science.txt"

    code_res = engine.search("compute_orbit")
    assert code_res.total_results == 1
    assert code_res.results[0].filename == "code.py"


def test_search_api_post_endpoint(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify HTTP POST /api/v1/search endpoint behaves correctly."""
    app = create_app()
    from app.api.v1.endpoints.search import get_search_engine
    app.dependency_overrides[get_search_engine] = lambda: populated_search_engine

    client = TestClient(app)
    response = client.post(
        "/api/v1/search",
        json={"query": "self-attention", "limit": 5, "offset": 0},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "self-attention"
    assert data["total_results"] >= 1
    assert len(data["results"]) >= 1


def test_search_api_get_endpoint(populated_search_engine: KeywordSearchEngine) -> None:
    """Verify HTTP GET /api/v1/search endpoint behaves correctly."""
    app = create_app()
    from app.api.v1.endpoints.search import get_search_engine
    app.dependency_overrides[get_search_engine] = lambda: populated_search_engine

    client = TestClient(app)
    response = client.get("/api/v1/search?q=Transformer&limit=2")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Transformer"
    assert len(data["results"]) >= 1
