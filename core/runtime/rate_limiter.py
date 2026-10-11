import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from core.infra.config import config
from core.infra.logger_config import logger
from core.persistence.history_db import history_manager
from core.shared.sqlite_base import SQLiteBase


class RateLimiter:
    def __init__(self, history_mgr: Any = None) -> None:
        self.history_mgr = history_mgr or history_manager
        self.db_path = getattr(self.history_mgr, "db_path", history_manager.db_path)
        # Extract quotas safely, defaulting to None if missing
        quotas = config.get("quotas", {}).get("llm", {})
        self.max_requests = quotas.get("max_requests_per_day", 100)
        self.max_tokens = quotas.get("max_tokens_per_day", 500000)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection]:
        if (
            self.history_mgr
            and getattr(self.history_mgr, "db_path", None) == self.db_path
        ):
            with self.history_mgr.connection() as conn:
                yield conn
        else:
            with SQLiteBase(self.db_path).connection() as conn:
                yield conn

    def _get_today_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def check_quotas(self) -> bool:
        """Returns True if within quotas, False if exceeded."""
        today = self._get_today_str()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT requests_count, tokens_count FROM api_usage WHERE date = ?",
                    (today,),
                )
                row = cursor.fetchone()

            if not row:
                return True  # No usage recorded yet for today

            req_count, token_count = row
            if req_count >= self.max_requests or token_count >= self.max_tokens:
                logger.warning(
                    f"Quota exceeded! Req: {req_count}/{self.max_requests}, Tokens: {token_count}/{self.max_tokens}"
                )
                return False

            return True
        except Exception as e:
            logger.error(f"Error checking quotas: {e}")
            return True  # Fail open to prevent locking out on DB error

    def log_usage(self, token_count: int = 0) -> None:
        """Logs an API call and its token usage."""
        today = self._get_today_str()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Upsert logic (Insert or Update)
                cursor.execute(
                    """
                    INSERT INTO api_usage (date, requests_count, tokens_count)
                    VALUES (?, 1, ?)
                    ON CONFLICT(date) DO UPDATE SET
                    requests_count = requests_count + 1,
                    tokens_count = tokens_count + ?
                """,
                    (today, token_count, token_count),
                )

            logger.debug(f"Logged API usage: +1 request, +{token_count} tokens.")
        except Exception as e:
            logger.error(f"Error logging API usage: {e}")


rate_limiter = RateLimiter()
