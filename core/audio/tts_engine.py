import queue
import threading
import time
from typing import Any

import pythoncom
import win32com.client

from core.infra.logger_config import logger
from core.shared.constants import (
    DEFAULT_SAPI5_LANGS,
    DEFAULT_SAPI5_VOICE,
    DEFAULT_TTS_RATE,
    DEFAULT_TTS_VOLUME,
    Timing,
)


class TTSEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.last_spoken_text = ""
        self.last_spoken_time = 0.0
        self.is_speaking = False
        self._speech_queue: queue.Queue[str] = queue.Queue()
        self._stop_tts = threading.Event()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

    def _tts_worker(self) -> None:
        try:
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice_keyword = (
                self.config.get("tts", {})
                .get("voice_keyword", DEFAULT_SAPI5_VOICE)
                .lower()
            )
            try:
                available_voices = voice.GetVoices()
                selected_voice = None
                for i in range(available_voices.Count):
                    v = available_voices.Item(i)
                    desc = v.GetDescription()
                    if voice_keyword in desc.lower():
                        selected_voice = v
                if selected_voice:
                    voice.Voice = selected_voice
                else:
                    for i in range(available_voices.Count):
                        v = available_voices.Item(i)
                        desc = v.GetDescription().lower()
                        if (
                            DEFAULT_SAPI5_LANGS[0] in desc
                            or DEFAULT_SAPI5_LANGS[1] in desc
                        ):
                            voice.Voice = v
                            break
            except Exception as e:
                logger.debug(f"Default voice will be used: {e}")

            voice.Rate = DEFAULT_TTS_RATE
            voice.Volume = DEFAULT_TTS_VOLUME

            while not self._stop_tts.is_set():
                try:
                    text = self._speech_queue.get(timeout=Timing.UI_STABILIZATION_LONG)
                    self.is_speaking = True
                    logger.info(f"Jarvis is speaking: '{text}'")
                    voice.Speak(text, 0)
                    self.is_speaking = False
                    self.last_spoken_time = time.time()
                    self._speech_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    self.is_speaking = False
                    logger.error(f"SAPI TTS error: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize SAPI5: {e}")
        finally:
            pythoncom.CoUninitialize()
            logger.info("TTS Worker thread finishing.")

    def speak(self, text: str) -> None:
        now = time.time()
        if text == self.last_spoken_text and (now - self.last_spoken_time) < 2.0:
            logger.debug(f"Skipping duplicate speech: {text}")
            return
        self.last_spoken_text = text
        self._speech_queue.put(text)

    def stop(self) -> None:
        self._stop_tts.set()
        self._tts_thread.join(timeout=2.0)
