"""Database initialization, migration execution, and startup recovery policies."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
from app.core.logging import get_logger
from app.database.connection import DatabaseConnectionManager
from app.database.migrations import apply_migrations

logger = get_logger(__name__)


def recover_interrupted_jobs(db: DatabaseConnectionManager) -> int:
    """Recover jobs left in 'running' or 'pending' state following an unexpected shutdown."""
    with db.transaction() as conn:
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE index_jobs
            SET status = 'interrupted',
                finished_at = ?,
                error_message = 'Job was interrupted by unexpected process termination'
            WHERE status IN ('running', 'pending');
            """,
            (now_iso,),
        )
        count = cursor.rowcount
        cursor.close()
        if count > 0:
            logger.warning("Recovered %d previously running/pending index jobs to 'interrupted' status", count)
        return count


def init_db(
    db_path: Optional[Union[str, Path]] = None,
    recover_jobs: bool = True,
) -> DatabaseConnectionManager:
    """Initialize the SQLite database, apply pending migrations, and run startup recovery.

    Args:
        db_path: Target path for the database file or ':memory:'. Defaults to configured setting.
        recover_jobs: Whether to mark interrupted jobs from previous sessions.

    Returns:
        Configured DatabaseConnectionManager instance.
    """
    manager = DatabaseConnectionManager(db_path=db_path)
    logger.info("Initializing database at target: %s", manager.db_path)

    with manager.transaction() as conn:
        apply_migrations(conn)

    if recover_jobs and str(manager.db_path) != ":memory:":
        recover_interrupted_jobs(manager)

    return manager
