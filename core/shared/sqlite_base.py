import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from core.infra.logger_config import logger


class SQLiteBase:
    """Base class to abstract common SQLite database operations with WAL mode and transaction handling."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensures that the directory containing the database file exists."""
        directory = os.path.dirname(os.path.abspath(self.db_path))
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                logger.error(
                    f"Failed to create directory {directory} for SQLite database: {e}"
                )
                raise

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection]:
        """Context manager to yield a safe SQLite connection, executing WAL mode and autocommitting modifications."""
        conn = None
        try:
            # 5-second timeout to mitigate 'database is locked' errors during concurrent writes
            conn = sqlite3.connect(self.db_path, timeout=5.0)

            # Enable WAL (Write-Ahead Logging) journal mode for improved read/write concurrency
            conn.execute("PRAGMA journal_mode=WAL;")

            yield conn
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"SQLite database error on {self.db_path}: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
