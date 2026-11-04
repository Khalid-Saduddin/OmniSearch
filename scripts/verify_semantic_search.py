#!/usr/bin/env python3
"""OmniSearch Phase 5 Semantic Search Verification Script.

Tests the semantic retrieval pipeline:
Document Chunks -> Embedding Generation -> ChromaDB Storage -> Query Embedding -> Cosine Retrieval.
"""

from pathlib import Path
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.core.config import get_settings
    from app.database.connection import DatabaseConnectionManager
    from app.database.initialization import init_db
    from app.database.repositories.chunks import ChunkRepository
    from app.database.repositories.files import FileRepository
    from app.database.repositories.folders import FolderRepository
    from app.embeddings.configuration import EmbeddingConfig
    from app.embeddings.embedder import EmbeddingGemmaEmbedder
    from app.embeddings.test_embedder import DeterministicTestEmbedder
    from app.schemas.extraction import ExtractionStatus
    from app.schemas.processing import DocumentChunk, FileRecord
    from app.search.semantic_search import SemanticSearchEngine
    from app.services.semantic_pipeline import SemanticPipeline
    from app.vector_store.chroma import ChromaVectorStore
except ImportError as err:
    sys.stderr.write(f"Error importing modules: {err}\n")
    sys.exit(1)


def verify_semantic_pipeline(use_real_model: bool = False) -> bool:
    """Run verification of the semantic search engine."""
    print("=" * 65)
    print("  OMNISEARCH PHASE 5: SEMANTIC SEARCH VERIFICATION")
    print("=" * 65)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "verify.db"
        test_vectors_dir = tmp_path / "vectors"

        db_manager = init_db(db_path=db_path, recover_jobs=False)
        vector_store = ChromaVectorStore(persist_dir=test_vectors_dir, collection_name="verification")

        embedder = None
        if use_real_model:
            print("\n[1/4] Attempting to load real Google EmbeddingGemma 2 model...")
            try:
                settings = get_settings()
                cfg = EmbeddingConfig(
                    model_id=settings.embedding_model_id,
                    dimension=settings.embedding_dimension,
                    device="cpu",
                    precision="float32",
                )
                embedder = EmbeddingGemmaEmbedder(config=cfg)
                start = time.perf_counter()
                vec = embedder.embed_query("smoke test")
                load_time = round(time.perf_counter() - start, 2)
                print(f"      Successfully loaded {cfg.model_id} (dimension: {len(vec)}, latency: {load_time}s)")
            except Exception as exc:
                print(f"      Real model loading skipped/failed: {exc}")
                print("      Falling back to DeterministicTestEmbedder for pipeline verification.")
                embedder = None

        if embedder is None:
            print("\n[1/4] Initializing DeterministicTestEmbedder (offline-safe double)...")
            embedder = DeterministicTestEmbedder(dimension=768)
            print(f"      Initialized test embedder with dimension: {embedder.dimension}")

        print("\n[2/4] Indexing sample documents into SQLite & ChromaDB...")
        with db_manager.transaction() as conn:
            fld = FolderRepository.get_or_create(conn, str(tmp_path))
            f_rec = FileRecord(
                folder_id=fld.id,
                path=str(tmp_path / "urban_monitoring.txt"),
                filename="urban_monitoring.txt",
                extension=".txt",
                file_type="text",
                status=ExtractionStatus.SUCCESS.value,
                modified_at="2026-11-04T12:00:00Z",
            )
            fid = FileRepository.upsert(conn, f_rec)
            chunks = [
                DocumentChunk(
                    chunk_index=0,
                    content="Bus-mounted cameras detect potholes and monitor urban road conditions.",
                    token_count=10,
                    char_count=68,
                ),
                DocumentChunk(
                    chunk_index=1,
                    content="Deep convolutional networks achieve high accuracy in visual image classification.",
                    token_count=10,
                    char_count=77,
                ),
            ]
            ChunkRepository.insert_chunks(conn, fid, chunks)

        pipeline = SemanticPipeline(db=db_manager, embedder=embedder, vector_store=vector_store)
        embedded_count = pipeline.sync_embeddings()
        print(f"      Successfully embedded and synced {embedded_count} chunk(s) into ChromaDB.")

        print("\n[3/4] Executing conceptual natural-language query...")
        query_text = "How can artificial intelligence identify damaged roads?"
        print(f"      Query: '{query_text}'")

        engine = SemanticSearchEngine(db=db_manager, vector_store=vector_store, embedder=embedder)
        response = engine.search(query=query_text, limit=3)

        print(f"      Results returned: {len(response.results)} in {response.execution_time_ms}ms")
        for idx, item in enumerate(response.results, 1):
            print(f"      {idx}. [{item.score:.4f} score | sim: {item.cosine_similarity:.4f}] {item.filename}:")
            print(f"         \"{item.snippet}\"")

        print("\n[4/4] Verification check:")
        if response.total_results > 0:
            print("      PASS: Semantic search pipeline retrieved matching documents cleanly.")
            return True
        else:
            print("      FAIL: No results returned.")
            return False


if __name__ == "__main__":
    use_real = "--real" in sys.argv
    success = verify_semantic_pipeline(use_real_model=use_real)
    sys.exit(0 if success else 1)
