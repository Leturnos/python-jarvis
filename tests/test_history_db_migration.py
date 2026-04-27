import sqlite3
import os
import json
from core.history_db import HistoryManager

def test_history_db():
    db_path = "data/test_history.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    hm = HistoryManager(db_path=db_path)
    
    # Test 1: Verify schema migration (implicitly handled by __init__)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(command_history)")
    columns = [column[1] for column in cursor.fetchall()]
    assert "action_json" in columns, "action_json column missing"
    conn.close()
    print("Test 1: Schema migration passed.")

    # Test 2: Log execution with action_json
    action = {"type": "test", "data": "payload"}
    action_str = json.dumps(action)
    hm.log_execution("test input", "test_source", "test_intent", "low", "success", action_json=action_str)
    
    # Test 3: Retrieve last successful json
    retrieved = hm.get_last_successful_json()
    assert retrieved == action_str, f"Expected {action_str}, got {retrieved}"
    print("Test 2 & 3: Log and retrieve passed.")

    # Test 4: Retrieve recent history
    hm.log_execution("test input 2", "test_source", "test_intent", "low", "success", action_json='{"id": 2}')
    history = hm.get_recent_history_json(n=2)
    assert len(history) == 2, f"Expected 2 items, got {len(history)}"
    assert history[0] == '{"id": 2}', f"Expected '{{\"id\": 2}}', got {history[0]}"
    print("Test 4: Recent history retrieval passed.")

    # Test 5: Exclude replay/macro
    hm.log_execution("replay input", "test_source", "replay", "low", "success", action_json='{"replay": true}')
    last = hm.get_last_successful_json()
    assert "replay" not in last, "Replay action should be excluded"
    print("Test 5: Exclusion of replay/macro passed.")

    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    try:
        test_history_db()
        print("\nAll tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        exit(1)
