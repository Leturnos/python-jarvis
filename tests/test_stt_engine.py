import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from core.audio.stt_engine import STTEngine

@pytest.fixture
def mock_whisper():
    with patch('core.audio.stt_engine.WhisperModel') as mock:
        yield mock

def test_stt_transcription_success(mock_whisper):
    # Mock return value of model.transcribe
    mock_model_instance = mock_whisper.return_value
    
    # segments is an iterable of segment objects with a .text attribute
    segment_mock = MagicMock()
    segment_mock.text = "Olá mundo"
    mock_model_instance.transcribe.return_value = ([segment_mock], MagicMock())
    
    engine = STTEngine(model_size="tiny")
    
    # Dummy audio (1 second of silence at 16k)
    audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
    
    result = engine.transcribe(audio_bytes)
    
    assert result == "Olá mundo"
    mock_model_instance.transcribe.assert_called()

def test_stt_transcription_empty_audio(mock_whisper):
    mock_model_instance = mock_whisper.return_value
    mock_model_instance.transcribe.return_value = ([], MagicMock())
    
    engine = STTEngine(model_size="tiny")
    
    result = engine.transcribe(b"")
    
    assert result == ""

def test_stt_transcription_error(mock_whisper):
    mock_model_instance = mock_whisper.return_value
    mock_model_instance.transcribe.side_effect = Exception("Model crash")
    
    engine = STTEngine(model_size="tiny")
    
    with pytest.raises(Exception) as excinfo:
        engine.transcribe(b"some audio data")
    
    assert "STT processing failed" in str(excinfo.value)
