import queue
import threading
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.execution.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from core.execution.job_queue import Job, JobStatus, JobType, job_manager
from core.execution.worker import (
    _handle_create_macro,
    _handle_llm,
    _handle_replay,
    _handle_wakeword,
    command_worker,
)
from core.llm import LLMAuthenticationError, LLMRateLimitError
from core.media.models import AutoplayStrategy
from core.runtime.state import JarvisState, state_manager
from core.shared.errors import BusinessError, TechnicalError


@pytest.fixture
def clean_job_history() -> Generator[None]:
    job_manager.history.clear()
    yield
    job_manager.history.clear()


@patch("core.execution.worker.pythoncom")
def test_command_worker_lifecycle(
    mock_pythoncom: MagicMock, mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies that command_worker initializes pythoncom and stops when stop_event is set."""
    task_queue: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    # Start thread
    stop_event.set()  # Stop immediately
    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    mock_pythoncom.CoInitialize.assert_called_once()
    mock_pythoncom.CoUninitialize.assert_called_once()


def test_handle_wakeword_success(
    mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies that _handle_wakeword triggers dispatcher correctly."""
    # Payload is tuple
    job = Job(type=JobType.WAKEWORD, payload=("hey_jarvis", 0.85))
    assert _handle_wakeword(job, mock_dispatcher, mock_notifier) is True

    mock_notifier.notify.assert_called_with(
        "Jarvis", "Comando 'hey_jarvis' detectado! (Score: 0.85)"
    )
    mock_dispatcher.handle.assert_called_with("hey_jarvis", confidence=0.85)

    # Payload is float
    job_float = Job(type=JobType.WAKEWORD, payload=0.72)
    assert _handle_wakeword(job_float, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.handle.assert_called_with("unknown", confidence=0.72)


def test_handle_replay_success(
    mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies _handle_replay triggers dispatcher's replay command."""
    job = Job(type=JobType.REPLAY, payload=None)
    mock_dispatcher.replay_last_command.return_value = True
    assert _handle_replay(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.replay_last_command.assert_called_once()


def test_handle_create_macro_success(
    mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies _handle_create_macro triggers dispatcher's macro creation."""
    job = Job(type=JobType.CREATE_MACRO, payload={"n": 4})
    mock_dispatcher.initiate_macro_creation.return_value = True
    assert _handle_create_macro(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.initiate_macro_creation.assert_called_with(n=4)

    # Missing payload dictionary, fallback to default 3
    job_no_payload = Job(type=JobType.CREATE_MACRO, payload=None)
    assert _handle_create_macro(job_no_payload, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.initiate_macro_creation.assert_called_with(n=3)


@patch("core.execution.worker.stt_engine")
def test_handle_llm_silent_audio(
    mock_stt: MagicMock, mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies that silent PCM audio returns True and speaks apology."""
    # 100 bytes of zeros
    silent_audio = b"\x00" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=silent_audio)

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.tts_engine.speak.assert_called_with("Desculpe, não ouvi nada.")


@patch("core.execution.worker.stt_engine")
def test_handle_llm_stt_empty(
    mock_stt: MagicMock, mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies that empty STT transcription results in apology and returns True."""
    # Simulating sound (non-silent PCM bytes)
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = ""

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.tts_engine.speak.assert_called_with("Desculpe, não entendi.")


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.plugin_manager")
def test_handle_llm_resolved_plugin_action(
    mock_plugins: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies that a locally resolved command is dispatched directly without calling the LLM."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "abrir notepad"

    # Mock resolved result
    mock_result = MagicMock()
    mock_result.is_system = False
    mock_result.intent_name = "notepad"
    mock_result.source = "local_fuzzy"
    mock_result.confidence = 0.9
    mock_resolver.resolve.return_value = mock_result

    # Mock intents risk level
    mock_plugins.get_intents.return_value = [
        {"intent": "notepad", "risk_level": "safe"}
    ]

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.handle_dynamic.assert_called_with(
        {"action": "plugin", "intent": "notepad", "risk_level": "safe"}
    )


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.HANDLERS")
def test_handle_llm_resolved_system_command(
    mock_handlers: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies that a locally resolved system command (like replay) is delegated to its system handler."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "repetir comando"

    # Mock system command result
    mock_result = MagicMock()
    mock_result.is_system = True
    mock_result.intent_name = "replay"
    mock_result.source = "exact"
    mock_resolver.resolve.return_value = mock_result

    mock_replay_handler = MagicMock(return_value=True)
    mock_handlers.__getitem__.return_value = mock_replay_handler

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_replay_handler.assert_called_once()
    assert mock_replay_handler.call_args[0][0].type == JobType.REPLAY


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
def test_handle_llm_fallback_chat(
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies LLM fallback when local match fails, resulting in a chat action."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "quantas horas"
    mock_resolver.resolve.return_value = None

    # LLM returns a chat response
    mock_llm.process_instruction.return_value = {
        "type": "chat",
        "response": "São 15 horas",
    }

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.handle_dynamic.assert_called_with(
        {"type": "chat", "response": "São 15 horas"}
    )


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
@patch("core.media.resolver.MediaResolver")
def test_handle_llm_fallback_media_tab_enter(
    mock_media_resolver_cls: MagicMock,
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies LLM fallback handles media intent with AutoplayStrategy.TAB_ENTER."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "tocar linkin park"
    mock_resolver.resolve.return_value = None

    # LLM returns media json
    mock_llm.process_instruction.return_value = {
        "type": "media",
        "action": "play_query",
        "query": "linkin park",
        "query_type": "entity",
        "description": "Tocar linkin park",
    }

    # Mock MediaResolver resolve_intent
    mock_media_resolver = MagicMock()
    mock_media_resolver_cls.return_value = mock_media_resolver

    mock_resolved_plan = MagicMock()
    mock_resolved_plan.steps = [
        ExecutionStep(
            type=StepType.COMMAND,
            payload={"target": "spotify:artist:abc"},
            description="Play artist",
        )
    ]

    mock_resolved_plan.strategy = AutoplayStrategy.TAB_ENTER
    mock_media_resolver.resolve_intent.return_value = mock_resolved_plan

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True

    # The dispatcher should have received an ExecutionPlan containing the initial step + the SPOTIFY_CLICK_PLAY step
    mock_dispatcher.handle_plan.assert_called_once()
    plan = mock_dispatcher.handle_plan.call_args[0][0]
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.steps) == 2
    assert plan.steps[1].type == StepType.SPOTIFY_CLICK_PLAY
    assert plan.steps[1].payload["click_type"] == "search"


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
@patch("core.media.resolver.MediaResolver")
def test_handle_llm_fallback_media_media_key(
    mock_media_resolver_cls: MagicMock,
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies LLM fallback handles media intent with AutoplayStrategy.MEDIA_KEY."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "tocar linkin park"
    mock_resolver.resolve.return_value = None

    mock_llm.process_instruction.return_value = {
        "type": "media",
        "action": "play_query",
        "query": "linkin park",
        "query_type": "entity",
        "description": "Tocar linkin park",
    }

    mock_media_resolver = MagicMock()
    mock_media_resolver_cls.return_value = mock_media_resolver

    mock_resolved_plan = MagicMock()
    mock_resolved_plan.steps = [
        ExecutionStep(
            type=StepType.COMMAND,
            payload={"target": "spotify:artist:abc"},
            description="Play artist",
        )
    ]

    mock_resolved_plan.strategy = AutoplayStrategy.MEDIA_KEY
    mock_media_resolver.resolve_intent.return_value = mock_resolved_plan

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True

    mock_dispatcher.handle_plan.assert_called_once()
    plan = mock_dispatcher.handle_plan.call_args[0][0]
    assert len(plan.steps) == 2
    assert plan.steps[1].type == StepType.SPOTIFY_CLICK_PLAY
    assert plan.steps[1].payload["click_type"] == "playlist"


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
@patch("core.media.resolver.MediaResolver")
def test_handle_llm_fallback_media_resolver_fails(
    mock_media_resolver_cls: MagicMock,
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies media intent fails gracefully and return True if resolver fails."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "tocar linkin park"
    mock_resolver.resolve.return_value = None

    mock_llm.process_instruction.return_value = {
        "type": "media",
        "action": "play_query",
    }

    mock_media_resolver = MagicMock()
    mock_media_resolver_cls.return_value = mock_media_resolver
    mock_media_resolver.resolve_intent.return_value = None

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.tts_engine.speak.assert_called_with(
        "Desculpe, não consegui preparar a mídia."
    )


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
@patch("core.execution.worker.HANDLERS")
def test_handle_llm_fallback_system_command(
    mock_handlers: MagicMock,
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies that system commands matched by the LLM (like replay) are correctly routed."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "repetir ultimo"
    mock_resolver.resolve.return_value = None

    # LLM identifies it is a system command
    mock_llm.process_instruction.return_value = {"intent": "replay"}

    mock_replay_handler = MagicMock(return_value=True)
    mock_handlers.__getitem__.return_value = mock_replay_handler

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_replay_handler.assert_called_once()


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
def test_handle_llm_fallback_plan(
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies standard execution plans generated by the LLM are handled properly."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "abrir notepad e escrever ola"
    mock_resolver.resolve.return_value = None

    # LLM returns structured plan
    mock_llm.process_instruction.return_value = {
        "intent": "notepad_custom",
        "description": "Custom notepad operation",
        "global_risk": "safe",
        "steps": [
            {
                "type": "run_command",
                "payload": {"command": "notepad.exe"},
                "description": "abrir notepad",
            },
            {
                "type": "keyboard_type",
                "payload": {"text": "ola"},
                "description": "digitar ola",
            },
        ],
    }

    assert _handle_llm(job, mock_dispatcher, mock_notifier) is True
    mock_dispatcher.handle_plan.assert_called_once()
    plan = mock_dispatcher.handle_plan.call_args[0][0]
    assert plan.intent == "notepad_custom"
    assert len(plan.steps) == 2


@patch("core.execution.worker.stt_engine")
@patch("core.execution.worker.resolver")
@patch("core.execution.worker.llm_agent")
def test_handle_llm_technical_error_on_api_fail(
    mock_llm: MagicMock,
    mock_resolver: MagicMock,
    mock_stt: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
) -> None:
    """Verifies that an API failure in LLM agent raises a TechnicalError in the worker."""
    loud_audio = b"\x10\x10" * 100
    job = Job(type=JobType.LLM_DYNAMIC, payload=loud_audio)
    mock_stt.transcribe.return_value = "abrir notepad"
    mock_resolver.resolve.return_value = None

    # LLM fails to process (returns None)
    mock_llm.process_instruction.return_value = None

    with pytest.raises(TechnicalError, match="LLM processing failed"):
        _handle_llm(job, mock_dispatcher, mock_notifier)


@patch("core.execution.worker.pythoncom")
@patch("core.execution.worker.HANDLERS")
@patch("core.execution.worker.time.sleep")  # mock backoff sleep
def test_worker_thread_retry_on_technical_error(
    mock_sleep: MagicMock,
    mock_handlers: MagicMock,
    mock_pythoncom: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
    clean_job_history: Any,
) -> None:
    """Verifies that command_worker retries jobs that raise TechnicalError, applying exponential backoff."""
    task_queue: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    job = Job(type=JobType.LLM_DYNAMIC, payload=b"audio_payload")
    task_queue.put(job)

    # Mock handler raises TechnicalError first time, succeeds the second time
    calls = 0

    def side_effect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TechnicalError("Network issue")
        return True

    mock_handlers.get.return_value = side_effect

    # Run loop once and stop
    def stop_worker(*args, **kwargs):
        stop_event.set()

    state_manager.add_callback(
        lambda o, n, c: stop_worker() if n == JarvisState.IDLE else None
    )

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    assert job.status == JobStatus.COMPLETED
    assert job.retries == 1
    mock_sleep.assert_called_once_with(2)  # backoff = 2**1


@patch("core.execution.worker.pythoncom")
@patch("core.execution.worker.HANDLERS")
def test_worker_thread_fails_on_business_error(
    mock_handlers: MagicMock,
    mock_pythoncom: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
    clean_job_history: Any,
) -> None:
    """Verifies that command_worker immediately fails job and does not retry on BusinessError."""
    task_queue: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    job = Job(type=JobType.LLM_DYNAMIC, payload=b"audio_payload")
    task_queue.put(job)

    # Mock handler raises BusinessError
    mock_handlers.get.return_value = MagicMock(
        side_effect=BusinessError("Empty history")
    )

    # Run loop once and stop
    def stop_worker(*args, **kwargs):
        stop_event.set()

    state_manager.add_callback(
        lambda o, n, c: stop_worker() if n == JarvisState.IDLE else None
    )

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    assert job.status == JobStatus.FAILED
    assert job.retries == 0
    assert job.error == "Empty history"


@patch("core.execution.worker.pythoncom")
@patch("core.execution.worker.HANDLERS")
def test_worker_thread_fails_on_unexpected_exception(
    mock_handlers: MagicMock,
    mock_pythoncom: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
    clean_job_history: Any,
) -> None:
    """Verifies that command_worker fails job and does not retry on generic unexpected exception."""
    task_queue: queue.Queue[Any] = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    job = Job(type=JobType.LLM_DYNAMIC, payload=b"audio_payload")
    task_queue.put(job)

    mock_handlers.get.return_value = MagicMock(
        side_effect=ValueError("Unexpected crash")
    )

    def stop_worker(*args, **kwargs):
        stop_event.set()

    state_manager.add_callback(
        lambda o, n, c: stop_worker() if n == JarvisState.IDLE else None
    )

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    assert job.status == JobStatus.FAILED
    assert job.retries == 0
    assert job.error == "Unexpected crash"


@patch("core.execution.worker.pythoncom")
def test_worker_thread_ignores_non_jobs(
    mock_pythoncom: MagicMock, mock_dispatcher: MagicMock, mock_notifier: MagicMock
) -> None:
    """Verifies that non-Job instances in queue are popped and ignored."""
    task_queue = MagicMock()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    def side_effect(timeout=None):
        if not stop_event.is_set():
            stop_event.set()
            return "not a job"
        raise queue.Empty()

    task_queue.get.side_effect = side_effect

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    task_queue.task_done.assert_called_once()


@patch("core.execution.worker.pythoncom")
@patch("core.execution.worker.HANDLERS")
def test_worker_thread_speaks_on_llm_auth_and_quota_errors(
    mock_handlers: MagicMock,
    mock_pythoncom: MagicMock,
    mock_dispatcher: MagicMock,
    mock_notifier: MagicMock,
    clean_job_history: Any,
) -> None:
    """Verifies that command_worker speaks specific messages for auth and quota exhaustion and skips retries."""
    # 1. Test Auth Error
    task_queue = queue.Queue()
    stop_event = threading.Event()
    worker_busy = threading.Event()

    job_auth = Job(type=JobType.LLM_DYNAMIC, payload=b"audio")
    task_queue.put(job_auth)

    auth_err = LLMAuthenticationError("Invalid API key")
    te_auth = TechnicalError("LLM failed")
    te_auth.__cause__ = auth_err

    mock_handlers.get.return_value = MagicMock(side_effect=te_auth)

    def stop_worker(*args, **kwargs):
        stop_event.set()

    state_manager.add_callback(
        lambda o, n, c: stop_worker() if n == JarvisState.IDLE else None
    )

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    assert job_auth.status == JobStatus.FAILED
    assert job_auth.retries == 0
    mock_dispatcher.tts_engine.speak.assert_called_with(
        "Chave de API inválida ou não configurada."
    )

    # 2. Test Quota Exhausted Error (Rate limit with status_code == 429)
    stop_event.clear()
    job_quota = Job(type=JobType.LLM_DYNAMIC, payload=b"audio")
    task_queue.put(job_quota)

    rate_err = LLMRateLimitError("Resource exhausted")
    rate_err.status_code = 429
    te_rate = TechnicalError("LLM failed")
    te_rate.__cause__ = rate_err

    mock_handlers.get.return_value = MagicMock(side_effect=te_rate)

    command_worker(task_queue, mock_dispatcher, mock_notifier, stop_event, worker_busy)

    assert job_quota.status == JobStatus.FAILED
    assert job_quota.retries == 0
    mock_dispatcher.tts_engine.speak.assert_called_with(
        "Desculpe, estou sem cota ou créditos no provedor de IA no momento."
    )
