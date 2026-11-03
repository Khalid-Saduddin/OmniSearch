"""Settings repository for persisting application configuration in SQLite."""

from datetime import datetime, timezone
import sqlite3
from typing import Optional


class SettingRepository:
    """Data access repository for key-value settings table."""

    @staticmethod
    def get(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch setting string value by key."""
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
        row = cursor.fetchone()
        cursor.close()
        if row is not None:
            return row["value"]
        return default

    @staticmethod
    def set(conn: sqlite3.Connection, key: str, value: str) -> None:
        """Insert or update setting value."""
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at;
            """,
            (key, value, now_iso),
        )
        cursor.close()

    @staticmethod
    def delete(conn: sqlite3.Connection, key: str) -> bool:
        """Delete setting key."""
        cursor = conn.cursor()
        cursor.execute("DELETE FROM settings WHERE key = ?;", (key,))
        deleted = cursor.rowcount > 0
        cursor.close()
        return deleted
