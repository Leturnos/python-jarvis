import pytest
import os
import sqlite3
import time
from core.cache.sqlite_cache import SQLiteLLMCache

@pytest.fixture
def temp_cache(tmp_path):
    db_path = tmp_path / "test_cache.db"
    cache = SQLiteLLMCache(db_path=str(db_path), ttl_seconds=2)
    yield cache
    cache.clear()

def test_cache_set_and_get(temp_cache):
    instruction = "Abra o VSCode"
    response = {
        "type": "action",
        "action": "system",
        "commands": ["code ."],
        "risk_level": "safe"
    }

    # Should be empty initially
    assert temp_cache.get(instruction) is None
    assert temp_cache.get_stats()["misses"] == 1
    
    # Save to cache
    temp_cache.set(instruction, response)
    
    # Should hit cache now
    cached = temp_cache.get(instruction)
    assert cached == response
    assert temp_cache.get_stats()["hits"] == 1

def test_cache_normalization(temp_cache):
    response = {"type": "action", "action": "plugin"}
    
    # Save using one variation
    temp_cache.set("Jarvis, abra o Chrome!", response)
    
    # Retrieve using a different but semantically identical (normalized) variation
    cached = temp_cache.get("jarvis abra o chrome")
    assert cached == response

def test_cache_ignores_chat(temp_cache):
    instruction = "Bom dia Jarvis"
    response = {
        "type": "chat",
        "message": "Bom dia, senhor!"
    }
    
    # Set should ignore this because type != action
    temp_cache.set(instruction, response)
    
    assert temp_cache.get(instruction) is None

def test_cache_ttl_expiration(temp_cache):
    instruction = "Teste TTL"
    response = {"type": "action", "action": "plugin"}
    
    temp_cache.set(instruction, response)
    
    # Should exist
    assert temp_cache.get(instruction) == response
    
    # Wait for TTL to expire (ttl is 2 seconds in this fixture)
    time.sleep(2.1)
    
    # Should be None now
    assert temp_cache.get(instruction) is None
