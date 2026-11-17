import queue
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.controller import JarvisController
from core.runtime.state import JarvisState, state_manager


@pytest.fixture(autouse=True)
def mock_activation_manager():
    """Ensure hardware/session states (fullscreen, lock screen) do not interfere with controller tests."""
    with (
        patch("core.activation.ActivationManager.is_fullscreen", return_value=False),
        patch("core.activation.ActivationManager.is_screen_locked", return_value=False),
        patch(
            "core.activation.ActivationManager.is_hotkey_pressed", return_value=False
        ),
    ):
        yield


@pytest.fixture
def mock_deps():
    stop_event = threading.Event()
    config = MagicMock()

    # Ensure config.get returns real values for expected keys
    def config_get_side_effect(key, default=None):
        if key == "jarvis":
            return {"threshold": 0.4, "volume_multiplier": 1.0, "cooldown_seconds": 5}
        return default

    config.get.side_effect = config_get_side_effect

    tts_engine = MagicMock()
    tts_engine.is_speaking = False

    return {
        "config": config,
        "tts_engine": tts_engine,
        "dispatcher": MagicMock(),
        "model": MagicMock(),
        "loaded_names": ["hey_jarvis"],
        "ui": MagicMock(),
        "tray": MagicMock(),
        "task_queue": queue.Queue(),
        "stop_event": stop_event,
        "pa": MagicMock(),
        "stream": MagicMock(),
    }


def test_controller_initialization(mock_deps):
    controller = JarvisController(**mock_deps)
    assert controller.config == mock_deps["config"]
    assert controller.loaded_names == ["hey_jarvis"]
    assert controller.threshold == 0.4


def test_controller_start_stop(mock_deps):
    controller = JarvisController(**mock_deps)
    controller.audio_manager.read_frame = MagicMock(return_value=(None, 0))

    thread = threading.Thread(target=controller.start)
    thread.start()

    time.sleep(0.1)
    mock_deps["stop_event"].set()
    thread.join(timeout=1.0)

    assert not thread.is_alive()


def test_wake_word_detection_idle_to_listening(mock_deps):
    controller = JarvisController(**mock_deps)
    state_manager.set_state(JarvisState.IDLE)

    pcm = np.zeros(1280, dtype=np.int16)
    rms = 30.0

    # Use a safety counter and stop the loop when state changes
    call_count = 0

    def slow_read():
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        if state_manager.get_state() == JarvisState.LISTENING or call_count > 10:
            mock_deps["stop_event"].set()
        return pcm, rms

    controller.audio_manager.read_frame = MagicMock(side_effect=slow_read)
    mock_deps["model"].predict.return_value = {"hey_jarvis": 0.9}

    with (
        patch.object(
            controller.activation_manager, "is_fullscreen", return_value=False
        ),
        patch.object(
            controller.activation_manager, "is_hotkey_pressed", return_value=False
        ),
    ):
        controller.start()

    assert state_manager.get_state() == JarvisState.LISTENING
    mock_deps["tts_engine"].speak.assert_called_with("Sim?")


def test_self_healing_dead_silence(mock_deps):
    controller = JarvisController(**mock_deps)
    controller.MAX_ZERO_RMS_BEFORE_RESET = 2
    state_manager.set_state(JarvisState.IDLE)

    pcm = np.zeros(1280, dtype=np.int16)
    rms = 0.0

    def slow_read():
        time.sleep(0.01)
        return pcm, rms

    controller.audio_manager.read_frame = MagicMock(side_effect=slow_read)

    with patch(
        "core.audio.audio_loop.safe_reset_audio",
        return_value=(mock_deps["pa"], mock_deps["stream"]),
    ) as mock_reset:

        def reset_side_effect(*args, **kwargs):
            mock_deps["stop_event"].set()
            return mock_deps["pa"], mock_deps["stream"]

        mock_reset.side_effect = reset_side_effect
        controller.start()

        assert mock_reset.called


def test_voice_confirmation_approval(mock_deps):
    # For this test, we MUST allow the transition from IDLE to CONFIRMING_DRY_RUN
    # or just start from IDLE and manually trigger the state.
    # The warning "Invalid transition attempt" is fine, it still sets the state.
    state_manager.set_state(JarvisState.CONFIRMING_DRY_RUN)

    controller = JarvisController(**mock_deps)
    pcm = np.zeros(1280, dtype=np.int16)
    rms = 10.0

    call_count = 0

    def slow_read():
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        # Force exit after some attempts if approve not called
        if call_count > 20:
            mock_deps["stop_event"].set()
        return pcm, rms

    controller.audio_manager.read_frame = MagicMock(side_effect=slow_read)

    # Setup mock active dialog
    active_dialog = MagicMock()
    mock_deps["dispatcher"].active_dialog = active_dialog
    # When approve is called, stop the loop
    active_dialog.approve.side_effect = lambda: mock_deps["stop_event"].set()

    with patch("core.controller.stt_engine.transcribe", return_value="sim"):
        controller.confirmation_frames = [b"data"] * 11
        controller.confirmation_silence_start = time.time() - 2.0
        controller.start()

        active_dialog.approve.assert_called()
        assert controller.ignore_audio_until > 0


def test_lock_screen_aborts_listening(mock_deps):
    controller = JarvisController(**mock_deps)
    state_manager.set_state(JarvisState.LISTENING)
    controller.command_frames = [b"audio_chunk"]

    pcm = np.zeros(1280, dtype=np.int16)
    rms = 20.0

    def slow_read():
        if state_manager.get_state() == JarvisState.SUSPENDED:
            mock_deps["stop_event"].set()
        return pcm, rms

    controller.audio_manager.read_frame = MagicMock(side_effect=slow_read)

    with patch.object(
        controller.activation_manager, "is_screen_locked", return_value=True
    ):
        controller.start()

    assert state_manager.get_state() == JarvisState.SUSPENDED
    assert controller.command_frames == []


def test_lock_screen_cancels_confirming_dry_run(mock_deps):
    controller = JarvisController(**mock_deps)
    state_manager.set_state(JarvisState.CONFIRMING_DRY_RUN)
    controller._pending_plan = MagicMock()
    controller.confirmation_frames = [b"audio_chunk"]

    pcm = np.zeros(1280, dtype=np.int16)
    rms = 20.0

    def slow_read():
        if state_manager.get_state() == JarvisState.SUSPENDED:
            mock_deps["stop_event"].set()
        return pcm, rms

    controller.audio_manager.read_frame = MagicMock(side_effect=slow_read)

    with patch.object(
        controller.activation_manager, "is_screen_locked", return_value=True
    ):
        controller.start()

    assert state_manager.get_state() == JarvisState.SUSPENDED
    assert controller._pending_plan is None
    assert controller.confirmation_frames == []


def test_post_execution_transition_resets_model_and_applies_cooldown(mock_deps):
    controller = JarvisController(**mock_deps)
    controller.cooldown = 0
    controller.ignore_audio_until = 0

    # Test EXECUTING -> IDLE
    controller._on_state_change(JarvisState.EXECUTING, JarvisState.IDLE, None)
    mock_deps["model"].reset.assert_called()
    assert controller.cooldown > time.time()
    assert controller.ignore_audio_until > time.time()

    # Reset mocks
    mock_deps["model"].reset.reset_mock()
    controller.cooldown = 0
    controller.ignore_audio_until = 0

    # Test THINKING -> IDLE
    controller._on_state_change(JarvisState.THINKING, JarvisState.IDLE, None)
    mock_deps["model"].reset.assert_called_once()
    assert controller.cooldown > time.time()
    assert controller.ignore_audio_until > time.time()


def test_handle_idle_updates_ui_status_to_pronto(mock_deps):
    from core.activation import ActivationContext

    controller = JarvisController(**mock_deps)
    controller.cooldown = 0  # Cooldown passed

    pcm = np.zeros(1280, dtype=np.int16)
    context = ActivationContext(
        wakeword_score=0.0,
        wakeword_detected=None,
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=time.time() + 10.0,
    )

    controller._handle_idle(pcm, rms=5.0, context=context)
    mock_deps["ui"].update.assert_any_call(status="Pronto")


def test_post_speech_guard_resets_model_and_anchors_command_start_time(mock_deps):
    controller = JarvisController(**mock_deps)
    controller.post_speech_guard_seconds = 0.05
    controller._enter_listening_state()

    pcm = np.zeros(1280, dtype=np.int16)
    step = 0

    def frame_gen():
        nonlocal step
        step += 1
        if step in (1, 2):
            # Simulate cold ONNX loading/synthesis (>0s) while is_speaking is still False
            mock_deps["tts_engine"].is_speaking = False
            mock_deps["tts_engine"].has_pending_speech = True
        elif step == 3:
            # Playback starts
            mock_deps["tts_engine"].is_speaking = True
            mock_deps["tts_engine"].has_pending_speech = True
        elif step == 4:
            # Playback ends: _was_speaking edge must refresh ignore_audio_until & clear buffers
            mock_deps["tts_engine"].is_speaking = False
            mock_deps["tts_engine"].has_pending_speech = False
        elif step == 5:
            # Guard window has now elapsed; first true listening frame starts capture
            time.sleep(0.06)
        else:
            mock_deps["stop_event"].set()
            return None, 0.0
        return pcm, 5.0

    controller.audio_manager.read_frame = MagicMock(side_effect=frame_gen)
    controller.start()

    assert controller.command_start_time is not None
    assert len(controller.command_frames) == 1
    assert mock_deps["model"].reset.call_count >= 2


def test_confirming_dry_run_skips_stt_while_tts_synthesizing(mock_deps):
    controller = JarvisController(**mock_deps)
    state_manager.set_state(JarvisState.CONFIRMING_DRY_RUN)
    controller.ignore_audio_until = 0.0

    pcm = np.zeros(1280, dtype=np.int16)
    step = 0

    def frame_gen():
        nonlocal step
        step += 1
        if step <= 3:
            mock_deps["tts_engine"].is_speaking = False
            mock_deps["tts_engine"].has_pending_speech = True
            controller.confirmation_silence_start = time.time() - 2.0
        else:
            mock_deps["stop_event"].set()
        return pcm, 5.0

    controller.audio_manager.read_frame = MagicMock(side_effect=frame_gen)
    with patch("core.controller.stt_engine.transcribe") as mock_transcribe:
        controller.start()

    mock_transcribe.assert_not_called()
    assert controller.confirmation_frames == []


@pytest.mark.parametrize("initial_state", [JarvisState.SLEEPING, JarvisState.SUSPENDED])
def test_wake_from_sleeping_or_suspended_preloads_stt_async(mock_deps, initial_state):
    from core.activation import ActivationAction, ActivationActionType

    controller = JarvisController(**mock_deps)
    state_manager.set_state(initial_state)

    pcm = np.zeros(1280, dtype=np.int16)
    controller.audio_manager.read_frame = MagicMock(return_value=(pcm, 5.0))
    controller.activation_manager.evaluate = MagicMock(
        return_value=ActivationAction(ActivationActionType.TRIGGER_PTT_START, "PTT")
    )

    started = threading.Event()
    release = threading.Event()

    def slow_stt_load():
        started.set()
        release.wait(timeout=2.0)

    def stop_on_enter():
        mock_deps["stop_event"].set()
        state_manager.set_state(JarvisState.LISTENING)

    with (
        patch("core.controller.stt_engine.model", None),
        patch(
            "core.controller.stt_engine.load", side_effect=slow_stt_load
        ) as mock_load,
        patch.object(controller, "_enter_listening_state", side_effect=stop_on_enter),
    ):
        # controller.start() must return immediately even while slow_stt_load blocks
        controller.start()
        assert started.wait(timeout=1.0)
        release.set()
        mock_load.assert_called_once()
