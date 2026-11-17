from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

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


def test_trim_pcm_silence_removes_outer_silence_with_margin():
    sample_rate = 1000  # 1 sample == 1 ms for simple boundary assertions
    lead = np.zeros(200, dtype=np.int16)
    speech = np.full(100, 3000, dtype=np.int16)
    tail = np.zeros(500, dtype=np.int16)
    pcm = np.concatenate([lead, speech, tail])

    trimmed = TTSEngine.trim_pcm_silence(
        pcm, sample_rate=sample_rate, threshold=250, margin_ms=25.0
    )
    # 100 active samples + 25 leading + 25 trailing = 150 samples
    assert trimmed.size == 150
    assert np.all(trimmed[:25] == 0)
    assert np.all(trimmed[25:125] == 3000)
    assert np.all(trimmed[125:] == 0)

    # All-silent input is returned untouched without crashing
    silent = np.zeros(100, dtype=np.int16)
    assert TTSEngine.trim_pcm_silence(silent, sample_rate=sample_rate).size == 100


def test_piper_cache_evicts_inactive_session_in_ram(tmp_path):
    onnx_a = tmp_path / "a.onnx"
    json_a = tmp_path / "a.onnx.json"
    onnx_b = tmp_path / "b.onnx"
    json_b = tmp_path / "b.onnx.json"
    for p in (onnx_a, json_a, onnx_b, json_b):
        p.write_bytes(b"dummy")

    config = {"tts": {"voice_keyword": "maria"}}
    with (
        patch("core.audio.tts_engine.threading.Thread"),
        patch("core.audio.tts_engine.Piper", side_effect=["sess_a", "sess_b"]),
    ):
        engine = TTSEngine(config)
        first = engine._get_or_load_piper("voice_a", str(onnx_a), str(json_a))
        assert first == "sess_a"
        assert list(engine._piper_cache.keys()) == ["voice_a"]

        second = engine._get_or_load_piper("voice_b", str(onnx_b), str(json_b))
        assert second == "sess_b"
        assert list(engine._piper_cache.keys()) == ["voice_b"]
        # Disk files for evicted RAM session must remain intact
        assert onnx_a.exists() and json_a.exists()
        assert onnx_b.exists() and json_b.exists()


def test_prewarm_active_voice_respects_lazy_load_profile():
    # Balanced profile (lazy_load_secondary_modules=True) must NOT prewarm on boot
    balanced_cfg = {
        "tts": {"active_voice_id": "jarvis_mk3"},
        "runtime": {"memory_optimization": {"lazy_load_secondary_modules": True}},
    }
    with (
        patch("core.audio.tts_engine.threading.Thread"),
        patch.object(TTSEngine, "_get_or_load_piper") as mock_load,
    ):
        engine = TTSEngine(balanced_cfg)
        engine._prewarm_active_voice_if_configured()
        mock_load.assert_not_called()

    # Performance profile (lazy_load_secondary_modules=False) DOES prewarm installed voice
    perf_cfg = {
        "tts": {"active_voice_id": "jarvis_mk3"},
        "runtime": {"memory_optimization": {"lazy_load_secondary_modules": False}},
    }
    with (
        patch("core.audio.tts_engine.threading.Thread"),
        patch.object(TTSEngine, "_get_or_load_piper") as mock_load,
    ):
        engine = TTSEngine(perf_cfg)
        engine.voice_manager = MagicMock()
        engine.voice_manager.get_model_paths.return_value = (
            Path("jarvis_mk3.onnx"),
            Path("jarvis_mk3.onnx.json"),
        )
        engine._prewarm_active_voice_if_configured()
        mock_load.assert_called_once_with(
            "jarvis_mk3", "jarvis_mk3.onnx", "jarvis_mk3.onnx.json"
        )


def test_tts_worker_sets_is_speaking_only_during_playback():
    cfg = {"tts": {"active_voice_id": "jarvis_mk3", "rate": 2, "volume": 100}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(cfg)

    observed_during_synth: list[bool] = []
    observed_during_play: list[bool] = []

    def fake_synth(**_kwargs):
        observed_during_synth.append(engine.is_speaking)
        return np.ones(100, dtype=np.int16), 22050

    def fake_play(*_args, **_kwargs):
        observed_during_play.append(engine.is_speaking)
        engine._stop_tts.set()

    engine.speak("Sim?")
    with (
        patch("core.audio.tts_engine.pythoncom.CoInitialize"),
        patch("core.audio.tts_engine.pythoncom.CoUninitialize"),
        patch("core.audio.tts_engine.win32com.client.Dispatch"),
        patch("core.audio.tts_engine.create_pyaudio", return_value=MagicMock()),
        patch("core.audio.tts_engine.terminate_pyaudio"),
        patch.object(engine, "_synthesize_neural", side_effect=fake_synth),
        patch.object(engine, "_play_pcm_int16", side_effect=fake_play),
    ):
        engine._tts_worker()

    assert observed_during_synth == [False]
    assert observed_during_play == [True]
    assert engine.is_speaking is False


def test_has_pending_speech_lifecycle_and_clear_queue():
    cfg = {"tts": {"active_voice_id": "jarvis_mk3", "rate": 2, "volume": 100}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(cfg)

    assert engine.has_pending_speech is False
    engine.speak("Frase um. Frase dois.")
    assert engine.has_pending_speech is True

    engine.clear_queue()
    assert engine.has_pending_speech is False

    observed_pending_in_synth: list[bool] = []

    def fake_synth(**_kwargs):
        observed_pending_in_synth.append(engine.has_pending_speech)
        return np.ones(100, dtype=np.int16), 22050

    def fake_play(*_args, **_kwargs):
        engine._stop_tts.set()

    engine._abort_current.clear()
    engine._stop_tts.clear()
    engine.speak("Sim?")
    assert engine.has_pending_speech is True
    with (
        patch("core.audio.tts_engine.pythoncom.CoInitialize"),
        patch("core.audio.tts_engine.pythoncom.CoUninitialize"),
        patch("core.audio.tts_engine.win32com.client.Dispatch"),
        patch("core.audio.tts_engine.create_pyaudio", return_value=MagicMock()),
        patch("core.audio.tts_engine.terminate_pyaudio"),
        patch.object(engine, "_synthesize_neural", side_effect=fake_synth),
        patch.object(engine, "_play_pcm_int16", side_effect=fake_play),
    ):
        engine._tts_worker()

    assert observed_pending_in_synth == [True]
    assert engine.has_pending_speech is False


def test_play_pcm_int16_stream_reuse_rate_change_and_fallback():
    cfg = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(cfg)

    pa = MagicMock()
    stream_22k = MagicMock()
    stream_22k.get_output_latency.return_value = 0.01
    stream_16k = MagicMock()
    stream_16k.get_output_latency.return_value = 0.01
    pa.open.side_effect = [stream_22k, stream_16k]

    pcm = np.full(100, 1000, dtype=np.int16)

    # 1. First call opens stream; second call at same rate reuses it without stop/close
    engine._play_pcm_int16(pcm, 22050, pa=pa)
    engine._play_pcm_int16(pcm, 22050, pa=pa)
    assert pa.open.call_count == 1
    assert stream_22k.write.call_count >= 2
    stream_22k.stop_stream.assert_not_called()
    stream_22k.get_output_latency.assert_called()

    # 2. Sample rate change closes previous stream and opens a new one
    engine._play_pcm_int16(pcm, 16000, pa=pa)
    assert pa.open.call_count == 2
    stream_22k.stop_stream.assert_called_once()
    stream_22k.close.assert_called_once()

    # 3. Write failure closes cached stream and triggers winsound fallback
    stream_16k.write.side_effect = OSError("audio device reset")
    with patch("core.audio.tts_engine.winsound.PlaySound") as mock_winsound:
        engine._play_pcm_int16(pcm, 16000, pa=pa)
    stream_16k.stop_stream.assert_called_once()
    stream_16k.close.assert_called_once()
    assert engine._output_stream is None
    mock_winsound.assert_called_once()


def test_synthesize_neural_short_phrase_length_scale():
    cfg = {"tts": {"voice_keyword": "maria"}}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(cfg)

    fake_piper = MagicMock()
    fake_piper.config = {
        "espeak": {"voice": "pt-br"},
        "inference": {"length_scale": 1.0},
    }
    fake_piper.phoneme_id_map = None
    fake_piper.create.return_value = (np.zeros(200, dtype=np.float32), 22050)

    with (
        patch.object(
            engine.voice_manager,
            "get_model_paths",
            return_value=(Path("jarvis_mk3.onnx"), Path("jarvis_mk3.onnx.json")),
        ),
        patch.object(engine, "_get_or_load_piper", return_value=fake_piper),
        patch("core.audio.tts_engine.phonemize", return_value="sˈĩ"),
        patch(
            "core.audio.tts_engine.apply_voice_dsp",
            side_effect=lambda s, _sr, _p: s,
        ),
    ):
        engine._synthesize_neural("Sim?", "jarvis_mk3", rate=2, volume=100)
        fast_scale = fake_piper.create.call_args.kwargs["length_scale"]
        assert fast_scale < 1.0

        engine._synthesize_neural("Sim?", "jarvis_mk3", rate=0, volume=100)
        default_scale = fake_piper.create.call_args.kwargs["length_scale"]
        assert default_scale == 1.04


def test_tts_worker_handles_null_runtime_and_tts_config():
    cfg = {"runtime": None, "tts": None}
    with patch("core.audio.tts_engine.threading.Thread"):
        engine = TTSEngine(cfg)

    # Must not raise AttributeError when config keys are explicitly None
    engine._prewarm_active_voice_if_configured()

    engine._stop_tts.set()
    with (
        patch("core.audio.tts_engine.pythoncom.CoInitialize"),
        patch("core.audio.tts_engine.pythoncom.CoUninitialize"),
        patch("core.audio.tts_engine.win32com.client.Dispatch"),
        patch("core.audio.tts_engine.create_pyaudio", return_value=MagicMock()),
        patch("core.audio.tts_engine.terminate_pyaudio"),
    ):
        engine._tts_worker()
