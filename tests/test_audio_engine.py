import pytest
from unittest.mock import MagicMock, patch, ANY
from core.audio.audio_engine import get_audio_stream, safe_reset_audio

@patch('core.audio.audio_engine.pyaudio.PyAudio')
def test_get_audio_stream(mock_pyaudio):
    mock_pa_instance = MagicMock()
    mock_pyaudio.return_value = mock_pa_instance
    mock_stream = MagicMock()
    mock_pa_instance.open.return_value = mock_stream
    
    pa, stream = get_audio_stream()
    
    assert pa == mock_pa_instance
    assert stream == mock_stream
    mock_pa_instance.open.assert_called_once_with(
        rate=16000,
        channels=1,
        format=ANY,
        input=True,
        frames_per_buffer=1280
    )

@patch('core.audio.audio_engine.get_audio_stream')
def test_safe_reset_audio(mock_get_stream):
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    
    mock_new_pa = MagicMock()
    mock_new_stream = MagicMock()
    mock_get_stream.return_value = (mock_new_pa, mock_new_stream)
    
    # Patch time.sleep to speed up tests
    with patch('core.audio.audio_engine.time.sleep'):
        new_pa, new_stream = safe_reset_audio(mock_pa, mock_stream)
    
    mock_stream.stop_stream.assert_called_once()
    mock_stream.close.assert_called_once()
    mock_pa.terminate.assert_called_once()
    assert new_pa == mock_new_pa
    assert new_stream == mock_new_stream

@patch('core.audio.audio_engine.pyaudio.PyAudio')
def test_safe_reset_audio_handles_none(mock_pyaudio):
    # If pa and stream are None
    with patch('core.audio.audio_engine.time.sleep'):
        with patch('core.audio.audio_engine.get_audio_stream', return_value=(MagicMock(), MagicMock())):
            safe_reset_audio(None, None)
    # Should not raise exception
