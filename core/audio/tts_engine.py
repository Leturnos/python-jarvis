import gc
import io
import queue
import re
import threading
import time
import wave
import winsound
from typing import Any

import espeakng_loader
import numpy as np
import pythoncom
import win32com.client
from numpy.typing import NDArray
from phonemizer import phonemize
from phonemizer.backend.espeak.wrapper import EspeakWrapper
from piper_onnx import Piper

from core.audio.portaudio_lock import create_pyaudio, terminate_pyaudio
from core.audio.voice_catalog import DEFAULT_VOICE_ID, get_voice_preset
from core.audio.voice_dsp import apply_voice_dsp
from core.audio.voice_manager import VoiceManager
from core.infra.logger_config import logger
from core.shared.constants import (
    DEFAULT_SAPI5_LANGS,
    DEFAULT_SAPI5_VOICE,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOLUME,
    Timing,
)

try:
    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
except Exception as e:
    logger.debug(f"Failed to configure espeakng library paths: {e}")


class TTSEngine:
    def __init__(
        self,
        config: dict[str, Any],
        voice_manager: VoiceManager | None = None,
    ) -> None:
        self.config = config
        self.voice_manager = voice_manager or VoiceManager()
        self.last_spoken_text = ""
        self.last_spoken_time = 0.0
        self.last_enqueued_time = 0.0
        self.is_speaking = False
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self._stop_tts = threading.Event()
        self._abort_current = threading.Event()
        self._preview_voice_override: str | None = None
        self._piper_cache: dict[str, Any] = {}
        self._cache_lock = threading.Lock()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def evict_cached_models(self, model_key: str | None = None) -> None:
        """Releases cached ONNX sessions so model files can be safely deleted on Windows."""
        with self._cache_lock:
            if model_key is None:
                self._piper_cache.clear()
            else:
                self._piper_cache.pop(model_key, None)
        gc.collect()

    def _get_or_load_piper(self, model_key: str, onnx_path: str, json_path: str) -> Any:
        """Loads and caches a Piper ONNX session for the requested model_key."""
        with self._cache_lock:
            cached = self._piper_cache.get(model_key)
            if cached is not None:
                return cached

            instance = Piper(model_path=onnx_path, config_path=json_path)
            self._piper_cache[model_key] = instance
            return instance

    @staticmethod
    def rate_to_length_scale(rate: int, base_scale: float = 1.0) -> float:
        """Converts SAPI5-style rate (-10 to +10) into Piper VITS length_scale."""
        clamped_rate = max(-10, min(10, int(rate)))
        scale = float(base_scale) * (1.0 - (0.04 * clamped_rate))
        return float(max(0.55, min(1.65, scale)))

    def _synthesize_neural(
        self, text: str, voice_id: str, rate: int, volume: int
    ) -> tuple[NDArray[np.int16], int] | None:
        """Synthesizes speech using Piper ONNX and applies the preset DSP profile."""
        preset = get_voice_preset(voice_id)
        if preset.provider != "piper_onnx" or preset.model_asset is None:
            return None

        paths = self.voice_manager.get_model_paths(preset.voice_id)
        if paths is None:
            return None

        onnx_path, json_path = paths
        piper = self._get_or_load_piper(
            preset.model_asset.model_key, str(onnx_path), str(json_path)
        )

        espeak_voice = (
            piper.config.get("espeak", {}).get("voice", "pt-br")
            if isinstance(piper.config, dict)
            else "pt-br"
        )
        phonemes = phonemize(
            text,
            language=espeak_voice,
            backend="espeak",
            preserve_punctuation=True,
            with_stress=True,
        )
        if not phonemes or not str(phonemes).strip():
            return None

        base_length_scale = float(
            piper.config.get("inference", {}).get("length_scale", 1.0)
        )
        length_scale = self.rate_to_length_scale(rate, base_length_scale)

        samples, sample_rate = piper.create(
            str(phonemes),
            is_phonemes=True,
            length_scale=length_scale,
        )

        processed = apply_voice_dsp(
            np.asarray(samples, dtype=np.float32),
            int(sample_rate),
            preset.dsp_profile,
        )

        vol_factor = max(0.0, min(1.0, float(volume) / 100.0))
        pcm_int16 = np.clip(processed * vol_factor * 32767.0, -32768, 32767).astype(
            np.int16
        )
        return pcm_int16, int(sample_rate)

    def _play_pcm_int16(
        self,
        pcm_int16: NDArray[np.int16],
        sample_rate: int,
        pa: Any = None,
    ) -> None:
        """Plays 16-bit mono PCM audio with chunked interruption support."""
        if pcm_int16.size == 0:
            return

        owned_pa = False
        try:
            if pa is None:
                pa = create_pyaudio()
                owned_pa = True

            stream = None
            try:
                stream = pa.open(
                    format=pa.get_format_from_width(2),
                    channels=1,
                    rate=sample_rate,
                    output=True,
                )
                chunk_samples = 2048
                total = pcm_int16.size
                idx = 0
                while (
                    idx < total
                    and not self._stop_tts.is_set()
                    and not self._abort_current.is_set()
                ):
                    sub = pcm_int16[idx : idx + chunk_samples]
                    stream.write(sub.tobytes())
                    idx += chunk_samples
            finally:
                if stream is not None:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if owned_pa and pa is not None:
                    terminate_pyaudio(pa)
        except Exception as e:
            if self._abort_current.is_set() or self._stop_tts.is_set():
                return
            logger.debug(f"PyAudio playback fallback to winsound: {e}")
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_int16.tobytes())
            if not self._abort_current.is_set() and not self._stop_tts.is_set():
                winsound.PlaySound(wav_buf.getvalue(), winsound.SND_MEMORY)

    @staticmethod
    def _configure_sapi_voice(voice_obj: Any, voice_keyword: str) -> None:
        try:
            available_voices = voice_obj.GetVoices()
            selected_voice = None
            for i in range(available_voices.Count):
                v = available_voices.Item(i)
                desc = v.GetDescription()
                if voice_keyword in desc.lower():
                    selected_voice = v
            if selected_voice:
                voice_obj.Voice = selected_voice
            else:
                for i in range(available_voices.Count):
                    v = available_voices.Item(i)
                    desc = v.GetDescription().lower()
                    if DEFAULT_SAPI5_LANGS[0] in desc or DEFAULT_SAPI5_LANGS[1] in desc:
                        voice_obj.Voice = v
                        break
        except Exception as e:
            logger.debug(f"Default SAPI5 voice will be used: {e}")

    def _tts_worker(self) -> None:
        pa = None
        try:
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice_keyword = (
                self.config.get("tts", {})
                .get("voice_keyword", DEFAULT_SAPI5_VOICE)
                .lower()
            )
            self._configure_sapi_voice(voice, voice_keyword)

            try:
                pa = create_pyaudio()
            except Exception as e:
                logger.debug(f"PyAudio unavailable in TTS worker: {e}")

            while not self._stop_tts.is_set():
                try:
                    text = self._speech_queue.get(timeout=Timing.UI_STABILIZATION_LONG)
                    self._abort_current.clear()
                    self.is_speaking = True

                    tts_conf = self.config.get("tts", {})
                    rate = int(tts_conf.get("rate", DEFAULT_TTS_RATE))
                    volume = int(tts_conf.get("volume", DEFAULT_TTS_VOLUME))
                    active_voice_id = str(
                        self._preview_voice_override
                        or tts_conf.get("active_voice_id", DEFAULT_VOICE_ID)
                    )

                    logger.info(f"Jarvis is speaking ({active_voice_id}): '{text}'")

                    spoken_via_pcm = False
                    preset = get_voice_preset(active_voice_id)
                    if preset.provider == "piper_onnx":
                        try:
                            synth = self._synthesize_neural(
                                text=text,
                                voice_id=preset.voice_id,
                                rate=rate,
                                volume=volume,
                            )
                            if synth is not None:
                                pcm_int16, sample_rate = synth
                                self._play_pcm_int16(pcm_int16, sample_rate, pa=pa)
                                spoken_via_pcm = True
                        except Exception as e:
                            logger.error(
                                f"Neural/DSP TTS synthesis error for '{active_voice_id}', falling back to SAPI5: {e}"
                            )

                    if not spoken_via_pcm and not self._abort_current.is_set():
                        voice.Rate = rate
                        voice.Volume = volume
                        voice.Speak(text, 0)

                    self.is_speaking = False
                    self.last_spoken_time = time.time()
                    self._speech_queue.task_done()
                    if self._speech_queue.empty():
                        self._preview_voice_override = None
                except queue.Empty:
                    continue
                except Exception as e:
                    self.is_speaking = False
                    logger.error(f"TTS worker error: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize TTS worker: {e}")
        finally:
            if pa is not None:
                try:
                    terminate_pyaudio(pa)
                except Exception:
                    pass
            pythoncom.CoUninitialize()
            logger.info("TTS Worker thread finishing.")

    @staticmethod
    def split_into_sentences(text: str) -> list[str]:
        """Splits multi-sentence text into clean speech chunks at punctuation boundaries."""
        clean = text.strip()
        if not clean:
            return []
        parts = re.split(r"(?<=[.!?\n])\s+", clean)
        return [p.strip() for p in parts if p.strip()]

    def clear_queue(self) -> None:
        """Empties pending speech items to allow immediate interruption."""
        self._abort_current.set()
        self._preview_voice_override = None
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except (queue.Empty, ValueError):
                break

    def speak(self, text: str) -> None:
        now = time.time()
        cooldown = self.config.get("tts", {}).get("cooldown_seconds", 2.0)
        if text == self.last_spoken_text and (
            self.is_speaking
            or (now - self.last_spoken_time) < cooldown
            or (now - self.last_enqueued_time) < cooldown
        ):
            logger.debug(f"Skipping duplicate speech: {text}")
            return
        self.last_spoken_text = text
        self.last_enqueued_time = now

        sentences = self.split_into_sentences(text)
        if not sentences:
            return

        for s in sentences:
            self._speech_queue.put(s)

    def speak_preview(self, text: str, voice_id: str | None = None) -> None:
        """Interrupts current speech and immediately speaks a sample using voice_id."""
        clean = text.strip()
        if not clean:
            return
        self.clear_queue()
        self._preview_voice_override = voice_id
        self.last_spoken_text = ""
        for s in self.split_into_sentences(clean):
            self._speech_queue.put(s)

    def stop(self) -> None:
        self._abort_current.set()
        self._stop_tts.set()
        self._tts_thread.join(timeout=2.0)
