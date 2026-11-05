"""Folder repository for tracking indexed root folders."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import List, Optional
from app.schemas.processing import FolderRecord


def normalize_folder_path(path: str) -> str:
    """Normalize directory path string for consistent database uniqueness."""
    return str(Path(path).resolve())


class FolderRepository:
    """Data access repository for folders table."""

    @staticmethod
    def get_or_create(conn: sqlite3.Connection, path: str) -> FolderRecord:
        """Retrieve existing folder record or create a new one."""
        normalized = normalize_folder_path(path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, path, enabled, created_at, updated_at FROM folders WHERE path = ?;", (normalized,))
        row = cursor.fetchone()
        if row:
            cursor.close()
            return FolderRecord(
                id=row["id"],
                path=row["path"],
                enabled=bool(row["enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO folders (path, enabled, created_at, updated_at)
            VALUES (?, 1, ?, ?);
            """,
            (normalized, now_iso, now_iso),
        )
        folder_id = cursor.lastrowid
        cursor.close()

        return FolderRecord(
            id=folder_id,
            path=normalized,
            enabled=True,
            created_at=now_iso,
            updated_at=now_iso,
        )

    @staticmethod
    def get_by_id(conn: sqlite3.Connection, folder_id: int) -> Optional[FolderRecord]:
        """Fetch folder by primary key ID."""
        cursor = conn.cursor()
        cursor.execute("SELECT id, path, enabled, created_at, updated_at FROM folders WHERE id = ?;", (folder_id,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return None
        return FolderRecord(
            id=row["id"],
            path=row["path"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> List[FolderRecord]:
        """List all registered folders."""
        cursor = conn.cursor()
        cursor.execute("SELECT id, path, enabled, created_at, updated_at FROM folders ORDER BY id ASC;")
        rows = cursor.fetchall()
        cursor.close()
        return [
            FolderRecord(
                id=r["id"],
                path=r["path"],
                enabled=bool(r["enabled"]),
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    @staticmethod
    def delete(conn: sqlite3.Connection, folder_id: int) -> bool:
        """Delete a folder record. Foreign-key CASCADE deletes associated files and chunks."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM folders WHERE id = ?;", (folder_id,))
        deleted = cursor.rowcount > 0
        cursor.close()
        return deleted

