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


def test_tts_engine_sentence_pipelining():
    config = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        multi = "Primeira frase. Segunda frase! Terceira frase?"
        engine.speak(multi)

        assert engine._speech_queue.get() == "Primeira frase."
        assert engine._speech_queue.get() == "Segunda frase!"
        assert engine._speech_queue.get() == "Terceira frase?"
        assert engine._speech_queue.empty()


def test_tts_engine_clear_queue():
    config = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        engine._preview_voice_override = "jarvis_mk3"
        engine.speak("Frase um. Frase dois.")
        assert not engine._speech_queue.empty()
        engine.clear_queue()
        assert engine._speech_queue.empty()
        assert engine._preview_voice_override is None


def test_tts_engine_evict_cached_models():
    config = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        engine._piper_cache["test_model"] = object()
        assert "test_model" in engine._piper_cache
        engine.evict_cached_models()
        assert len(engine._piper_cache) == 0


def test_tts_engine_debounce_duplicate_speech():
    config = {"tts": {"voice_keyword": "maria", "cooldown_seconds": 2.0}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        # First call enqueues
        engine.speak("Fala idêntica")
        assert engine._speech_queue.qsize() == 1

        # Second rapid consecutive call with same text is debounced
        engine.speak("Fala idêntica")
        assert engine._speech_queue.qsize() == 1

        # Call with different text is queued
        engine.speak("Outra fala")
        assert engine._speech_queue.qsize() == 2


def test_tts_engine_rate_to_length_scale_and_preview():
    config = {"tts": {"voice_keyword": "maria", "active_voice_id": "sapi5_default"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(config)
        # Positive rate speeds up speech (smaller length_scale)
        fast_scale = engine.rate_to_length_scale(5, base_scale=1.0)
        slow_scale = engine.rate_to_length_scale(-5, base_scale=1.0)
        assert fast_scale < 1.0 < slow_scale

        engine.speak("Frase antiga")
        engine.speak_preview("Teste de voz. Segunda parte!", voice_id="jarvis_mk3")
        assert engine._preview_voice_override == "jarvis_mk3"
        assert engine._speech_queue.get() == "Teste de voz."
        assert engine._speech_queue.get() == "Segunda parte!"
