import os
import time
import queue
import threading
import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from core.persistence.history_db import HistoryManager
from core.cache.sqlite_cache import SQLiteLLMCache
from core.plugins.plugin_manager import PluginManager
from core.execution.job_queue import Job, JobType, JobStatus
from core.execution.worker import command_worker
from core.runtime.state import state_manager, JarvisState
from core.shared.errors import TechnicalError, BusinessError
from core.controller import JarvisController

@pytest.fixture
def temp_env(tmp_path):
    """Fixture that provides temporary paths for SQLite databases and plugins, cleaned up by pytest."""
    test_db_path = str(tmp_path / "test_history.db")
    test_cache_path = str(tmp_path / "test_llm_cache.db")
    test_plugins_dir = str(tmp_path / "test_plugins")
    os.makedirs(test_plugins_dir, exist_ok=True)

    # Clear state manager callbacks
    state_manager.set_state(JarvisState.IDLE)
    state_manager._callbacks = []

    yield {
        "db_path": test_db_path,
        "cache_path": test_cache_path,
        "plugins_dir": test_plugins_dir,
    }

# ==========================================
# 1. RECOVERY TESTS
# ==========================================

@patch("core.controller.safe_reset_audio")
def test_microphone_failure_and_healing(mock_reset):
    """Simulates microphone I/O failures in the audio loop and ensures self-healing triggers."""
    print("\n--- Test 1.1: Microphone Failure Recovery (Self-Healing) ---")
    
    stop_event = threading.Event()
    config = {
        "jarvis": {"threshold": 0.4, "volume_multiplier": 1.0, "cooldown_seconds": 2},
        "voice_activation": {"mode": "hybrid", "auto_suspend": {"fullscreen": False}}
    }
    
    automator = MagicMock()
    automator.is_speaking = False
    dispatcher = MagicMock()
    model = MagicMock()
    ui = MagicMock()
    tray = MagicMock()
    task_queue = queue.Queue()
    pa = MagicMock()
    stream = MagicMock()
    
    # Inject device read error (Simulate microphone disconnection)
    stream.read.side_effect = IOError("Device Unavailable")
    
    # Setup reset mock to stop the controller loop after healing is triggered
    def reset_side_effect(p, s):
        print("[INFO] safe_reset_audio was called due to simulated microphone failure.")
        stop_event.set()
        return p, s
    mock_reset.side_effect = reset_side_effect

    controller = JarvisController(
        config=config,
        automator=automator,
        dispatcher=dispatcher,
        model=model,
        loaded_names=["hey_jarvis"],
        ui=ui,
        tray=tray,
        task_queue=task_queue,
        stop_event=stop_event,
        pa=pa,
        stream=stream
    )
    
    thread = threading.Thread(target=controller.start, daemon=True)
    thread.start()
    thread.join(timeout=3.0)

    assert mock_reset.called, "safe_reset_audio should have been called."
    print("[SUCCESS] The loop handled the microphone error and triggered the self-healing routine.")


@patch("core.ai.llm_agent.llm_cache.get", return_value=None)
@patch("litellm.completion")
def test_internet_down_retry(mock_completion, mock_cache_get):
    """Simulates internet connection loss causing completion errors in litellm and checks worker retries."""
    print("\n--- Test 1.2: Internet Connection Loss Recovery (Retries) ---")
    
    # Mock completion to raise network error
    mock_completion.side_effect = Exception("APIConnectionError: Network unreachable")

    task_queue = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()
    
    dispatcher = MagicMock()
    dispatcher.automator.is_speaking = False
    notifier = MagicMock()
    
    # Create LLM dynamic job
    job = Job(type=JobType.LLM_DYNAMIC, payload=b"mocked audio content")
    job.payload_text = "executar comando complexo remoto"
    job.max_retries = 2  # speed up tests
    task_queue.put(job)

    # Run command worker briefly to process one job
    def stop_worker_after_job():
        time.sleep(0.5)
        stop_event.set()

    threading.Thread(target=stop_worker_after_job, daemon=True).start()
    command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy)

    assert job.status == JobStatus.FAILED
    assert job.retries > 0, "The job should have retried due to a technical error."
    assert "Network unreachable" in job.error
    print(f"[SUCCESS] The worker retried {job.retries} times and failed gracefully with a network error.")


@patch("core.ai.llm_agent.llm_cache.get", return_value=None)
@patch("litellm.completion")
def test_gemini_rate_limit_429(mock_completion, mock_cache_get):
    """Simulates Gemini HTTP 429 Rate Limit error and validates resiliency/backoff."""
    print("\n--- Test 1.3: Gemini Rate Limit (Error 429) ---")
    
    import litellm
    mock_completion.side_effect = litellm.exceptions.RateLimitError(
        message="Rate limit exceeded",
        llm_provider="gemini",
        model="gemini-2.5-flash"
    )

    task_queue = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()
    
    dispatcher = MagicMock()
    notifier = MagicMock()
    
    job = Job(type=JobType.LLM_DYNAMIC, payload=b"mocked audio content")
    job.payload_text = "executar comando complexo remoto"
    job.max_retries = 2
    task_queue.put(job)

    def stop_worker():
        time.sleep(0.5)
        stop_event.set()

    threading.Thread(target=stop_worker, daemon=True).start()
    command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy)

    assert job.status == JobStatus.FAILED
    assert job.retries == 2, "The job should have exhausted the 2 retries limit."
    print(f"[SUCCESS] Rate Limit 429 error handled with complete retries ({job.retries}/2).")


# ==========================================
# 2. DATABASE TESTS
# ==========================================

def test_database_logging_and_history(temp_env):
    """Validates that HistoryManager inserts commands, reads history, and manages metrics asynchronously."""
    print("\n--- Test 2: History Database and Metrics ---")
    
    db_mgr = HistoryManager(temp_env["db_path"])
    
    # Check tables initialized
    conn = sqlite3.connect(temp_env["db_path"])
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    conn.close()

    assert "command_history" in tables
    assert "api_usage" in tables
    assert "metrics" in tables
    
    # Test logging a command
    db_mgr.log_execution(
        input_text="iniciar projeto",
        input_source="voice",
        intent="iniciar_backend",
        risk_level="safe",
        status="success",
        confidence=0.95,
        action_json='{"intent": "iniciar_backend", "steps": []}'
    )

    # Test retrieving last successful action
    last_json = db_mgr.get_last_successful_json()
    assert last_json is not None
    assert "iniciar_backend" in last_json

    # Test retrieving recent history list
    recent = db_mgr.get_recent_history_json(5)
    assert len(recent) == 1

    # Test logging metrics (asynchronous writing)
    db_mgr.log_metric("api_latency", 245.5, tags="gemini")
    db_mgr.log_metric("cache_hit", 0.0)

    # Wait a small moment for thread queue processing
    time.sleep(0.3)
    
    # Query metrics directly
    conn = sqlite3.connect(temp_env["db_path"])
    cursor = conn.cursor()
    cursor.execute("SELECT metric_name, metric_value, tags FROM metrics ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0][0] == "api_latency"
    assert rows[0][1] == 245.5
    assert rows[0][2] == "gemini"

    db_mgr.close()
    print("[SUCCESS] Commands saved, history retrieved, and metrics recorded asynchronously in SQLite.")


# ==========================================
# 3. LLM CACHE TESTS
# ==========================================

def test_llm_cache_operations(temp_env):
    """Validates that SQLiteLLMCache stores instructions uniquely and retrieves them by normalized hash."""
    print("\n--- Test 3: LLM Query Cache (SQLite) ---")
    
    # Using 0.1 seconds TTL to speed up the expiration test (10x faster)
    cache = SQLiteLLMCache(db_path=temp_env["cache_path"], ttl_seconds=0.1)
    
    instruction = "  Abrir o VS CODE agora!  "
    response_data = {
        "type": "action",
        "intent": "programar",
        "explanation": "Abrindo VS Code",
        "steps": [{"type": "open_app", "target": "vscode"}]
    }

    # Cache set
    cache.set(instruction, response_data)

    # Cache get (Hit)
    hit_data = cache.get(instruction)
    assert hit_data is not None
    assert hit_data["intent"] == "programar"
    assert cache.hits == 1

    # Cache get with slightly different spacing/case (Normalization test)
    hit_data_diff = cache.get("abrir o vs code agora")
    assert hit_data_diff is not None
    assert cache.hits == 2

    # Cache miss test
    miss_data = cache.get("outro comando qualquer")
    assert miss_data is None
    assert cache.misses == 1

    # Cache TTL Expiry test (Uses 0.2s sleep now instead of 2.5s)
    time.sleep(0.2)
    expired_data = cache.get(instruction)
    assert expired_data is None, "The cache should have expired."
    
    # Cache stats
    stats = cache.get_stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 2

    # Clear cache
    cache.set(instruction, response_data)
    cache.clear()
    assert cache.get(instruction) is None
    
    print("[SUCCESS] Normalization, hash storage, TTL expiration, and cache statistics verified.")


# ==========================================
# 4. LIGHT STRESS TESTS
# ==========================================

def test_light_stress_on_worker_queue():
    """Submits multiple commands concurrently to the queue and ensures sequential processing without concurrency."""
    print("\n--- Test 4: Light Stress (Worker Queue Concurrency) ---")
    
    task_queue = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()
    
    dispatcher = MagicMock()
    notifier = MagicMock()
    
    executed_jobs = []

    # Setup custom handler mock to capture speed
    def mock_handler_wakeword(job, disp, notif):
        time.sleep(0.01)
        executed_jobs.append(job.payload[0])
        return True

    # Hook into HANDLERS
    from core.execution.worker import HANDLERS
    original_wakeword_handler = HANDLERS[JobType.WAKEWORD]
    HANDLERS[JobType.WAKEWORD] = mock_handler_wakeword

    try:
        # Put 30 jobs in queue quickly
        total_jobs = 30
        for i in range(total_jobs):
            job = Job(type=JobType.WAKEWORD, payload=(f"cmd_{i}", 0.9))
            task_queue.put(job)

        worker_thread = threading.Thread(
            target=command_worker,
            args=(task_queue, dispatcher, notifier, stop_event, worker_busy),
            daemon=True
        )
        worker_thread.start()

        time.sleep(1.0)
        stop_event.set()
        worker_thread.join(timeout=2.0)

        assert len(executed_jobs) == total_jobs, "All 30 jobs should have been executed."
        assert executed_jobs[0] == "cmd_0", "The queue must process sequentially in FIFO order."
        assert executed_jobs[-1] == f"cmd_{total_jobs-1}"
        print(f"[SUCCESS] Queue sequentially processed {total_jobs} concurrent commands without deadlock.")

    finally:
        # Restore original handler
        HANDLERS[JobType.WAKEWORD] = original_wakeword_handler


# ==========================================
# 5. PLUGIN SYSTEM TESTS
# ==========================================

def test_plugin_loading_and_shared_actions_resolution(temp_env):
    """Creates and loads a test YAML plugin, validating shared_actions inheritance and intent mapping."""
    print("\n--- Test 5: YAML Plugin System Loading ---")
    
    plugin_yaml = """
name: "Test Developer Tools"
description: "Plugin de teste do Jarvis"
version: "1.0.0"

shared_actions:
  init_env:
    - type: "system_open"
      target: "notepad.exe"
    - type: "wait"
      duration: 0.5

commands:
  - intent: "test_intent_one"
    phrases:
      - "abrir editor"
      - "iniciar bloco de notas"
    description: "Abre o bloco de notas e digita algo"
    risk_level: "low"
    actions:
      - type: "include"
        name: "init_env"
      - type: "type_and_enter"
        text: "Ola Mundo"
"""
    yaml_file_path = os.path.join(temp_env["plugins_dir"], "test_dev.yaml")
    with open(yaml_file_path, "w", encoding="utf-8") as f:
        f.write(plugin_yaml)

    pm = PluginManager(plugins_dir=temp_env["plugins_dir"])
    
    intents = pm.get_intents()
    assert len(intents) == 1
    assert intents[0]["intent"] == "test_intent_one"
    assert intents[0]["risk_level"] == "low"
    assert "abrir editor" in intents[0]["phrases"]

    actions = pm.get_actions_for_intent("test_intent_one")
    assert actions is not None
    assert len(actions) == 3
    assert actions[0]["type"] == "system_open"
    assert actions[0]["target"] == "notepad.exe"
    assert actions[1]["type"] == "wait"
    assert actions[1]["duration"] == 0.5
    assert actions[2]["type"] == "type_and_enter"
    assert actions[2]["text"] == "Ola Mundo"

    print("[SUCCESS] YAML plugin read correctly, shared_actions expanded, and intent metadata verified.")
