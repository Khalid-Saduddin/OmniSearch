#!/usr/bin/env python3
"""OmniSearch Manual Folder Indexing CLI Utility.

Recursively scans, extracts, processes, and persists documents from a local folder
into the canonical SQLite database and SQLite FTS5 search index.
"""

import argparse
from pathlib import Path
import sys
import time

# Ensure backend package is importable regardless of current working directory
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.core.config import get_settings
    from app.core.logging import setup_logging
    from app.database.connection import DatabaseConnectionManager
    from app.database.initialization import init_db
    from app.services.indexer import IndexingService
except ImportError as err:
    sys.stderr.write(
        f"Error: Unable to import OmniSearch backend modules ({err}).\n"
        f"Please run this script using the backend virtual environment, e.g.:\n"
        f"  .\\backend\\.venv\\Scripts\\python.exe scripts/index_folder.py <folder_path>\n"
    )
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    description = (
        "OmniSearch — Manual Folder Indexing CLI Utility\n"
        "Recursively indexes documents in the target folder into OmniSearch's SQLite database."
    )
    epilog = """
Usage Examples:
  # Index a documents folder using default application database:
  python scripts/index_folder.py "C:\\Users\\User\\Documents"

  # Force re-indexing of all files (even if unchanged):
  python scripts/index_folder.py "C:\\Users\\User\\Documents" --force

  # Index without reconciling/removing deleted files:
  python scripts/index_folder.py "./my_docs" --no-reconcile

  # Index into a custom database file:
  python scripts/index_folder.py "./my_docs" --db-path "C:\\data\\custom.db"
"""
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "folder_path",
        type=str,
        help="Local filesystem path of the folder to index recursively.",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-indexing and chunk replacement even if file size and SHA-256 match.",
    )
    parser.add_argument(
        "--no-reconcile",
        action="store_true",
        help="Do not remove database records for files that have been deleted from disk.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom path to the SQLite database. Defaults to standard local app storage.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate semantic vector embeddings and persist to ChromaDB.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed DEBUG logging output during indexing.",
    )
    return parser.parse_args()


def count_folder_chunks(db: DatabaseConnectionManager, resolved_folder: Path) -> int:
    """Query the total number of document chunks currently stored for the specified folder."""
    try:
        with db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(c.id)
                FROM chunks c
                JOIN files f ON c.file_id = f.id
                JOIN folders fld ON f.folder_id = fld.id
                WHERE fld.path = ?;
                """,
                (str(resolved_folder),),
            )
            count = cursor.fetchone()[0]
            cursor.close()
            return count
    except Exception:
        return 0


def main() -> int:
    """Execute folder indexing workflow and print execution summary."""
    args = parse_args()

    # Configure logging level
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # Validate target folder
    target_path = Path(args.folder_path)
    if not target_path.exists():
        sys.stderr.write(f"\n[Error] Folder path does not exist: {target_path}\n")
        return 1

    if not target_path.is_dir():
        sys.stderr.write(f"\n[Error] Specified path is a file, not a directory: {target_path}\n")
        return 1

    resolved_folder = target_path.resolve()

    print("\n" + "=" * 65)
    print("  OMNISEARCH FOLDER INDEXER")
    print("=" * 65)
    print(f"  Target Folder : {resolved_folder}")
    print(f"  Force Reindex : {'Yes' if args.force else 'No'}")
    print(f"  Reconciliation: {'Disabled' if args.no_reconcile else 'Enabled'}")

    try:
        # Initialize database (applies versioned migrations if needed)
        db_target = Path(args.db_path).resolve() if args.db_path else None
        db_manager = init_db(db_path=db_target, recover_jobs=True)
        print(f"  Database Path : {db_manager.db_path}")
        print("=" * 65)
        print("\nStarting indexing process...\n")

        start_time = time.perf_counter()

        # Configure semantic pipeline if requested
        semantic_pipeline = None
        if args.embed:
            from app.embeddings.configuration import EmbeddingConfig
            from app.embeddings.embedder import EmbeddingGemmaEmbedder
            from app.services.semantic_pipeline import SemanticPipeline
            from app.vector_store.chroma import ChromaVectorStore

            settings = get_settings()
            resolved_model = settings.resolved_embedding_model
            vstore = ChromaVectorStore(persist_dir=settings.vectors_dir)
            cfg = EmbeddingConfig(
                model_id=resolved_model,
                dimension=settings.embedding_dimension,
                batch_size=settings.embedding_batch_size,
                device=settings.embedding_device,
                precision=settings.embedding_precision,
                local_files_only=(resolved_model != settings.embedding_model_id),
            )
            embedder = EmbeddingGemmaEmbedder(config=cfg)
            semantic_pipeline = SemanticPipeline(db=db_manager, embedder=embedder, vector_store=vstore)

        # Execute indexing pipeline via existing IndexingService
        indexer = IndexingService(db=db_manager, semantic_pipeline=semantic_pipeline)
        job_record = indexer.index_folder(
            folder_path=resolved_folder,
            reconcile_deleted=not args.no_reconcile,
            force_reindex=args.force,
            generate_embeddings=args.embed,
        )

        elapsed_seconds = round(time.perf_counter() - start_time, 2)
        total_chunks = count_folder_chunks(db_manager, resolved_folder)

        print("\n" + "-" * 65)
        print("  INDEXING SUMMARY")
        print("-" * 65)
        print(f"  Job Status        : {job_record.status.value.upper()}")
        print(f"  Files Discovered  : {job_record.total_files}")
        print(f"  Files Indexed     : {job_record.successful_files}")
        print(f"  Files Skipped     : {job_record.skipped_files} (unchanged content)")
        print(f"  Files Failed      : {job_record.failed_files}")
        print(f"  Total Chunks      : {total_chunks}")
        print(f"  Duration          : {elapsed_seconds}s")
        print(f"  Database Location : {db_manager.db_path}")
        print("-" * 65 + "\n")

        if job_record.failed_files > 0:
            print(f"[Warning] {job_record.failed_files} file(s) failed during indexing.")
            if job_record.error_message:
                print(f"Details: {job_record.error_message}")
            return 2

        print("[Success] Folder indexing completed successfully.")
        return 0

    except Exception as exc:
        sys.stderr.write(f"\n[Fatal Error] Indexing failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())

