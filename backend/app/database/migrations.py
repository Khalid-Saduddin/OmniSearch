"""Versioned schema migrations for SQLite database."""

from datetime import datetime, timezone
import sqlite3
from typing import Callable, List, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)


def migration_v1(conn: sqlite3.Connection) -> None:
    """Initial Phase 3 schema: folders, files, chunks, index_jobs, and settings tables."""
    cursor = conn.cursor()

    # 1. Folders table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 2. Files table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
        path TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        extension TEXT NOT NULL,
        file_type TEXT NOT NULL,
        sha256 TEXT,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        modified_at TEXT NOT NULL,
        indexed_at TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_folder_id ON files(folder_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);")

    # 3. Chunks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        source_segment_index INTEGER NOT NULL DEFAULT 0,
        content TEXT NOT NULL,
        token_count INTEGER NOT NULL DEFAULT 0,
        page_number INTEGER,
        slide_number INTEGER,
        sheet_name TEXT,
        row_number INTEGER,
        start_line INTEGER,
        end_line INTEGER,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_chunk ON chunks(file_id, chunk_index);")

    # 4. Indexing Jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS index_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status TEXT NOT NULL,
        total_files INTEGER NOT NULL DEFAULT 0,
        processed_files INTEGER NOT NULL DEFAULT 0,
        successful_files INTEGER NOT NULL DEFAULT 0,
        failed_files INTEGER NOT NULL DEFAULT 0,
        skipped_files INTEGER NOT NULL DEFAULT 0,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        error_message TEXT
    );
    """)

    # 5. Application Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    cursor.close()


# Ordered migration registry: (version, migration_function)
MIGRATIONS: List[Tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, migration_v1),
]


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations to the connected SQLite database in version sequence.

    Args:
        conn: Open SQLite connection.

    Returns:
        Highest migration version applied.
    """
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );
    """)

    cursor.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
    applied_versions = {row[0] for row in cursor.fetchall()}

    applied_count = 0
    highest_version = max(applied_versions) if applied_versions else 0

    for version, migration_fn in MIGRATIONS:
        if version not in applied_versions:
            logger.info("Applying database schema migration v%d...", version)
            migration_fn(conn)
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?);",
                (version, now_iso),
            )
            applied_count += 1
            highest_version = version

    cursor.close()
    if applied_count > 0:
        logger.info("Successfully applied %d migration(s). Current schema version: v%d", applied_count, highest_version)
    return highest_version

