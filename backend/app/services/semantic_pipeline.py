"""Semantic indexing pipeline orchestrating chunk embedding and ChromaDB synchronization."""

import logging
from typing import List, Optional, Set, Tuple

from app.database.connection import DatabaseConnectionManager
from app.database.repositories.embeddings import ChunkEmbeddingRepository
from app.embeddings.base import BaseEmbedder
from app.vector_store.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


class SemanticPipeline:
    """Coordinates embedding generation from SQLite chunks to ChromaDB vector store."""

    def __init__(
        self,
        db: DatabaseConnectionManager,
        embedder: BaseEmbedder,
        vector_store: ChromaVectorStore,
        batch_size: int = 16,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.batch_size = batch_size

    def sync_embeddings(self, max_chunks: Optional[int] = None) -> int:
        """Fetch unembedded chunks from SQLite, generate embeddings, and persist to ChromaDB.

        Args:
            max_chunks: Optional maximum number of chunks to process in this run.

        Returns:
            Total number of newly embedded chunks stored.
        """
        total_embedded = 0

        while True:
            limit = self.batch_size
            if max_chunks is not None:
                remaining = max_chunks - total_embedded
                if remaining <= 0:
                    break
                limit = min(limit, remaining)

            with self.db.connection() as conn:
                unembedded_rows = ChunkEmbeddingRepository.get_unembedded_chunks(conn, limit=limit)

            if not unembedded_rows:
                break

            chunk_ids: List[int] = []
            file_ids: List[int] = []
            contents: List[str] = []
            titles: List[Optional[str]] = []
            metadatas: List[dict] = []

            for row in unembedded_rows:
                cid = row["chunk_id"]
                fid = row["file_id"]
                c_content = row["content"]
                fname = row["filename"]
                ftype = row["file_type"]
                folder_id = row["folder_id"]
                c_index = row["chunk_index"]

                chunk_ids.append(cid)
                file_ids.append(fid)
                contents.append(c_content)
                titles.append(fname)
                metadatas.append({
                    "file_id": fid,
                    "filename": fname,
                    "file_type": ftype,
                    "folder_id": folder_id,
                    "chunk_index": c_index,
                    "page_number": row["page_number"],
                    "slide_number": row["slide_number"],
                    "sheet_name": row["sheet_name"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                })

            # Generate embeddings using embedder
            embeddings = self.embedder.embed_documents(contents, titles=titles)

            # Store in ChromaDB
            self.vector_store.upsert(
                chunk_ids=chunk_ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=contents,
            )

            # Record in SQLite chunk_embeddings table
            records_to_commit: List[Tuple[int, int, str, int]] = [
                (cid, fid, self.embedder.model_id, self.embedder.dimension)
                for cid, fid in zip(chunk_ids, file_ids)
            ]
            with self.db.transaction() as conn:
                ChunkEmbeddingRepository.record_batch(conn, records_to_commit)

            total_embedded += len(chunk_ids)
            logger.info("Embedded and synced %d chunks (total so far: %d)", len(chunk_ids), total_embedded)

        return total_embedded

    def reconcile_vector_store(self) -> int:
        """Identify and remove vectors in ChromaDB that no longer exist in SQLite chunks table.

        Returns:
            Number of orphaned vectors removed from ChromaDB.
        """
        chroma_ids = self.vector_store.get_all_chunk_ids()
        if not chroma_ids:
            return 0

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM chunks;")
            valid_chunk_ids = {row[0] for row in cursor.fetchall()}
            cursor.close()

        orphaned = chroma_ids - valid_chunk_ids
        if orphaned:
            logger.info("Found %d orphaned vectors in ChromaDB. Deleting...", len(orphaned))
            self.vector_store.delete(list(orphaned))
            with self.db.transaction() as conn:
                for oid in orphaned:
                    ChunkEmbeddingRepository.delete_by_chunk_id(conn, oid)

        return len(orphaned)

    def delete_file_embeddings(self, file_id: int) -> None:
        """Remove all vector embeddings for a given file ID from both Chroma and SQLite."""
        self.vector_store.delete_by_file_id(file_id)
        with self.db.transaction() as conn:
            ChunkEmbeddingRepository.delete_by_file_id(conn, file_id)

