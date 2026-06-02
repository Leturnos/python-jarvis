import queue
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.controller import JarvisController
from core.runtime.state import JarvisState, state_manager


@pytest.fixture(autouse=True)
def reset_state():
    state_manager.set_state(JarvisState.IDLE)
    state_manager._callbacks = []  # Clear callbacks to avoid cross-test interference
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

    automator = MagicMock()
    automator.is_speaking = False

    return {
        "config": config,
        "automator": automator,
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
    controller._read_audio = MagicMock(return_value=(None, 0))

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

    controller._read_audio = MagicMock(side_effect=slow_read)
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
    mock_deps["automator"].speak.assert_called_with("Sim?")


def test_self_healing_dead_silence(mock_deps):
    controller = JarvisController(**mock_deps)
    controller.MAX_ZERO_RMS_BEFORE_RESET = 2
    state_manager.set_state(JarvisState.IDLE)

    pcm = np.zeros(1280, dtype=np.int16)
    rms = 0.0

    def slow_read():
        time.sleep(0.01)
        return pcm, rms

    controller._read_audio = MagicMock(side_effect=slow_read)

    with patch(
        "core.controller.safe_reset_audio",
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
    rms = 20.0

    call_count = 0

    def slow_read():
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        # Force exit after some attempts if approve not called
        if call_count > 20:
            mock_deps["stop_event"].set()
        return pcm, rms

    controller._read_audio = MagicMock(side_effect=slow_read)

    # Setup mock active dialog
    active_dialog = MagicMock()
    mock_deps["dispatcher"].active_dialog = active_dialog
    # When approve is called, stop the loop
    active_dialog.approve.side_effect = lambda: mock_deps["stop_event"].set()

    with patch("core.controller.stt_engine.transcribe", return_value="sim"):
        controller.confirmation_frames = [b"data"] * 11
        controller.start()

        active_dialog.approve.assert_called()
        assert controller.ignore_audio_until > 0
