import logging
import time
import winsound
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

logger = logging.getLogger(__name__)


class CueType(str, Enum):
    WAKE = "wake"
    COMMAND_RECOGNIZED = "command_recognized"
    ACTION_COMPLETED = "action_completed"


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="AudioCueWorker")


def _play_sound_async(frequency: int, duration: int) -> None:
    try:
        winsound.Beep(frequency, duration)
    except Exception as e:
        logger.debug(f"Audio cue playback error: {e}")


class AudioCueManager:
    """Manages debounced non-blocking audio cue sound effects."""

    def __init__(self, config: dict) -> None:
        self.config = config.get("audio_cues", {})
        self.enabled = self.config.get("enabled", True)
        self.debounce_ms = self.config.get("debounce_ms", 200)
        self.last_cue_time = 0.0

        freq_config = self.config.get("frequencies", {})
        self.cue_frequencies = {
            CueType.WAKE: (
                freq_config.get("wake", [800, 80])[0],
                freq_config.get("wake", [800, 80])[1],
            ),
            CueType.COMMAND_RECOGNIZED: (
                freq_config.get("command_recognized", [1000, 60])[0],
                freq_config.get("command_recognized", [1000, 60])[1],
            ),
            CueType.ACTION_COMPLETED: (
                freq_config.get("action_completed", [1200, 100])[0],
                freq_config.get("action_completed", [1200, 100])[1],
            ),
        }

    def play_cue(self, cue_type: CueType) -> bool:
        if not self.enabled:
            return False

        now = time.time() * 1000
        if now - self.last_cue_time < self.debounce_ms:
            logger.debug(f"Audio cue '{cue_type}' debounced.")
            return False

        self.last_cue_time = now
        freq, dur = self.cue_frequencies.get(cue_type, (800, 80))
        _executor.submit(_play_sound_async, freq, dur)
        return True
