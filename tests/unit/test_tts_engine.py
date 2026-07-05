from unittest.mock import patch

from core.audio.tts_engine import TTSEngine


def test_tts_engine_lifecycle():
    config = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        assert engine.is_speaking is False
        engine.speak("Test speech")
        assert engine._speech_queue.get() == "Test speech"
        engine.stop()
        assert engine._stop_tts.is_set()
