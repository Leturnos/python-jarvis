import os
import sqlite3
from collections.abc import Generator
from datetime import datetime
from unittest.mock import patch

import pytest

from core.runtime.rate_limiter import RateLimiter


@pytest.fixture
def temp_db(tmp_path) -> Generator[str]:
    """Creates a temporary sqlite database and creates the api_usage table schema."""
    db_file = tmp_path / "test_history.db"
    db_path = str(db_file)

    # Establish schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            requests_count INTEGER DEFAULT 0,
            tokens_count INTEGER DEFAULT 0,
            UNIQUE(date)
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    # Clean up
    if db_file.exists():
        try:
            os.remove(db_path)
        except OSError:
            pass


@pytest.fixture
def mock_config() -> Generator[dict]:
    # Mock config quotas to be small for easy testing
    test_config = {
        "quotas": {"llm": {"max_requests_per_day": 3, "max_tokens_per_day": 500}}
    }
    with patch("core.runtime.rate_limiter.config", test_config):
        yield test_config


def test_rate_limiter_init(mock_config) -> None:
    """Verifies that RateLimiter initializes with configured values."""
    rl = RateLimiter()
    assert rl.max_requests == 3
    assert rl.max_tokens == 500


def test_get_today_str() -> None:
    """Verifies date format matches YYYY-MM-DD."""
    rl = RateLimiter()
    today_str = rl._get_today_str()
    assert today_str == datetime.now().strftime("%Y-%m-%d")


def test_check_quotas_empty_db(mock_config, temp_db) -> None:
    """Verifies that check_quotas returns True when there are no usage entries for today."""
    rl = RateLimiter()
    rl.db_path = temp_db
    assert rl.check_quotas() is True


def test_check_quotas_within_limits(mock_config, temp_db) -> None:
    """Verifies check_quotas is True when usage is below max limits."""
    rl = RateLimiter()
    rl.db_path = temp_db

    # Log usage below limits
    rl.log_usage(token_count=100)
    assert rl.check_quotas() is True

    rl.log_usage(token_count=200)
    assert rl.check_quotas() is True  # Total 2 requests, 300 tokens (limit is 3, 500)


def test_check_quotas_exceeded_requests(mock_config, temp_db) -> None:
    """Verifies check_quotas is False when requests limit is reached."""
    rl = RateLimiter()
    rl.db_path = temp_db

    # max_requests is 3
    rl.log_usage(token_count=10)
    rl.log_usage(token_count=10)
    rl.log_usage(token_count=10)  # 3 requests logged

    # Current counts: 3 requests, 30 tokens
    assert rl.check_quotas() is False


def test_check_quotas_exceeded_tokens(mock_config, temp_db) -> None:
    """Verifies check_quotas is False when tokens limit is exceeded in fewer requests."""
    rl = RateLimiter()
    rl.db_path = temp_db

    # max_tokens is 500
    rl.log_usage(token_count=600)  # 1 request, 600 tokens
    assert rl.check_quotas() is False


def test_log_usage_insert_and_upsert(mock_config, temp_db) -> None:
    """Verifies log_usage correctly inserts new record or updates existing row for today."""
    rl = RateLimiter()
    rl.db_path = temp_db
    today = rl._get_today_str()

    # 1. Insert
    rl.log_usage(token_count=150)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT requests_count, tokens_count FROM api_usage WHERE date = ?", (today,)
    )
    row = cursor.fetchone()
    assert row == (1, 150)

    # 2. Update (conflict trigger on date)
    rl.log_usage(token_count=50)
    cursor.execute(
        "SELECT requests_count, tokens_count FROM api_usage WHERE date = ?", (today,)
    )
    row = cursor.fetchone()
    assert row == (2, 200)

    conn.close()


def test_check_quotas_error_fails_open(mock_config) -> None:
    """Verifies check_quotas returns True (fail-open) and logs error when database connection fails."""
    rl = RateLimiter()
    rl.db_path = "invalid_path/non_existent_directory/database.db"

    # Database connection should fail, check_quotas must return True
    assert rl.check_quotas() is True


def test_log_usage_error_handled_safely(mock_config) -> None:
    """Verifies log_usage handles database connection errors gracefully without raising exceptions."""
    rl = RateLimiter()
    rl.db_path = "invalid_path/non_existent_directory/database.db"

    # Should complete without throwing an exception
    rl.log_usage(token_count=100)
