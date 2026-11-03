"""SQLite database connection management, WAL configuration, and transaction lifecycle."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional, Union
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseConnectionManager:
    """Manages thread-safe SQLite connections with WAL mode and foreign-key enforcement."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        if db_path is not None:
            self._db_path = Path(db_path) if str(db_path) != ":memory:" else db_path
        else:
            settings = get_settings()
            self._db_path = settings.resolved_db_path

    @property
    def db_path(self) -> Union[Path, str]:
        """Return the target database path."""
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a fresh SQLite connection with standard PRAGMAs."""
        if isinstance(self._db_path, Path):
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            db_target = str(self._db_path)
        else:
            db_target = str(self._db_path)

        conn = sqlite3.connect(
            db_target,
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row

        # Enforce SQLite performance and integrity PRAGMAs
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        if db_target != ":memory:":
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
        cursor.execute("PRAGMA busy_timeout = 5000;")
        cursor.close()

        return conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing a managed connection closed on block exit."""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic transaction (committed on success, rolled back on error)."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            logger.error("Transaction rolled back due to error: %s", exc)
            conn.rollback()
            raise
        finally:
            conn.close()
