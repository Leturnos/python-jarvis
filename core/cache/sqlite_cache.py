import hashlib
import json
import re
import time
from typing import Any, cast

from core.cache.base import LLMCacheBase
from core.infra.logger_config import logger
from core.shared.sqlite_base import SQLiteBase


class SQLiteLLMCache(SQLiteBase, LLMCacheBase):
    def __init__(self, db_path: str = "data/llm_cache.db", ttl_seconds: int = 86400):
        SQLiteBase.__init__(self, db_path)
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
        self._init_db()

    def _init_db(self) -> None:
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        hash_key TEXT PRIMARY KEY,
                        instruction TEXT,
                        response_json TEXT,
                        created_at REAL
                    )
                """)
        except Exception as e:
            logger.error(f"Error initializing SQLite cache: {e}")

    def _normalize(self, text: str) -> str:
        """Normalizes text by making it lowercase and removing extra spaces/punctuation."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _hash(self, text: str) -> str:
        """Generates a SHA-256 hash for the normalized text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, instruction: str) -> dict[str, Any] | None:
        normalized = self._normalize(instruction)
        if not normalized:
            self.misses += 1
            return None

        hash_key = self._hash(normalized)

        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT response_json, created_at FROM cache WHERE hash_key = ?",
                    (hash_key,),
                )
                row = cursor.fetchone()

                if row:
                    response_json_str, created_at = row
                    if time.time() - created_at <= self.ttl_seconds:
                        self.hits += 1
                        logger.debug(f"Cache HIT for: '{instruction}'")
                        return cast(dict[str, Any], json.loads(response_json_str))
                    else:
                        # Expired
                        cursor.execute(
                            "DELETE FROM cache WHERE hash_key = ?", (hash_key,)
                        )
                        logger.debug(f"Cache EXPIRED for: '{instruction}'")

        except Exception as e:
            logger.error(f"Error reading from cache: {e}")

        self.misses += 1
        return None

    def set(self, instruction: str, response: dict[str, Any]) -> None:
        # Only cache actions (e.g., skip 'chat' type)
        if response.get("type") != "action":
            return

        normalized = self._normalize(instruction)
        if not normalized:
            return

        hash_key = self._hash(normalized)
        response_str = json.dumps(response)
        created_at = time.time()

        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO cache (hash_key, instruction, response_json, created_at)
                    VALUES (?, ?, ?, ?)
                """,
                    (hash_key, instruction, response_str, created_at),
                )
                logger.debug(f"Saved to cache: '{instruction}'")
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")

    def clear(self) -> None:
        try:
            with self.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache")
                logger.info("LLM cache cleared.")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def get_stats(self) -> dict[str, float]:
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
        }
