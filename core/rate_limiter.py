import sqlite3
from datetime import datetime
from core.config import config
from core.history_db import history_manager
from core.logger_config import logger

class RateLimiter:
    def __init__(self):
        self.db_path = history_manager.db_path
        # Extract quotas safely, defaulting to None if missing
        quotas = config.get("quotas", {}).get("llm", {})
        self.max_requests = quotas.get("max_requests_per_day", 100)
        self.max_tokens = quotas.get("max_tokens_per_day", 500000)

    def _get_today_str(self):
        return datetime.now().strftime("%Y-%m-%d")

    def check_quotas(self):
        """Returns True if within quotas, False if exceeded."""
        today = self._get_today_str()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT requests_count, tokens_count FROM api_usage WHERE date = ?", (today,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return True # No usage recorded yet for today

            req_count, token_count = row
            if req_count >= self.max_requests or token_count >= self.max_tokens:
                logger.warning(f"Quota exceeded! Req: {req_count}/{self.max_requests}, Tokens: {token_count}/{self.max_tokens}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking quotas: {e}")
            return True # Fail open to prevent locking out on DB error

    def log_usage(self, token_count=0):
        """Logs an API call and its token usage."""
        today = self._get_today_str()
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Upsert logic (Insert or Update)
            cursor.execute('''
                INSERT INTO api_usage (date, requests_count, tokens_count) 
                VALUES (?, 1, ?)
                ON CONFLICT(date) DO UPDATE SET 
                requests_count = requests_count + 1,
                tokens_count = tokens_count + ?
            ''', (today, token_count, token_count))
            
            conn.commit()
            conn.close()
            logger.debug(f"Logged API usage: +1 request, +{token_count} tokens.")
        except Exception as e:
            logger.error(f"Error logging API usage: {e}")

rate_limiter = RateLimiter()