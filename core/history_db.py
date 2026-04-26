import sqlite3
import os
from datetime import datetime
from core.logger_config import logger

class HistoryManager:
    def __init__(self, db_path="data/history.db"):
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        directory = os.path.dirname(self.db_path)
        if not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _init_db(self):
        """Initializes the SQLite database and creates the history table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    input_text TEXT,
                    input_source TEXT,
                    intent TEXT,
                    confidence REAL,
                    risk_level TEXT,
                    execution_status TEXT,
                    error_message TEXT
                )
            ''')
            # New table for rate limiting
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    requests_count INTEGER DEFAULT 0,
                    tokens_count INTEGER DEFAULT 0,
                    UNIQUE(date)
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize history database: {e}")

    def log_execution(self, input_text, input_source, intent, risk_level, status, confidence=1.0, error_msg=None):
        """Logs a command execution into the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_history 
                (timestamp, input_text, input_source, intent, confidence, risk_level, execution_status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), input_text, input_source, intent, float(confidence), risk_level, status, error_msg))
            conn.commit()
            conn.close()
            logger.debug(f"History logged: {intent} ({status}) with confidence {confidence:.2f}")
        except Exception as e:
            logger.error(f"Failed to log execution to history: {e}")

# Singleton instance
history_manager = HistoryManager()
