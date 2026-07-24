import logging
import threading
import time
from typing import Any

import numpy as np

from core.audio.audio_engine import safe_reset_audio

logger = logging.getLogger(__name__)


class AudioLoopManager:
    """Manages the physical audio hardware stream, volume multipliers, and self-healing.

    This class isolates PyAudio dependencies and raw device recovery logic from the main controller.
    """

    def __init__(
        self,
        config: dict[str, Any],
        dispatcher: Any,
        ui: Any,
        pa: Any,
        stream: Any,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.ui = ui
        self.pa = pa
        self.stream = stream
        self.stop_event = stop_event
        self.consecutive_zero_rms = 0

        self.frame_size = config.get("voice_activation", {}).get(
            "frames_per_buffer", 1280
        )
        self.volume_multiplier = config.get("jarvis", {}).get("volume_multiplier", 1.0)
        self.max_zero_rms_before_reset = (
            config.get("voice_activation", {})
            .get("thresholds", {})
            .get("max_zero_rms_frames", 30)
        )

    def read_frame(self) -> tuple[np.ndarray | None, float]:
        """Reads a frame of audio from the input stream and calculates its RMS.

        If a stream error occurs, it attempts to safely reset the audio device.
        """
        try:
            audio_data = self.stream.read(self.frame_size, exception_on_overflow=False)
            pcm = np.frombuffer(audio_data, dtype=np.int16)

            if self.volume_multiplier != 1.0:
                pcm = (
                    (pcm * self.volume_multiplier).clip(-32768, 32767).astype(np.int16)
                )

            rms = np.sqrt(np.mean(pcm.astype(np.float32) ** 2))
            return pcm, rms
        except Exception as e:
            if self.stop_event is not None and self.stop_event.is_set():
                return None, 0.0
            logger.error(f"Microphone stream error: {e}. Resetting...")
            self.ui.update(status="Resetting Mic...")
            self.pa, self.stream = safe_reset_audio(self.pa, self.stream)
            self.dispatcher.audio_stream = self.stream
            time.sleep(1)
            return None, 0.0

    def check_dead_silence(self, rms: float, model: Any) -> bool:
        """Verifies if the stream is dead silent and performs self-healing.

        Args:
            rms (float): The current audio frame volume.
            model (Any): The wake word model to reset on self-heal.
        """
        if rms < 0.1:
            self.consecutive_zero_rms += 1
        else:
            self.consecutive_zero_rms = 0

        if self.consecutive_zero_rms > self.max_zero_rms_before_reset:
            logger.warning("Dead silence detected! Self-healing...")
            self.ui.update(status="Self-Healing...")
            self.pa, self.stream = safe_reset_audio(self.pa, self.stream)
            self.dispatcher.audio_stream = self.stream
            self.consecutive_zero_rms = 0
            model.reset()
            return True
        return False

    def cleanup(self) -> None:
        """Safely stops and releases PyAudio resources."""
        logger.info("Cleaning up AudioLoopManager...")
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.pa.terminate()
        except Exception as e:
            logger.debug(f"Error terminating PyAudio: {e}")
