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
        self._speech_state_lock = threading.Lock()
        self._queued_count: int = 0
        self._active_utterance: bool = False
        self._output_stream: Any = None
        self._output_stream_rate: int = 0
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    @property
    def has_pending_speech(self) -> bool:
        """Returns True while any speech item is queued, synthesizing, or playing."""
        with self._speech_state_lock:
            return self.is_speaking or self._active_utterance or self._queued_count > 0

    def evict_cached_models(self, model_key: str | None = None) -> None:
        """Releases cached ONNX sessions so model files can be safely deleted on Windows."""
        with self._cache_lock:
            if model_key is None:
                self._piper_cache.clear()
            else:
                self._piper_cache.pop(model_key, None)
        gc.collect()

    def _get_or_load_piper(self, model_key: str, onnx_path: str, json_path: str) -> Any:
        """Loads and caches a Piper ONNX session (keeping at most 1 session in RAM)."""
        with self._cache_lock:
            cached = self._piper_cache.get(model_key)
            if cached is not None:
                return cached

            # Evict inactive ONNX sessions from RAM while leaving files on disk intact
            if self._piper_cache:
                self._piper_cache.clear()
                gc.collect()

            instance = Piper(model_path=onnx_path, config_path=json_path)
            self._piper_cache[model_key] = instance
            return instance

    @staticmethod
    def trim_pcm_silence(
        pcm_int16: NDArray[np.int16],
        sample_rate: int,
        threshold: int = 250,
        margin_ms: float = 25.0,
    ) -> NDArray[np.int16]:
        """Trims leading/trailing silence from synthesized PCM while keeping a safety margin."""
        if pcm_int16.size == 0 or sample_rate <= 0:
            return pcm_int16

        active_indices = np.flatnonzero(np.abs(pcm_int16.astype(np.int32)) > threshold)
        if active_indices.size == 0:
            return pcm_int16

        margin_samples = max(0, int(round((margin_ms / 1000.0) * sample_rate)))
        start = max(0, int(active_indices[0]) - margin_samples)
        end = min(pcm_int16.size, int(active_indices[-1]) + 1 + margin_samples)
        return pcm_int16[start:end]

    def _prewarm_active_voice_if_configured(self) -> None:
        """Preloads the active neural TTS model on startup only when lazy loading is disabled."""
        if not isinstance(self.config, dict):
            return
        raw_rt = self.config.get("runtime")
        rt_conf = raw_rt if isinstance(raw_rt, dict) else {}
        raw_mem = rt_conf.get("memory_optimization")
        mem_opt = raw_mem if isinstance(raw_mem, dict) else {}
        if mem_opt.get("lazy_load_secondary_modules", True):
            return

        raw_tts = self.config.get("tts")
        tts_conf = raw_tts if isinstance(raw_tts, dict) else {}
        active_voice_id = str(tts_conf.get("active_voice_id", DEFAULT_VOICE_ID))
        preset = get_voice_preset(active_voice_id)
        if preset.provider != "piper_onnx" or preset.model_asset is None:
            return

        paths = self.voice_manager.get_model_paths(preset.voice_id)
        if paths is None:
            return
        onnx_path, json_path = paths
        try:
            self._get_or_load_piper(
                preset.model_asset.model_key, str(onnx_path), str(json_path)
            )
            logger.info(
                f"Pre-warmed neural TTS model '{preset.voice_id}' (performance profile)."
            )
        except Exception as e:
            logger.debug(
                f"Failed to pre-warm neural TTS model '{preset.voice_id}': {e}"
            )

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
        phonemes_str = str(phonemes).strip() if phonemes else ""
        if not phonemes_str:
            return None
        if preset.period_phoneme_substitute:
            phonemes_str = phonemes_str.replace(".", preset.period_phoneme_substitute)
            if len(phonemes_str) <= 8 and phonemes_str.endswith("?"):
                phonemes_str = phonemes_str[:-1] + preset.period_phoneme_substitute

        base_length_scale = float(
            piper.config.get("inference", {}).get("length_scale", 1.0)
        )
        length_scale = self.rate_to_length_scale(rate, base_length_scale)
        if len(phonemes_str) <= 8 and rate <= 0:
            length_scale = max(length_scale, base_length_scale * 1.04)

        padded_phonemes = " " + phonemes_str
        pmap = getattr(piper, "phoneme_id_map", None)
        if (
            isinstance(pmap, dict)
            and "^" in pmap
            and "_" in pmap
            and "$" in pmap
            and hasattr(piper, "_create_input")
            and hasattr(piper, "sess")
        ):
            ids: list[int] = list(pmap["^"])
            for ch in padded_phonemes:
                if ch in pmap:
                    ids.extend(pmap[ch])
                    ids.extend(pmap["_"])
            ids.extend(pmap["$"])
            inputs = piper._create_input(ids, length_scale, 0.333, 0.333, 0)
            raw_samples = piper.sess.run(None, inputs)[0].squeeze((0, 1)).squeeze()
            samples = np.asarray(raw_samples, dtype=np.float32)
            sample_rate = int(piper.sample_rate)
        else:
            samples, sample_rate = piper.create(
                padded_phonemes,
                is_phonemes=True,
                length_scale=length_scale,
                noise_scale=0.333,
                noise_w=0.333,
            )

        processed = apply_voice_dsp(
            np.asarray(samples, dtype=np.float32),
            int(sample_rate),
            preset.dsp_profile,
        )

        unscaled_pcm = np.clip(processed * 32767.0, -32768, 32767).astype(np.int16)
        trimmed_pcm = self.trim_pcm_silence(unscaled_pcm, int(sample_rate))

        vol_factor = max(0.0, min(1.0, float(volume) / 100.0))
        if vol_factor < 1.0:
            pcm_int16 = np.clip(
                trimmed_pcm.astype(np.float32) * vol_factor, -32768, 32767
            ).astype(np.int16)
        else:
            pcm_int16 = trimmed_pcm
        return pcm_int16, int(sample_rate)

    def _close_output_stream(self) -> None:
        """Safely stops and closes the cached PyAudio output stream if open."""
        stream = self._output_stream
        self._output_stream = None
        self._output_stream_rate = 0
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception as e:
                logger.debug(f"Failed to close cached PyAudio output stream: {e}")

    def _play_pcm_int16(
        self,
        pcm_int16: NDArray[np.int16],
        sample_rate: int,
        pa: Any = None,
    ) -> None:
        """Plays 16-bit mono PCM audio with chunked interruption support and stream reuse."""
        if pcm_int16.size == 0:
            return

        # Lead with a brief silence and short fade-in/fade-out, plus a compact
        # trailing drain margin so Windows audio hardware finishes cleanly without clicks.
        padded_pcm = pcm_int16.copy()
        fade_samples = min(padded_pcm.size, max(1, int(sample_rate * 0.015)))
        if padded_pcm.size > fade_samples * 2:
            fade_in_samples = max(1, int(sample_rate * 0.005))
            fade_in = np.linspace(0.0, 1.0, fade_in_samples, dtype=np.float32)
            padded_pcm[:fade_in_samples] = (
                padded_pcm[:fade_in_samples].astype(np.float32) * fade_in
            ).astype(np.int16)
            fade_curve = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
            padded_pcm[-fade_samples:] = (
                padded_pcm[-fade_samples:].astype(np.float32) * fade_curve
            ).astype(np.int16)
        lead_silence = np.zeros(max(1, int(sample_rate * 0.05)), dtype=np.int16)
        tail_silence = np.zeros(max(1, int(sample_rate * 0.07)), dtype=np.int16)
        playback_pcm = np.concatenate([lead_silence, padded_pcm, tail_silence])

        owned_pa = False
        try:
            if pa is None:
                pa = create_pyaudio()
                owned_pa = True

            stream = None
            reusable = not owned_pa
            try:
                if reusable:
                    if (
                        self._output_stream is not None
                        and self._output_stream_rate != sample_rate
                    ):
                        self._close_output_stream()
                    if self._output_stream is None:
                        self._output_stream = pa.open(
                            format=pa.get_format_from_width(2),
                            channels=1,
                            rate=sample_rate,
                            output=True,
                        )
                        self._output_stream_rate = sample_rate
                    stream = self._output_stream
                else:
                    stream = pa.open(
                        format=pa.get_format_from_width(2),
                        channels=1,
                        rate=sample_rate,
                        output=True,
                    )

                chunk_samples = 2048
                total = playback_pcm.size
                idx = 0
                while (
                    idx < total
                    and not self._stop_tts.is_set()
                    and not self._abort_current.is_set()
                ):
                    sub = playback_pcm[idx : idx + chunk_samples]
                    stream.write(sub.tobytes())
                    idx += chunk_samples

                # Reusable streams skip stop_stream(), so wait for the OS output buffer
                # to finish draining before clearing is_speaking.
                if (
                    reusable
                    and not self._stop_tts.is_set()
                    and not self._abort_current.is_set()
                ):
                    try:
                        latency = stream.get_output_latency()
                        if isinstance(latency, (int, float)) and latency > 0:
                            self._abort_current.wait(timeout=min(0.25, float(latency)))
                    except Exception:
                        pass
            except Exception:
                if reusable:
                    self._close_output_stream()
                raise
            finally:
                if not reusable and stream is not None:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                elif reusable and (
                    self._abort_current.is_set() or self._stop_tts.is_set()
                ):
                    self._close_output_stream()
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
            raw_tts_init = (
                self.config.get("tts") if isinstance(self.config, dict) else {}
            )
            tts_init = raw_tts_init if isinstance(raw_tts_init, dict) else {}
            voice_keyword = str(
                tts_init.get("voice_keyword", DEFAULT_SAPI5_VOICE)
                or DEFAULT_SAPI5_VOICE
            ).lower()
            self._configure_sapi_voice(voice, voice_keyword)

            try:
                pa = create_pyaudio()
            except Exception as e:
                logger.debug(f"PyAudio unavailable in TTS worker: {e}")

            self._prewarm_active_voice_if_configured()

            while not self._stop_tts.is_set():
                try:
                    text = self._speech_queue.get(timeout=Timing.UI_STABILIZATION_LONG)
                    with self._speech_state_lock:
                        self._queued_count = max(0, self._queued_count - 1)
                        self._active_utterance = True
                    try:
                        self._abort_current.clear()

                        raw_tts = (
                            self.config.get("tts")
                            if isinstance(self.config, dict)
                            else {}
                        )
                        tts_conf = raw_tts if isinstance(raw_tts, dict) else {}
                        rate = int(tts_conf.get("rate", DEFAULT_TTS_RATE))
                        volume = int(tts_conf.get("volume", DEFAULT_TTS_VOLUME))
                        active_voice_id = str(
                            self._preview_voice_override
                            or tts_conf.get("active_voice_id", DEFAULT_VOICE_ID)
                        )

                        logger.info(f"Jarvis is speaking ({active_voice_id}): '{text}'")

                        synth: tuple[NDArray[np.int16], int] | None = None
                        preset = get_voice_preset(active_voice_id)
                        if preset.provider == "piper_onnx":
                            try:
                                synth = self._synthesize_neural(
                                    text=text,
                                    voice_id=preset.voice_id,
                                    rate=rate,
                                    volume=volume,
                                )
                            except Exception as e:
                                logger.error(
                                    f"Neural/DSP TTS synthesis error for '{active_voice_id}', falling back to SAPI5: {e}"
                                )

                        if (
                            not self._abort_current.is_set()
                            and not self._stop_tts.is_set()
                        ):
                            self.is_speaking = True
                            try:
                                if synth is not None:
                                    pcm_int16, sample_rate = synth
                                    self._play_pcm_int16(pcm_int16, sample_rate, pa=pa)
                                else:
                                    voice.Rate = rate
                                    voice.Volume = volume
                                    voice.Speak(text, 0)
                            finally:
                                self.is_speaking = False

                        self.last_spoken_time = time.time()
                    finally:
                        with self._speech_state_lock:
                            self._active_utterance = False
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
            self._close_output_stream()
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
        drained = 0
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
                drained += 1
            except (queue.Empty, ValueError):
                break
        if drained:
            with self._speech_state_lock:
                self._queued_count = max(0, self._queued_count - drained)

    def _enqueue_sentences(self, sentences: list[str]) -> None:
        """Pushes prepared sentences onto the speech queue while tracking pending count."""
        with self._speech_state_lock:
            self._queued_count += len(sentences)
        for s in sentences:
            self._speech_queue.put(s)

    def speak(self, text: str) -> None:
        now = time.time()
        raw_tts = self.config.get("tts") if isinstance(self.config, dict) else {}
        tts_conf = raw_tts if isinstance(raw_tts, dict) else {}
        cooldown = float(tts_conf.get("cooldown_seconds", 2.0) or 2.0)
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

        self._enqueue_sentences(sentences)

    def speak_preview(self, text: str, voice_id: str | None = None) -> None:
        """Interrupts current speech and immediately speaks a sample using voice_id."""
        clean = text.strip()
        if not clean:
            return
        self.clear_queue()
        self._preview_voice_override = voice_id
        self.last_spoken_text = ""
        sentences = self.split_into_sentences(clean)
        if sentences:
            self._enqueue_sentences(sentences)

    def stop(self) -> None:
        self._abort_current.set()
        self._stop_tts.set()
        self._tts_thread.join(timeout=2.0)
