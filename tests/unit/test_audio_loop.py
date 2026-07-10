from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from core.audio.audio_loop import AudioLoopManager


@pytest.fixture
def base_components():
    config = {
        "jarvis": {"volume_multiplier": 1.5},
        "voice_activation": {"thresholds": {"max_zero_rms_frames": 1}},
    }
    dispatcher = MagicMock()
    ui = MagicMock()
    pa = MagicMock()
    stream = MagicMock()
    return config, dispatcher, ui, pa, stream


def test_audio_loop_manager_read_frame_success(base_components):
    config, dispatcher, ui, pa, stream = base_components

    # Create fake 1280 sample PCM buffer
    fake_pcm = np.ones(1280, dtype=np.int16) * 10
    stream.read.return_value = fake_pcm.tobytes()

    manager = AudioLoopManager(config, dispatcher, ui, pa, stream)
    pcm, rms = manager.read_frame()

    # Verify mock read and calculations
    assert pcm is not None
    assert len(pcm) == 1280
    assert pcm[0] == 15  # 10 * 1.5 volume multiplier
    assert rms > 0.0
    stream.read.assert_called_once_with(1280, exception_on_overflow=False)


@patch("core.audio.audio_loop.safe_reset_audio")
def test_audio_loop_manager_read_frame_reset_on_error(mock_reset, base_components):
    config, dispatcher, ui, pa, stream = base_components
    stream.read.side_effect = Exception("Hardware disconnected")

    new_pa = MagicMock()
    new_stream = MagicMock()
    mock_reset.return_value = (new_pa, new_stream)

    stop_event = MagicMock()
    stop_event.is_set.return_value = False

    manager = AudioLoopManager(
        config, dispatcher, ui, pa, stream, stop_event=stop_event
    )
    pcm, rms = manager.read_frame()

    assert pcm is None
    assert rms == 0.0
    mock_reset.assert_called_once_with(pa, stream)
    assert manager.pa == new_pa
    assert manager.stream == new_stream
    assert dispatcher.audio_stream == new_stream


@patch("core.audio.audio_loop.safe_reset_audio")
def test_audio_loop_manager_self_healing_dead_silence(mock_reset, base_components):
    config, dispatcher, ui, pa, stream = base_components
    mock_reset.return_value = (pa, stream)

    manager = AudioLoopManager(config, dispatcher, ui, pa, stream)
    model = MagicMock()

    # Zero volume frames
    # First frame of zero (consecutive_zero_rms becomes 1, 1 > 1 is False)
    healing_triggered = manager.check_dead_silence(0.0, model)
    assert healing_triggered is False

    # Second frame of zero (consecutive_zero_rms becomes 2, 2 > 1 is True) -> triggers healing
    healing_triggered = manager.check_dead_silence(0.0, model)
    assert healing_triggered is True

    mock_reset.assert_called_once_with(pa, stream)
    model.reset.assert_called_once()
    assert manager.consecutive_zero_rms == 0


def test_audio_loop_manager_read_frame_error_with_stop_event(base_components):
    config, dispatcher, ui, pa, stream = base_components
    stream.read.side_effect = Exception("Hardware closed on shutdown")

    stop_event = MagicMock()
    stop_event.is_set.return_value = True

    manager = AudioLoopManager(
        config, dispatcher, ui, pa, stream, stop_event=stop_event
    )

    with patch("core.audio.audio_loop.safe_reset_audio") as mock_reset:
        pcm, rms = manager.read_frame()
        assert pcm is None
        assert rms == 0.0
        # Should not reset audio device if stop event is set
        mock_reset.assert_not_called()


def test_audio_loop_manager_cleanup_success(base_components):
    config, dispatcher, ui, pa, stream = base_components
    manager = AudioLoopManager(config, dispatcher, ui, pa, stream)

    manager.cleanup()

    stream.stop_stream.assert_called_once()
    stream.close.assert_called_once()
    pa.terminate.assert_called_once()


def test_audio_loop_manager_cleanup_exception_handling(base_components):
    config, dispatcher, ui, pa, stream = base_components
    stream.stop_stream.side_effect = Exception("PyAudio hardware lock")

    manager = AudioLoopManager(config, dispatcher, ui, pa, stream)

    # Should not raise exception
    try:
        manager.cleanup()
    except Exception as e:
        pytest.fail(f"cleanup raised an exception: {e}")


def test_audio_loop_manager_read_frame_no_volume_multiplier(base_components):
    config, dispatcher, ui, pa, stream = base_components
    config["jarvis"]["volume_multiplier"] = 1.0

    fake_pcm = np.ones(1280, dtype=np.int16) * 10
    stream.read.return_value = fake_pcm.tobytes()

    manager = AudioLoopManager(config, dispatcher, ui, pa, stream)
    pcm, rms = manager.read_frame()

    assert pcm is not None
    assert pcm[0] == 10  # multiplier 1.0, value is unchanged
