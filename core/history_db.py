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
                    error_message TEXT,
                    action_json TEXT
                )
            ''')
            
            # Migration check: Add action_json if it doesn't exist
            cursor.execute("PRAGMA table_info(command_history)")
            columns = [column[1] for column in cursor.fetchall()]
            if "action_json" not in columns:
                logger.info("Migrating history database: Adding action_json column")
                cursor.execute("ALTER TABLE command_history ADD COLUMN action_json TEXT")

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

    def log_execution(self, input_text, input_source, intent, risk_level, status, confidence=1.0, error_msg=None, action_json=None):
        """Logs a command execution into the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO command_history 
                (timestamp, input_text, input_source, intent, confidence, risk_level, execution_status, error_message, action_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now().isoformat(), input_text, input_source, intent, float(confidence), risk_level, status, error_msg, action_json))
            conn.commit()
            conn.close()
            logger.debug(f"History logged: {intent} ({status}) with confidence {confidence:.2f}")
        except Exception as e:
            logger.error(f"Failed to log execution to history: {e}")

    def get_last_successful_json(self):
        """Returns the action_json of the most recent successful action (excluding replay/macro)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT action_json FROM command_history 
                WHERE execution_status = 'success' 
                AND intent NOT IN ('replay', 'macro')
                AND action_json IS NOT NULL
                ORDER BY timestamp DESC LIMIT 1
            ''')
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error retrieving last successful json: {e}")
            return None

    def get_recent_history_json(self, n=5):
        """Returns a list of action_json for the last N successful actions."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT action_json FROM command_history 
                WHERE execution_status = 'success' 
                AND intent NOT IN ('replay', 'macro')
                AND action_json IS NOT NULL
                ORDER BY timestamp DESC LIMIT ?
            ''', (n,))
            rows = cursor.fetchall()
            conn.close()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving recent history json: {e}")
            return []

# Singleton instance
history_manager = HistoryManager()
